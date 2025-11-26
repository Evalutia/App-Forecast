"""
model.py
Implementación simplificada de N-BEATS en PyTorch.
Input: tensor (batch, input_length)
Output: tensor (batch, output_length)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

class NBeatsBlock(nn.Module):
    def __init__(self, input_size, theta_size, hidden_size=128, n_layers=2):
        super().__init__()
        layers = []
        last = input_size
        for _ in range(n_layers):
            layers.append(nn.Linear(last, hidden_size))
            layers.append(nn.ReLU())
            last = hidden_size
        self.net = nn.Sequential(*layers)
        self.theta = nn.Linear(last, theta_size)

    def forward(self, x):
        # x: (batch, input_size)
        x = self.net(x)
        t = self.theta(x)
        return t

class NBeats(nn.Module):
    def __init__(self, input_length=8, output_length=2, stack_types=('trend','seasonality'),
                 hidden_size=128, n_layers=2, n_blocks=3):
        super().__init__()
        self.input_length = input_length
        self.output_length = output_length
        self.blocks = nn.ModuleList()
        for _ in range(n_blocks):
            # For simplicity produce direct forecast (no backcast)
            block = NBeatsBlock(input_length, theta_size=output_length, hidden_size=hidden_size, n_layers=n_layers)
            self.blocks.append(block)

    def forward(self, x):
        # x: (batch, input_length)
        # sum predictions from blocks
        preds = 0
        for block in self.blocks:
            preds = preds + block(x)
        return preds  # (batch, output_length)

def make_model(input_length=8, output_length=2, device='cpu'):
    model = NBeats(input_length=input_length, output_length=output_length)
    return model.to(device)
