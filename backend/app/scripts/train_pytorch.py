import argparse
import torch
import random
import numpy as np
import copy
from pathlib import Path

from app.services.pytorch_projection_model import PyTorchProjectionModel
from app.services.NFL_data import NFLData
from app.config.model_config import POSITION_CONFIGS, QB_FEATURE_COLS, RB_FEATURE_COLS, WR_TE_FEATURE_COLS, FEATURE_COLS
from app.services.player_sequence_dataset import PlayerSequenceDataset

FEATURES_BY_POSITION = {
    "QB": QB_FEATURE_COLS,
    "RB": RB_FEATURE_COLS,
    "WR": WR_TE_FEATURE_COLS,
    "TE": WR_TE_FEATURE_COLS,
}

parser = argparse.ArgumentParser()

parser.add_argument("-p", "--position", type=str.upper, choices=["QB", "RB", "WR", "TE", "ALL"], default="ALL", help="Position to train the model for. If not specified, the model will be trained for all positions.")
parser.add_argument("-s", "--season", type=int, nargs="+", default=[2020, 2021, 2022, 2023, 2024], help="Seasons to include in the training data. If not specified, the model will be trained on all seasons from 2020 to 2024.")
parser.add_argument("--batch_size", type=int, default=32, help="Batch size for training.")
parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
parser.add_argument("--learning_rate", type=float, default=0.001, help="Learning rate for the optimizer.")
parser.add_argument("--num_epochs", type=int, default=30, help="Number of epochs to train the model.")
parser.add_argument("--patience", type=int, default=7, help="Number of epochs to wait for improvement before early stopping.")
parser.add_argument("--version", type=int, default=2, help="Version number for saving the model.")

def parse_arguments():
    args = parser.parse_args()
    return args

def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def train_one_epoch(model, loader, loss_fn, optimizer, device):
    model.train()

    total_loss = 0.0
    total_examples = 0

    for sequence, matchup, target in loader:
        sequence = sequence.to(device)
        matchup = matchup.to(device)
        target = target.to(device)

        optimizer.zero_grad()

        predictions = model(sequence, matchup)
        loss = loss_fn(predictions, target)

        loss.backward()

        torch.nn.utils.clip_grad_norm_(
            model.parameters(),
            max_norm=1.0,
        )

        optimizer.step()

        batch_size = target.size(0)
        total_loss += loss.item() * batch_size
        total_examples += batch_size

    return total_loss / total_examples

def evaluate(model, loader, loss_fn, device):
    model.eval()
    
    total_loss = 0.0
    total_examples = 0
    
    with torch.no_grad():
        for sequence, matchup, target in loader:
            sequence = sequence.to(device)
            matchup = matchup.to(device)
            target = target.to(device)

            predictions = model(sequence, matchup)
            loss = loss_fn(predictions, target)

            batch_size = target.size(0)
            total_loss += loss.item() * batch_size
            total_examples += batch_size
    
    return total_loss / total_examples

def scaler_state(scaler):
    return {
        "mean": torch.tensor(scaler.mean_, dtype=torch.float64),
        "scale": torch.tensor(scaler.scale_, dtype=torch.float64),
        "var": torch.tensor(scaler.var_, dtype=torch.float64),
        "n_features_in": int(scaler.n_features_in_),
        "n_samples_seen": int(
            np.asarray(scaler.n_samples_seen_).max()
        ),
    }
    
def calculate_baselines(dataset):
    scaled = dataset.sequences.numpy()
    sample_count, sequence_length, feature_count = scaled.shape

    unscaled = dataset.scaler.inverse_transform(
        scaled.reshape(-1, feature_count)
    ).reshape(sample_count, sequence_length, feature_count)

    points_index = dataset.feature_cols.index(
        "fantasy_points_ppr"
    )

    targets = dataset.targets.numpy()
    last_game_predictions = unscaled[:, -1, points_index]
    rolling_mean_predictions = unscaled[:, :, points_index].mean(axis=1)

    return {
        "last_game_mae": float(
            np.mean(np.abs(targets - last_game_predictions))
        ),
        "rolling_mean_mae": float(
            np.mean(np.abs(targets - rolling_mean_predictions))
        ),
    }   

def main():
    args = parse_arguments()
    set_seed(args.seed)
    seasons = sorted(set(args.season))
    generator = torch.Generator()
    generator.manual_seed(args.seed)
    
    if len(seasons) < 3:
        parser.error("Provide at least three seasons for train, validation, and test.")

    print(f"Training model for position: {args.position}")
    print(f"Training model for seasons: {seasons}")

    train_seasons = seasons[:-2]
    validation_seasons = [seasons[-2]]
    test_seasons = [seasons[-1]]
    
    print(f"Training seasons: {train_seasons}")
    print(f"Validation seasons: {validation_seasons}")
    print(f"Test seasons: {test_seasons}")

    nfl_data = NFLData(season=args.season)
    
    nfl_data.load_data()
    
    player_data = nfl_data.get_player_stats()
    defense_data = nfl_data.get_defense_stats()
    
    print(f"Player data shape: {player_data.shape}")
    print(f"Defense data shape: {defense_data.shape}")
    
    positions = (
        ["QB", "RB", "WR", "TE"]
        if args.position == "ALL"
        else [args.position]
    )
    
    for position in positions:
        feature_cols = FEATURES_BY_POSITION[position]
        position_config = POSITION_CONFIGS[position]
        
        train_dataset = PlayerSequenceDataset(
            player_data,
            defense_data,
            feature_cols=feature_cols,
            sequence_length=5,
            seasons=train_seasons,
            position=position
        )
        
        validation_dataset = PlayerSequenceDataset(
            player_data,
            defense_data,
            feature_cols=feature_cols,
            sequence_length=5,
            seasons=validation_seasons,
            position=position,
            scaler=train_dataset.scaler,
            matchup_scaler=train_dataset.matchup_scaler,
        )
        
        test_dataset = PlayerSequenceDataset(
            player_data,
            defense_data,
            feature_cols=feature_cols,
            sequence_length=5,
            seasons=test_seasons,
            position=position,
            scaler=train_dataset.scaler,
            matchup_scaler=train_dataset.matchup_scaler,
        )
        
        print(f"{position} samples:")
        print(f"  Train: {len(train_dataset)}")
        print(f"  Validation: {len(validation_dataset)}")
        print(f"  Test: {len(test_dataset)}")
        
        train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, generator=generator)
        validation_loader = torch.utils.data.DataLoader(validation_dataset, batch_size=args.batch_size, shuffle=False)
        test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)
        
        sequence, matchup, target = next(iter(train_loader))

        print(f"Sequence: {sequence.shape}")
        print(f"Matchup: {matchup.shape}")
        print(f"Target: {target.shape}")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        model = PyTorchProjectionModel(
            input_size=len(train_dataset.feature_cols),
            matchup_size=len(train_dataset.matchup_feature_cols),
            **position_config,
        ).to(device)
        
        sequence = sequence.to(device)
        matchup = matchup.to(device)
        target = target.to(device)

        with torch.no_grad():
            predictions = model(sequence, matchup)
        
        assert predictions.shape == target.shape
        
        print(f"Device: {device}")
        print(f"Predictions: {predictions.shape}")
        
        loss_fn = torch.nn.L1Loss()
        optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)

        best_validation_mae = float("inf")
        best_state_dict = None
        best_epoch = 0
        epochs_without_improvement = 0
        
        for epoch in range(1, args.num_epochs + 1):
            train_mae = train_one_epoch(model, train_loader, loss_fn, optimizer, device)
            validation_mae = evaluate(model, validation_loader, loss_fn, device)
            
            print(f"Epoch {epoch}: Train MAE: {train_mae:.4f}, Validation MAE: {validation_mae:.4f}")
            
            if validation_mae < best_validation_mae:
                best_validation_mae = validation_mae
                best_state_dict = copy.deepcopy(model.state_dict())
                best_epoch = epoch
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1
            
            if epochs_without_improvement >= args.patience:
                print(f"Early stopping triggered after {epochs_without_improvement} epochs without improvement.")
                break
        
        if best_state_dict is None:
            raise RuntimeError("Training did not produce a valid checkpoint.")

        model.load_state_dict(best_state_dict)

        print(
            f"Best epoch: {best_epoch}, "
            f"Validation MAE: {best_validation_mae:.4f}"
        )
        
        test_mae = evaluate(model, test_loader, loss_fn, device)
        baselines = calculate_baselines(test_dataset)
        
        print(f"Last-game baseline MAE: {baselines['last_game_mae']:.4f}")
        print(f"Rolling mean baseline MAE: {baselines['rolling_mean_mae']:.4f}")

        print(
            f"{position} final results | "
            f"Best epoch: {best_epoch} | "
            f"Validation MAE: {best_validation_mae:.4f} | "
            f"Test MAE: {test_mae:.4f}"
        )
        
        checkpoint = {
            "format_version": 2,
            "model_state_dict": {
                name: value.cpu()
                for name, value in model.state_dict().items()
            },
            "sequence_scaler": scaler_state(train_dataset.scaler),
            "matchup_scaler": scaler_state(train_dataset.matchup_scaler),
            "feature_cols": train_dataset.feature_cols,
            "matchup_feature_cols": train_dataset.matchup_feature_cols,
            "sequence_length": train_dataset.sequence_length,
            "position": position,
            "version": args.version,
            "model_config": position_config,
            "train_seasons": train_seasons,
            "validation_seasons": validation_seasons,
            "test_seasons": test_seasons,
            "best_epoch": best_epoch,
            "validation_mae": best_validation_mae,
            "test_mae": test_mae,
            "seed": args.seed,
            "last_game_baseline_mae": baselines["last_game_mae"],
            "rolling_mean_baseline_mae": baselines["rolling_mean_mae"],
        }
        
        backend_dir = Path(__file__).resolve().parents[2]
        model_dir = backend_dir / "models" / "pytorch"
        model_dir.mkdir(parents=True, exist_ok=True)
        
        checkpoint_path = (
            model_dir / f"{position}_model_v{args.version}.pth"
        )

        torch.save(checkpoint, checkpoint_path)
        print(f"Saved checkpoint: {checkpoint_path}")

if __name__ == "__main__":
    main()