"""
train.py
Script de entrenamiento sencillo para N-BEATS.
Guarda el mejor checkpoint en checkpoints/best_model.pth
Usa TensorBoard para logs en runs/
"""

import argparse
import os
import torch
from torch.utils.data import TensorDataset, DataLoader
from torch.utils.tensorboard import SummaryWriter
import numpy as np
from ml_nn.data_loader import prepare_dataset
from ml_nn.model import make_model
from ml_nn.metrics import mae
import pandas as pd

def train_loop(model, loader, opt, device):
    model.train()
    total_loss = 0.0
    for xb, yb in loader:
        xb = xb.to(device)
        yb = yb.to(device)
        pred = model(xb)
        loss = torch.nn.functional.l1_loss(pred, yb)
        opt.zero_grad()
        loss.backward()
        opt.step()
        total_loss += loss.item() * xb.size(0)
    return total_loss / len(loader.dataset)

def val_loop(model, loader, device):
    model.eval()
    total = 0.0
    with torch.no_grad():
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            pred = model(xb)
            total += torch.nn.functional.l1_loss(pred, yb).item() * xb.size(0)
    return total / len(loader.dataset)

def load_series_csv(path, freq_rule='Q'):
    # csv simple: columns: sku, date, qty
    df = pd.read_csv(path, parse_dates=['date'])
    out = {}
    for sku, g in df.groupby('sku'):
        s = pd.Series(data=g['qty'].values, index=g['date'])
        out[sku] = s
    return out

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=str, required=True, help="CSV con columnas sku,date,qty")
    parser.add_argument("--input-length", type=int, default=8)
    parser.add_argument("--output-length", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--device", type=str, default="cpu")
    args = parser.parse_args()

    os.makedirs("checkpoints", exist_ok=True)
    writer = SummaryWriter()

    # cargar
    series = load_series_csv(args.input_file)
    X, y, skus = prepare_dataset(series, input_length=args.input_length, output_length=args.output_length, rule='Q')
    if X is None:
        raise RuntimeError("No hay datos suficientes")
    # split simple: 80/20
    n = X.shape[0]
    idx = int(n * 0.8)
    X_train, X_val = X[:idx], X[idx:]
    y_train, y_val = y[:idx], y[idx:]

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    val_ds = TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val))
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    device = torch.device(args.device if torch.cuda.is_available() and args.device != 'cpu' else 'cpu')
    model = make_model(input_length=args.input_length, output_length=args.output_length, device=device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    best_val = float('inf')
    for epoch in range(1, args.epochs + 1):
        tr_loss = train_loop(model, train_loader, opt, device)
        v_loss = val_loop(model, val_loader, device)
        writer.add_scalar("loss/train", tr_loss, epoch)
        writer.add_scalar("loss/val", v_loss, epoch)
        print(f"Epoch {epoch}: train_loss={tr_loss:.6f}, val_loss={v_loss:.6f}")
        if v_loss < best_val:
            best_val = v_loss
            torch.save({"model_state": model.state_dict(), "input_length": args.input_length, "output_length": args.output_length}, "checkpoints/best_model.pth")
            print("  -> checkpoint guardado")
    writer.close()

if __name__ == "__main__":
    main()
