from pathlib import Path

import numpy as np
import torch
import argparse

from app.services.NFL_data import NFLData
from app.services.player_sequence_dataset import (
    PlayerSequenceDataset,
    build_player_history,
    )
from app.services.pytorch_projection_model import (
    load_projection_checkpoint,
    predict_from_raw_features,
)
from app.services.defense_features import build_upcoming_defense_features
from app.services.pytorch_inference import (
    PlayerProjectionRequest,
    PyTorchProjectionService,
    predict_player_projection,
)
from torch.utils.data import DataLoader, Subset
from app.config.model_config import (
    SELECTED_PYTORCH_MODEL_VERSIONS,
)

import time

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--position",
        choices=["QB", "RB", "WR", "TE"],
        default="QB",
    )

    parser.add_argument(
        "--split",
        choices=["validation", "test"],
        default="validation",
        help="Which split to use for evaluation. Default is 'validation'.",
    )

    parser.add_argument(
        "--version",
        type=int,
        default=4,
    )
    
    parser.add_argument(
        "--benchmark-size",
        type=int,
        default=0,
    )

    return parser.parse_args()

def evaluate_dataset(
    model: torch.nn.Module,
    dataset: PlayerSequenceDataset | Subset,
    device: torch.device,
    batch_size: int = 256,
) -> float:
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
    )

    total_absolute_error = 0.0
    total_samples = 0

    model.eval()

    with torch.no_grad():
        for sequence, matchup, target in loader:
            sequence = sequence.to(device)
            matchup = matchup.to(device)
            target = target.to(device)

            predictions = model(sequence, matchup)

            total_absolute_error += (
                torch.abs(predictions - target)
                .sum()
                .item()
            )

            total_samples += target.numel()

    return total_absolute_error / total_samples

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

    if args.split == "validation":
        target_seasons = checkpoint["validation_seasons"]

        context_seasons = checkpoint.get(
            "validation_context_seasons",
            [
                checkpoint["train_seasons"][-1],
                *target_seasons,
            ],
        )
    else:
        target_seasons = checkpoint["test_seasons"]

        context_seasons = checkpoint.get(
            "test_context_seasons",
            [
                checkpoint["validation_seasons"][-1],
                *target_seasons,
            ],
        )

    target_season = target_seasons[-1]

    data = NFLData(context_seasons)
    data.load_data()
    
    player_df = data.get_player_stats()
    defense_df = data.get_defense_stats()

    dataset = PlayerSequenceDataset(
        player_df,
        defense_df,
        feature_cols=checkpoint["feature_cols"],
        sequence_length=checkpoint["sequence_length"],
        position=checkpoint["position"],
        seasons=context_seasons,
        target_seasons=target_seasons,
        scaler=sequence_scaler,
        matchup_scaler=matchup_scaler,
    )
    
    full_mae = evaluate_dataset(
        model,
        dataset,
        device,
    )

    print(
        f"{args.position} {args.split} MAE: "
        f"{full_mae:.4f} over {len(dataset)} samples"
    )
    
    early_indices = [
        index
        for index, sample in enumerate(
            dataset.sample_metadata
        )
        if sample["week"] <= 5
    ]

    later_indices = [
        index
        for index, sample in enumerate(
            dataset.sample_metadata
        )
        if sample["week"] > 5
    ]

    early_mae = evaluate_dataset(
        model,
        Subset(dataset, early_indices),
        device,
    )

    later_mae = evaluate_dataset(
        model,
        Subset(dataset, later_indices),
        device,
    )

    print(
        f"Weeks 1-5 MAE: {early_mae:.4f} "
        f"over {len(early_indices)} samples"
    )

    print(
        f"Weeks 6+ MAE: {later_mae:.4f} "
        f"over {len(later_indices)} samples"
    )

    sample_index = next(
        (
            index
            for index, sample in enumerate(
                dataset.sample_metadata
            )
            if sample["season"] == target_season
            and sample["week"] == 1
        ),
        None,
    )

    if sample_index is None:
        raise RuntimeError(
            "No week 1 cross-season sample was found."
        )

    scaled_sequence, scaled_matchup, target = dataset[
        sample_index
    ]
    metadata = dataset.sample_metadata[sample_index]
        
    with torch.no_grad():
        direct_prediction = model(
            scaled_sequence.unsqueeze(0).to(device),
            scaled_matchup.unsqueeze(0).to(device),
        ).item()

    raw_sequence = sequence_scaler.inverse_transform(
        scaled_sequence.numpy()
    )
    
    calculated_history = build_player_history(
        player_df=player_df,
        defense_df=defense_df,
        player_id=metadata["player_id"],
        season=metadata["season"],
        upcoming_week=metadata["week"],
        position=checkpoint["position"],
        feature_cols=checkpoint["feature_cols"],
        sequence_length=checkpoint["sequence_length"],
    )

    calculated_history_values = np.asarray(
        [
            [
                game[column]
                for column in checkpoint["feature_cols"]
            ]
            for game in calculated_history
        ],
        dtype=np.float32,
    )

    np.testing.assert_allclose(
        calculated_history_values,
        raw_sequence,
        rtol=1e-5,
        atol=1e-4,
    )

    print("Player history calculation passed.")

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

    history = calculated_history

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
    
    service_prediction = predict_player_projection(
        model=model,
        sequence_scaler=sequence_scaler,
        matchup_scaler=matchup_scaler,
        checkpoint=checkpoint,
        device=device,
        player_df=player_df,
        defense_df=defense_df,
        player_id=metadata["player_id"],
        season=metadata["season"],
        upcoming_week=metadata["week"],
        opponent_team=metadata["opponent_team"],
    )
    
    optimized_prediction = None

    selected_version = (
        SELECTED_PYTORCH_MODEL_VERSIONS[args.position]
    )

    if args.version == selected_version:
        optimized_service = PyTorchProjectionService(
            position=args.position,
            player_df=player_df,
            defense_df=defense_df,
            device=device,
        )

        optimized_prediction = optimized_service.predict(
            player_id=metadata["player_id"],
            season=metadata["season"],
            upcoming_week=metadata["week"],
            opponent_team=metadata["opponent_team"],
        )
        
        second_index = (
            sample_index + 1
            if sample_index + 1 < len(dataset)
            else sample_index - 1
        )

        second_metadata = dataset.sample_metadata[
            second_index
        ]

        requests = [
            PlayerProjectionRequest(
                player_id=metadata["player_id"],
                season=metadata["season"],
                upcoming_week=metadata["week"],
                opponent_team=metadata["opponent_team"],
            ),
            PlayerProjectionRequest(
                player_id=second_metadata["player_id"],
                season=second_metadata["season"],
                upcoming_week=second_metadata["week"],
                opponent_team=second_metadata[
                    "opponent_team"
                ],
            ),
        ]

        batch_predictions = optimized_service.predict_many(
            requests
        )

        second_single_prediction = optimized_service.predict(
            player_id=second_metadata["player_id"],
            season=second_metadata["season"],
            upcoming_week=second_metadata["week"],
            opponent_team=second_metadata["opponent_team"],
        )

        np.testing.assert_allclose(
            batch_predictions,
            [
                optimized_prediction,
                second_single_prediction,
            ],
            rtol=1e-5,
            atol=1e-5,
        )

        print(
            f"Batch predictions: "
            f"{batch_predictions}"
        )

        print("Batch inference passed.")

        if args.benchmark_size > 0:
            benchmark_count = min(
                args.benchmark_size,
                len(dataset.sample_metadata),
            )

            benchmark_requests = [
                PlayerProjectionRequest(
                    player_id=sample["player_id"],
                    season=sample["season"],
                    upcoming_week=sample["week"],
                    opponent_team=sample["opponent_team"],
                )
                for sample in dataset.sample_metadata[
                    :benchmark_count
                ]
            ]

            # Warm up PyTorch/CUDA before measuring.
            optimized_service.predict_many(
                benchmark_requests[:1]
            )

            if device.type == "cuda":
                torch.cuda.synchronize(device)

            optimized_service.matchup_cache.clear()

            individual_start = time.perf_counter()

            individual_predictions = [
                optimized_service.predict(
                    player_id=request.player_id,
                    season=request.season,
                    upcoming_week=request.upcoming_week,
                    opponent_team=request.opponent_team,
                )
                for request in benchmark_requests
            ]

            if device.type == "cuda":
                torch.cuda.synchronize(device)

            individual_seconds = (
                time.perf_counter() - individual_start
            )

            optimized_service.matchup_cache.clear()

            if device.type == "cuda":
                torch.cuda.synchronize(device)

            batch_start = time.perf_counter()

            benchmark_batch_predictions = (
                optimized_service.predict_many(
                    benchmark_requests
                )
            )

            if device.type == "cuda":
                torch.cuda.synchronize(device)

            batch_seconds = (
                time.perf_counter() - batch_start
            )

            np.testing.assert_allclose(
                benchmark_batch_predictions,
                individual_predictions,
                rtol=1e-4,
                atol=2e-3,
            )

            speedup = individual_seconds / batch_seconds

            print(
                f"Individual inference: "
                f"{individual_seconds:.4f}s"
            )

            print(
                f"Batch inference: {batch_seconds:.4f}s"
            )

            print(f"Batch speedup: {speedup:.2f}x")
    
        print(
            f"Optimized service prediction: "
            f"{optimized_prediction:.6f}"
        )
    
    print(f"Service prediction: {service_prediction:.6f}")
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
    
    if not np.isclose(
        direct_prediction,
        service_prediction,
        atol=1e-5,
    ):
        raise RuntimeError(
            "Inference service prediction does not match."
        )
    
    if (
        optimized_prediction is not None
        and not np.isclose(
            direct_prediction,
            optimized_prediction,
            atol=1e-5,
        )
    ):
        raise RuntimeError(
            "Optimized service prediction does not match."
        )

    if optimized_prediction is not None:
        print("Optimized inference service passed.")

    print("Inference service passed.")


if __name__ == "__main__":
    main()