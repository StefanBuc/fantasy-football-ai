import argparse
import copy
import random
from pathlib import Path

import numpy as np
import torch

from app.config.model_config import (
    DST_FEATURE_COLS,
    K_FEATURE_COLS,
    POSITION_CONFIGS,
    SPECIAL_TEAMS_MATCHUP_SOURCES,
)
from app.services.pytorch_projection_model import (
    PyTorchProjectionModel,
)
from app.services.special_teams_data import (
    load_special_teams_weekly,
)
from app.services.special_teams_sequence_dataset import (
    SpecialTeamsSequenceDataset,
)


FEATURES_BY_POSITION = {
    "K": K_FEATURE_COLS,
    "DST": DST_FEATURE_COLS,
}


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p",
        "--position",
        type=str.upper,
        choices=["K", "DST", "ALL"],
        default="ALL",
    )
    parser.add_argument(
        "-s",
        "--season",
        type=int,
        nargs="+",
        default=[2020, 2021, 2022, 2023, 2024],
    )
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--learning_rate", type=float, default=0.001)
    parser.add_argument("--num_epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=7)
    parser.add_argument("--version", type=int, default=1)
    return parser.parse_args()


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def run_epoch(model, loader, loss_fn, device, optimizer=None):
    is_training = optimizer is not None
    model.train(is_training)
    total_loss = 0.0
    total_examples = 0

    context = torch.enable_grad() if is_training else torch.inference_mode()
    with context:
        for sequence, matchup, target in loader:
            sequence = sequence.to(device)
            matchup = matchup.to(device)
            target = target.to(device)

            if optimizer is not None:
                optimizer.zero_grad()

            predictions = model(sequence, matchup)
            loss = loss_fn(predictions, target)

            if optimizer is not None:
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

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
        "n_samples_seen": int(np.asarray(scaler.n_samples_seen_).max()),
    }


def calculate_baselines(dataset):
    scaled = dataset.sequences.numpy()
    samples, sequence_length, features = scaled.shape
    unscaled = dataset.scaler.inverse_transform(
        scaled.reshape(-1, features)
    ).reshape(samples, sequence_length, features)
    points_index = dataset.feature_cols.index("fantasy_points")
    targets = dataset.targets.numpy()

    return {
        "last_game_mae": float(
            np.mean(np.abs(targets - unscaled[:, -1, points_index]))
        ),
        "rolling_mean_mae": float(
            np.mean(
                np.abs(
                    targets
                    - unscaled[:, :, points_index].mean(axis=1)
                )
            )
        ),
    }


def main():
    args = parse_arguments()
    set_seed(args.seed)
    seasons = sorted(set(args.season))

    if len(seasons) < 3:
        raise ValueError(
            "Provide at least three seasons for train, validation, and test."
        )

    train_seasons = seasons[:-2]
    validation_seasons = [seasons[-2]]
    test_seasons = [seasons[-1]]
    validation_context = [train_seasons[-1], *validation_seasons]
    test_context = [validation_seasons[-1], *test_seasons]

    print(f"Loading play-by-play for seasons: {seasons}")
    data_by_position = load_special_teams_weekly(seasons)
    positions = (
        ["K", "DST"]
        if args.position == "ALL"
        else [args.position]
    )
    generator = torch.Generator().manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    for position in positions:
        weekly = data_by_position[position]
        feature_cols = FEATURES_BY_POSITION[position]
        matchup_sources = SPECIAL_TEAMS_MATCHUP_SOURCES[position]

        train_dataset = SpecialTeamsSequenceDataset(
            weekly_df=weekly,
            feature_cols=feature_cols,
            matchup_sources=matchup_sources,
            seasons=train_seasons,
            target_seasons=train_seasons,
        )
        validation_dataset = SpecialTeamsSequenceDataset(
            weekly_df=weekly,
            feature_cols=feature_cols,
            matchup_sources=matchup_sources,
            seasons=validation_context,
            target_seasons=validation_seasons,
            scaler=train_dataset.scaler,
            matchup_scaler=train_dataset.matchup_scaler,
        )
        test_dataset = SpecialTeamsSequenceDataset(
            weekly_df=weekly,
            feature_cols=feature_cols,
            matchup_sources=matchup_sources,
            seasons=test_context,
            target_seasons=test_seasons,
            scaler=train_dataset.scaler,
            matchup_scaler=train_dataset.matchup_scaler,
        )

        print(f"\n{position} samples:")
        print(f"  Train: {len(train_dataset)}")
        print(f"  Validation: {len(validation_dataset)}")
        print(f"  Test: {len(test_dataset)}")
        print(f"Device: {device}")

        train_loader = torch.utils.data.DataLoader(
            train_dataset,
            batch_size=args.batch_size,
            shuffle=True,
            generator=generator,
        )
        validation_loader = torch.utils.data.DataLoader(
            validation_dataset,
            batch_size=args.batch_size,
        )
        test_loader = torch.utils.data.DataLoader(
            test_dataset,
            batch_size=args.batch_size,
        )

        model_config = POSITION_CONFIGS[position]
        model = PyTorchProjectionModel(
            input_size=len(feature_cols),
            matchup_size=len(matchup_sources),
            **model_config,
        ).to(device)
        loss_fn = torch.nn.L1Loss()
        optimizer = torch.optim.Adam(
            model.parameters(),
            lr=args.learning_rate,
        )

        best_validation_mae = float("inf")
        best_state_dict = None
        best_epoch = 0
        epochs_without_improvement = 0

        for epoch in range(1, args.num_epochs + 1):
            train_mae = run_epoch(
                model, train_loader, loss_fn, device, optimizer
            )
            validation_mae = run_epoch(
                model, validation_loader, loss_fn, device
            )
            print(
                f"Epoch {epoch}: Train MAE: {train_mae:.4f}, "
                f"Validation MAE: {validation_mae:.4f}"
            )

            if validation_mae < best_validation_mae:
                best_validation_mae = validation_mae
                best_state_dict = copy.deepcopy(model.state_dict())
                best_epoch = epoch
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1

            if epochs_without_improvement >= args.patience:
                print("Early stopping triggered.")
                break

        if best_state_dict is None:
            raise RuntimeError("Training did not produce a checkpoint.")

        model.load_state_dict(best_state_dict)
        test_mae = run_epoch(model, test_loader, loss_fn, device)
        baselines = calculate_baselines(test_dataset)

        print(f"Best epoch: {best_epoch}")
        print(f"Validation MAE: {best_validation_mae:.4f}")
        print(f"Test MAE: {test_mae:.4f}")
        print(
            f"Last-game baseline MAE: "
            f"{baselines['last_game_mae']:.4f}"
        )
        print(
            f"Rolling mean baseline MAE: "
            f"{baselines['rolling_mean_mae']:.4f}"
        )

        checkpoint = {
            "format_version": 2,
            "model_state_dict": {
                name: value.cpu()
                for name, value in model.state_dict().items()
            },
            "sequence_scaler": scaler_state(train_dataset.scaler),
            "matchup_scaler": scaler_state(train_dataset.matchup_scaler),
            "feature_cols": feature_cols,
            "matchup_feature_cols": list(matchup_sources),
            "matchup_sources": matchup_sources,
            "sequence_length": train_dataset.sequence_length,
            "position": position,
            "version": args.version,
            "model_config": model_config,
            "train_seasons": train_seasons,
            "validation_seasons": validation_seasons,
            "test_seasons": test_seasons,
            "best_epoch": best_epoch,
            "validation_mae": best_validation_mae,
            "test_mae": test_mae,
            "seed": args.seed,
            **baselines,
        }

        model_dir = (
            Path(__file__).resolve().parents[2]
            / "models"
            / "pytorch"
        )
        model_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = (
            model_dir / f"{position}_model_v{args.version}.pth"
        )
        torch.save(checkpoint, checkpoint_path)
        print(f"Saved checkpoint: {checkpoint_path}")


if __name__ == "__main__":
    main()
