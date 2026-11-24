"""Convolutional neural network (PyTorch) for product-tile category classification.

Install CPU PyTorch first:  pip install torch --index-url https://download.pytorch.org/whl/cpu
Train:                      python -m retailpulse.cli train-cnn --epochs 10
Weights are saved as a state_dict and loaded with weights_only=True (no arbitrary unpickling).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .synth_images import CLASSES, make_dataset

try:  # optional heavy dependency
    import torch
    from torch import nn
except ImportError:  # pragma: no cover
    torch = None
    nn = None

WEIGHTS_FILE = "vision_cnn.pt"


def torch_available() -> bool:
    return torch is not None


def build_model(num_classes: int = len(CLASSES)):
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),   # 16x16
        nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),  # 8x8
        nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(), nn.AdaptiveAvgPool2d(1),
        nn.Flatten(), nn.Dropout(0.2), nn.Linear(64, num_classes),
    )


def _to_tensor(X: np.ndarray):
    x = torch.from_numpy(X.astype(np.float32) / 255.0).permute(0, 3, 1, 2)
    return (x - 0.5) / 0.5


def train_cnn(models_dir: Path, epochs: int = 8, n_per_class: int = 500, seed: int = 0,
              batch_size: int = 64, lr: float = 2e-3) -> dict:
    if torch is None:
        raise RuntimeError("PyTorch is not installed. See the install line in this file's docstring.")
    torch.manual_seed(seed)
    X, y = make_dataset(n_per_class, seed)
    split = int(0.8 * len(y))
    Xtr, ytr, Xte, yte = _to_tensor(X[:split]), torch.from_numpy(y[:split]), _to_tensor(X[split:]), torch.from_numpy(y[split:])

    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss()
    history = []
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(ytr))
        total = 0.0
        for i in range(0, len(perm), batch_size):
            idx = perm[i:i + batch_size]
            opt.zero_grad()
            loss = loss_fn(model(Xtr[idx]), ytr[idx])
            loss.backward()
            opt.step()
            total += loss.item() * len(idx)
        model.eval()
        with torch.no_grad():
            acc = (model(Xte).argmax(1) == yte).float().mean().item()
        history.append({"epoch": epoch + 1, "train_loss": round(total / len(perm), 4), "test_acc": round(acc, 4)})

    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), models_dir / WEIGHTS_FILE)
    return {"backend": "torch-cnn", "classes": CLASSES, "accuracy": history[-1]["test_acc"], "history": history}


def load_cnn(path: Path):
    model = build_model()
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    model.eval()
    return model


def predict_proba(model, X: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        return torch.softmax(model(_to_tensor(X)), dim=1).numpy()
