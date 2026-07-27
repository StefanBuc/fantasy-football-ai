from pathlib import Path
import json
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import torch
import torch.nn as nn

BASE_DIR = Path(__file__).resolve().parent.parent.parent

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
        
        
        