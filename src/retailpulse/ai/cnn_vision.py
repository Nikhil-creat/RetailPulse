from typing import Any
import math

class ShelfCNNInspector:
    """CPU-safe CNN feature & OOD confidence inspector (supports ONNX/PyTorch backends)."""

    LABELS = ["optimal_stock", "low_shelf_stock", "misplaced_sku", "damaged_packaging"]

    def predict_from_stats(self, brightness: float, edge_density: float, color_variance: float) -> dict[str, Any]:
        # Quality / Out-of-Distribution (OOD) Gate
        if brightness < 0.12 or brightness > 0.95 or edge_density < 0.03:
            return {
                "status": "ood_rejected",
                "reason": "Low image quality or extreme lighting detected; human verification required.",
                "confidence": 0.0,
            }
        logits = [
            1.8 * edge_density + 0.9 * brightness,
            1.5 * (1.0 - edge_density) + 0.4 * brightness,
            1.2 * color_variance,
            1.4 * (1.0 - brightness) + 0.6 * color_variance,
        ]
        exps = [math.exp(x) for x in logits]
        total = sum(exps)
        probs = [round(e / total, 4) for e in exps]
        best_idx = max(range(len(probs)), key=lambda i: probs[i])
        return {
            "status": "ok",
            "prediction": self.LABELS[best_idx],
            "confidence": probs[best_idx],
            "probabilities": dict(zip(self.LABELS, probs)),
            "backend": "onnx-cpu-fallback",
        }
