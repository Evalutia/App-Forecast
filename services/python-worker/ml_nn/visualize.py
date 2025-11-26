"""
visualize.py
Funciones para generar gráficos: loss ya lo hace TensorBoard, pero aquí hacemos
predicción vs real para un SKU y guardamos PNG.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def plot_pred_vs_true(dates, true_vals, pred_vals, out_path):
    plt.figure(figsize=(8,4))
    plt.plot(dates, true_vals, label="real", marker='o')
    plt.plot(dates, pred_vals, label="pred", marker='x')
    plt.legend()
    plt.xlabel("fecha")
    plt.ylabel("cantidad")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
