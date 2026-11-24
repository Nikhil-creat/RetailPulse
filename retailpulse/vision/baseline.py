"""Dependency-light image classifier (scikit-learn MLP) with SAFE weight persistence.

Weights are saved as plain .npz arrays (no pickle) and inference is a tiny NumPy forward
pass, so loading a model file can never execute code. Used when PyTorch isn't installed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

from .synth_images import CLASSES, make_dataset

WEIGHTS_FILE = "vision_mlp.npz"


def to_features(X: np.ndarray) -> np.ndarray:
    gray = X.astype(np.float32).mean(axis=-1) / 255.0
    return gray.reshape(len(X), -1)


class NumpyMLP:
    def __init__(self, weights: list[np.ndarray], biases: list[np.ndarray]):
        self.W, self.b = weights, biases

    @classmethod
    def load(cls, path: Path) -> "NumpyMLP":
        data = np.load(path, allow_pickle=False)
        n = len([k for k in data.files if k.startswith("W")])
        return cls([data[f"W{i}"] for i in range(n)], [data[f"b{i}"] for i in range(n)])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        a = to_features(X)
        for W, b in zip(self.W[:-1], self.b[:-1]):
            a = np.maximum(a @ W + b, 0.0)
        z = a @ self.W[-1] + self.b[-1]
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)


def train_baseline(models_dir: Path, n_per_class: int = 300, seed: int = 0) -> dict:
    X, y = make_dataset(n_per_class, seed)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=seed)
    clf = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=80, early_stopping=True, random_state=seed)
    clf.fit(to_features(Xtr), ytr)
    pred = clf.predict(to_features(Xte))
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    arrays = {f"W{i}": w for i, w in enumerate(clf.coefs_)} | {f"b{i}": b for i, b in enumerate(clf.intercepts_)}
    np.savez(models_dir / WEIGHTS_FILE, **arrays)
    return {
        "backend": "numpy-mlp", "classes": CLASSES, "train_images": int(len(ytr)), "test_images": int(len(yte)),
        "accuracy": round(float(accuracy_score(yte, pred)), 4),
        "confusion_matrix": confusion_matrix(yte, pred).tolist(),
    }
