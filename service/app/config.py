"""Provisional quality thresholds for VisionFit VF-0.

These are starting values only. They have NOT been domain-approved and must be
re-evaluated against real captures before any measurement work depends on them.
Passing these checks means only that exposure and blur are acceptable — it does
NOT verify posture, framing, waist-cord placement or measurement suitability.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityThresholds:
    # Exposure — evaluated on the grayscale image (0-255).
    luma_mean_min: float = 45.0  # mean below this -> underexposed
    luma_mean_max: float = 210.0  # mean above this -> overexposed
    clip_dark_value: int = 8  # pixels <= this count as shadow-clipped
    clip_bright_value: int = 247  # pixels >= this count as highlight-clipped
    clip_fraction_max: float = 0.05  # max allowed clipped fraction at either end

    # Blur — variance of the Laplacian of the grayscale image.
    laplacian_variance_min: float = 100.0  # below this -> blurry

    def as_dict(self) -> dict:
        return {
            "lumaMeanMin": self.luma_mean_min,
            "lumaMeanMax": self.luma_mean_max,
            "clipDarkValue": self.clip_dark_value,
            "clipBrightValue": self.clip_bright_value,
            "clipFractionMax": self.clip_fraction_max,
            "laplacianVarianceMin": self.laplacian_variance_min,
        }


DEFAULT_THRESHOLDS = QualityThresholds()
