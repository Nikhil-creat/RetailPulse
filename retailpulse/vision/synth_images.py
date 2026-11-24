"""Synthetic 'product tile' images: one icon per product category, with jitter, colour and noise.

Real deployments would train on real product photos; this keeps the repo self-contained,
legally clean and reproducible while exercising the full image-classification pipeline.
"""
from __future__ import annotations

import colorsys
import math

import numpy as np
from PIL import Image, ImageDraw

CLASSES = ["Electronics", "Fashion", "Grocery", "Home", "Beauty", "Sports"]
SIZE = 32
_CANVAS = 64


def _tf(points, angle, scale, ox, oy):
    c = _CANVAS / 2
    ca, sa = math.cos(angle), math.sin(angle)
    out = []
    for x, y in points:
        x, y = (x - c) * scale, (y - c) * scale
        out.append((c + x * ca - y * sa + ox, c + x * sa + y * ca + oy))
    return out


def _draw(draw: ImageDraw.ImageDraw, cls: int, fg, accent, angle, scale, ox, oy):
    def T(pts):
        return _tf(pts, angle, scale, ox, oy)

    if cls == 0:  # phone
        draw.polygon(T([(22, 8), (42, 8), (42, 56), (22, 56)]), fill=fg)
        draw.polygon(T([(25, 14), (39, 14), (39, 48), (25, 48)]), fill=accent)
    elif cls == 1:  # t-shirt
        draw.polygon(T([(8, 20), (24, 8), (30, 12), (34, 12), (40, 8), (56, 20), (48, 32), (42, 28),
                        (42, 56), (22, 56), (22, 28), (16, 32)]), fill=fg)
    elif cls == 2:  # can
        draw.polygon(T([(18, 16), (46, 16), (46, 52), (18, 52)]), fill=fg)
        draw.polygon(T([(18, 16), (46, 16), (41, 9), (23, 9)]), fill=accent)
        draw.polygon(T([(18, 28), (46, 28), (46, 40), (18, 40)]), fill=accent)
    elif cls == 3:  # house
        draw.polygon(T([(8, 30), (32, 8), (56, 30)]), fill=accent)
        draw.polygon(T([(14, 30), (50, 30), (50, 56), (14, 56)]), fill=fg)
        draw.polygon(T([(28, 42), (36, 42), (36, 56), (28, 56)]), fill=accent)
    elif cls == 4:  # lipstick
        draw.polygon(T([(24, 36), (40, 36), (40, 56), (24, 56)]), fill=fg)
        draw.polygon(T([(27, 22), (37, 22), (37, 36), (27, 36)]), fill=accent)
        draw.polygon(T([(27, 22), (37, 22), (37, 12), (32, 7), (27, 13)]), fill=fg)
    else:  # ball
        cx, cy, r = 32 + ox, 32 + oy, 22 * scale
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fg)
        draw.line([(cx - r, cy), (cx + r, cy)], fill=accent, width=2)
        draw.line([(cx, cy - r), (cx, cy + r)], fill=accent, width=2)
        draw.arc([cx - r * 0.6, cy - r, cx + r * 0.6, cy + r], 0, 360, fill=accent, width=2)


def _rgb(h, s, v):
    return tuple(int(255 * c) for c in colorsys.hsv_to_rgb(h, s, v))


def draw_tile(cls: int, rng: np.random.Generator) -> np.ndarray:
    bg = _rgb(rng.uniform(0, 1), rng.uniform(0.0, 0.15), rng.uniform(0.85, 1.0))
    h = rng.uniform(0, 1)
    fg = _rgb(h, rng.uniform(0.5, 0.9), rng.uniform(0.35, 0.7))
    accent = _rgb((h + 0.5) % 1.0, rng.uniform(0.2, 0.6), rng.uniform(0.8, 1.0))
    img = Image.new("RGB", (_CANVAS, _CANVAS), bg)
    _draw(ImageDraw.Draw(img), cls, fg, accent, rng.uniform(-0.25, 0.25), rng.uniform(0.7, 0.95),
          rng.uniform(-4, 4), rng.uniform(-4, 4))
    img = img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    arr = np.asarray(img).astype(np.float32) + rng.normal(0, 6, (SIZE, SIZE, 3))
    return np.clip(arr, 0, 255).astype(np.uint8)


def make_dataset(n_per_class: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    X = np.stack([draw_tile(c, rng) for c in range(len(CLASSES)) for _ in range(n_per_class)])
    y = np.repeat(np.arange(len(CLASSES)), n_per_class)
    order = rng.permutation(len(y))
    return X[order], y[order]
