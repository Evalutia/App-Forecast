# python-worker/ml_nn/train_from_mysql.py
"""
Entrenar N-BEATS cargando series desde MySQL (evalutia).
Uso:
  py -3 python-worker/ml_nn/train_from_mysql.py --epochs 20 --input-length 8 --output-length 2 --batch-size 64 --device cpu
"""
import argparse, os
import torch
from torch.utils.data import TensorDataset, DataLoader
from torch.utils.tensorboard import SummaryWriter
import numpy as np
import pandas as pd
from ml_nn.data_loader import prepare_dataset
from ml_nn.model import make_model
from ioworker.db import DBConfig, get_engine
from ioworker.data import load_series_by_sku_mysql

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


def load_series_from_mysql(host, port, db, user, password, freq_rule='Q', top_n=200):
    engine = get_engine(DBConfig(host=host, port=port, db=db, user=user, password=password))
    return load_series_by_sku_mysql(engine=engine, table="ventas_historicas", schema=None, freq=freq_rule, only_skus=None, top_n=top_n)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-length", type=int, default=8)
    parser.add_argument("--output-length", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--mysql-host", type=str, default="localhost")
    parser.add_argument("--mysql-port", type=int, default=3306)
    parser.add_argument("--mysql-db", type=str, default="evalutia")
    parser.add_argument("--mysql-user", type=str, default="evalutia")
    parser.add_argument("--mysql-pass", type=str, default="evalutia")
    parser.add_argument("--top-n", type=int, default=200)
    args = parser.parse_args()

    os.makedirs("checkpoints", exist_ok=True)
    writer = SummaryWriter()

    series_dict = load_series_from_mysql(host=args.mysql_host, port=args.mysql_port, db=args.mysql_db, user=args.mysql_user, password=args.mysql_pass, freq_rule='Q', top_n=args.top_n)
    if not series_dict:
        raise RuntimeError("No se obtuvieron series desde MySQL. Revisa conexión o tabla.")

    X, y, skus = prepare_dataset(series_dict, input_length=args.input_length, output_length=args.output_length, rule='Q')
    if X is None:
        raise RuntimeError("No hay suficientes datos para formar ventanas. Revisa input_length/output_length o los datos en DB.")

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
