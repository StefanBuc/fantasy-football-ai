from pathlib import Path
import torch
import torch.nn as nn
import json
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import StandardScaler
import numpy as np
from app.config.model_config import (
    SELECTED_PYTORCH_MODEL_VERSIONS,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

def scaler_from_state(state):
    scaler = StandardScaler()

    scaler.mean_ = state["mean"].cpu().numpy()
    scaler.scale_ = state["scale"].cpu().numpy()
    scaler.var_ = state["var"].cpu().numpy()
    scaler.n_features_in_ = int(state["n_features_in"])
    scaler.n_samples_seen_ = int(state["n_samples_seen"])

    return scaler

def load_projection_checkpoint(checkpoint_path: str | Path, device: torch.device | None = None):
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    
    if checkpoint.get("format_version") != 2:
        raise ValueError("Unsupported checkpoint format.")

    feature_cols = checkpoint["feature_cols"]
    matchup_feature_cols = checkpoint["matchup_feature_cols"]

    model = PyTorchProjectionModel(
        input_size=len(feature_cols),
        matchup_size=len(matchup_feature_cols),
        **checkpoint["model_config"],
    )

    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    sequence_scaler = scaler_from_state(
        checkpoint["sequence_scaler"]
    )
    matchup_scaler = scaler_from_state(
        checkpoint["matchup_scaler"]
    )

    return (
        model,
        sequence_scaler,
        matchup_scaler,
        checkpoint,
        device,
    )
    
def load_selected_projection_checkpoint(
    position: str,
    device: torch.device | None = None,
):
    normalized_position = position.upper()

    if (
        normalized_position
        not in SELECTED_PYTORCH_MODEL_VERSIONS
    ):
        raise ValueError(
            f"Unsupported position: {position}"
        )

    version = SELECTED_PYTORCH_MODEL_VERSIONS[
        normalized_position
    ]

    checkpoint_path = (
        BASE_DIR
        / "models"
        / "pytorch"
        / (
            f"{normalized_position}"
            f"_model_v{version}.pth"
        )
    )

    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"Selected checkpoint does not exist: "
            f"{checkpoint_path}"
        )

    loaded = load_projection_checkpoint(
        checkpoint_path,
        device=device,
    )

    checkpoint = loaded[3]

    if (
        checkpoint["position"] != normalized_position
        or checkpoint["version"] != version
    ):
        raise ValueError(
            "Selected checkpoint metadata does not "
            "match the model registry."
        )

    return loaded

class PyTorchProjectionModel(nn.Module):
    def __init__(self, input_size: int, matchup_size: int, hidden_size: int = 64, num_layers: int = 2, dropout: float = 0.2,):
        super().__init__()

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        self.matchup_encoder = nn.Sequential(
            nn.Linear(matchup_size, 16),
            nn.ReLU(),
        )

        self.output_layer = nn.Sequential(
            nn.Linear(hidden_size + 16, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(
        self,
        sequence: torch.Tensor,
        matchup: torch.Tensor,
    ) -> torch.Tensor:

        lstm_out, _ = self.lstm(sequence)

        # Representation of the previous 5 games
        history = lstm_out[:, -1, :]
    
        # Encode the matchup information
        matchup_encoded = self.matchup_encoder(matchup)

        # Add upcoming opponent information
        combined = torch.cat(
            [history, matchup_encoded],
            dim=1,
        )

        prediction = self.output_layer(combined)

        return prediction.squeeze(-1)

def predict_from_raw_features(
    model,
    sequence_scaler,
    matchup_scaler,
    checkpoint,
    device,
    history,
    matchup,
):
    feature_cols = checkpoint["feature_cols"]
    matchup_cols = checkpoint["matchup_feature_cols"]
    sequence_length = checkpoint["sequence_length"]

    if len(history) != sequence_length:
        raise ValueError(
            f"Expected {sequence_length} history games, "
            f"received {len(history)}."
        )

    sequence_values = []

    for game_number, game in enumerate(history, start=1):
        missing = [
            column
            for column in feature_cols
            if column not in game
        ]

        if missing:
            raise ValueError(
                f"History game {game_number} is missing: {missing}"
            )

        sequence_values.append(
            [game[column] for column in feature_cols]
        )

    missing_matchup = [
        column
        for column in matchup_cols
        if column not in matchup
    ]

    if missing_matchup:
        raise ValueError(
            f"Matchup is missing: {missing_matchup}"
        )

    sequence_array = np.asarray(
        sequence_values,
        dtype=np.float32,
    )

    matchup_array = np.asarray(
        [[matchup[column] for column in matchup_cols]],
        dtype=np.float32,
    )

    if not np.isfinite(sequence_array).all():
        raise ValueError("History features must be finite.")

    if not np.isfinite(matchup_array).all():
        raise ValueError("Matchup features must be finite.")

    scaled_sequence = sequence_scaler.transform(sequence_array)
    scaled_matchup = matchup_scaler.transform(matchup_array)

    sequence_tensor = torch.tensor(
        scaled_sequence,
        dtype=torch.float32,
        device=device,
    ).unsqueeze(0)

    matchup_tensor = torch.tensor(
        scaled_matchup,
        dtype=torch.float32,
        device=device,
    )

    model.eval()

    with torch.no_grad():
        prediction = model(sequence_tensor, matchup_tensor)

    return float(prediction.item())

def predict_batch_from_raw_features(
    model,
    sequence_scaler,
    matchup_scaler,
    checkpoint,
    device,
    histories,
    matchups,
) -> list[float]:
    if len(histories) != len(matchups):
        raise ValueError(
            "History and matchup counts do not match."
        )

    if not histories:
        return []

    feature_cols = checkpoint["feature_cols"]
    matchup_cols = checkpoint["matchup_feature_cols"]
    sequence_length = checkpoint["sequence_length"]

    sequence_values = []

    for sample_number, history in enumerate(
        histories,
        start=1,
    ):
        if len(history) != sequence_length:
            raise ValueError(
                f"Sample {sample_number} expected "
                f"{sequence_length} history games, "
                f"received {len(history)}."
            )

        sample_values = []

        for game_number, game in enumerate(
            history,
            start=1,
        ):
            missing = [
                column
                for column in feature_cols
                if column not in game
            ]

            if missing:
                raise ValueError(
                    f"Sample {sample_number}, history game "
                    f"{game_number} is missing: {missing}"
                )

            sample_values.append(
                [
                    game[column]
                    for column in feature_cols
                ]
            )

        sequence_values.append(sample_values)

    matchup_values = []

    for sample_number, matchup in enumerate(
        matchups,
        start=1,
    ):
        missing = [
            column
            for column in matchup_cols
            if column not in matchup
        ]

        if missing:
            raise ValueError(
                f"Sample {sample_number} matchup is "
                f"missing: {missing}"
            )

        matchup_values.append(
            [
                matchup[column]
                for column in matchup_cols
            ]
        )

    sequence_array = np.asarray(
        sequence_values,
        dtype=np.float32,
    )

    matchup_array = np.asarray(
        matchup_values,
        dtype=np.float32,
    )

    if not np.isfinite(sequence_array).all():
        raise ValueError(
            "History features must be finite."
        )

    if not np.isfinite(matchup_array).all():
        raise ValueError(
            "Matchup features must be finite."
        )

    batch_size, sequence_length, feature_count = (
        sequence_array.shape
    )

    scaled_sequences = sequence_scaler.transform(
        sequence_array.reshape(-1, feature_count)
    ).reshape(
        batch_size,
        sequence_length,
        feature_count,
    )

    scaled_matchups = matchup_scaler.transform(
        matchup_array
    )

    sequence_tensor = torch.as_tensor(
        scaled_sequences,
        dtype=torch.float32,
        device=device,
    )

    matchup_tensor = torch.as_tensor(
        scaled_matchups,
        dtype=torch.float32,
        device=device,
    )

    model.eval()

    with torch.inference_mode():
        predictions = model(
            sequence_tensor,
            matchup_tensor,
        )

    return [
        float(value)
        for value in predictions.cpu().tolist()
    ]