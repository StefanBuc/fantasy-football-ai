from pathlib import Path

import numpy as np
import torch
import argparse

from app.services.NFL_data import NFLData
from app.services.player_sequence_dataset import PlayerSequenceDataset
from app.services.pytorch_projection_model import (
    load_projection_checkpoint,
    predict_from_raw_features,
)
from app.services.defense_features import build_upcoming_defense_features

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--position",
        choices=["QB", "RB", "WR", "TE"],
        default="QB",
    )

    parser.add_argument(
        "--version",
        type=int,
        default=2,
    )

    return parser.parse_args()

def main():
    args = parse_args()
    backend_dir = Path(__file__).resolve().parents[2]
    checkpoint_path = (
        backend_dir
        / "models"
        / "pytorch"
        / f"{args.position}_model_v{args.version}.pth"
    )

    (
        model,
        sequence_scaler,
        matchup_scaler,
        checkpoint,
        device,
    ) = load_projection_checkpoint(checkpoint_path)

    data = NFLData([2024])
    data.load_data()
    
    defense_df = data.get_defense_stats()
    

    dataset = PlayerSequenceDataset(
        data.get_player_stats(),
        defense_df,
        feature_cols=checkpoint["feature_cols"],
        sequence_length=checkpoint["sequence_length"],
        position=checkpoint["position"],
        seasons=checkpoint["test_seasons"],
        scaler=sequence_scaler,
        matchup_scaler=matchup_scaler,
    )

    scaled_sequence, scaled_matchup, target = dataset[0]
    metadata = dataset.sample_metadata[0]
        
    with torch.no_grad():
        direct_prediction = model(
            scaled_sequence.unsqueeze(0).to(device),
            scaled_matchup.unsqueeze(0).to(device),
        ).item()

    raw_sequence = sequence_scaler.inverse_transform(
        scaled_sequence.numpy()
    )

    raw_matchup = matchup_scaler.inverse_transform(
        scaled_matchup.numpy().reshape(1, -1)
    )[0]
    
    calculated_matchup = build_upcoming_defense_features(
        defense_df=defense_df,
        defense_team=metadata["opponent_team"],
        season=metadata["season"],
        position=checkpoint["position"],
        upcoming_week=metadata["week"],
    )

    calculated_matchup_values = np.asarray(
        [
            calculated_matchup[column]
            for column in checkpoint["matchup_feature_cols"]
        ],
        dtype=np.float32,
    )

    np.testing.assert_allclose(
        calculated_matchup_values,
        raw_matchup,
        rtol=1e-5,
        atol=1e-4,
    )

    print("Upcoming matchup calculation passed.")

    history = [
        dict(zip(checkpoint["feature_cols"], game))
        for game in raw_sequence
    ]

    matchup = calculated_matchup

    raw_input_prediction = predict_from_raw_features(
        model,
        sequence_scaler,
        matchup_scaler,
        checkpoint,
        device,
        history,
        matchup,
    )

    print(f"Direct prediction: {direct_prediction:.6f}")
    print(f"Raw-input prediction: {raw_input_prediction:.6f}")
    print(f"Actual points: {target.item():.2f}")
    print(f"Sample: {metadata}")

    if not np.isclose(
        direct_prediction,
        raw_input_prediction,
        atol=1e-5,
    ):
        raise RuntimeError("Inference round-trip does not match.")

    print("Inference round-trip passed.")


if __name__ == "__main__":
    main()