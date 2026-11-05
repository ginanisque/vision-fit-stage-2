"""Real image-quality checks for exposure and blur.

This is the only quality signal implemented in VF-0. It intentionally covers
exposure and blur — NOT posture, framing, waist-cord placement or measurement
suitability, which are later milestones.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import DEFAULT_THRESHOLDS, QualityThresholds


@dataclass(frozen=True)
class ExposureResult:
    status: str  # 'pass' | 'fail'
    luma_mean: float
    dark_clip_fraction: float
    bright_clip_fraction: float


@dataclass(frozen=True)
class BlurResult:
    status: str  # 'pass' | 'fail'
    laplacian_variance: float


@dataclass(frozen=True)
class QualityCheckResult:
    exposure: ExposureResult
    blur: BlurResult
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.exposure.status == "pass" and self.blur.status == "pass"


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def evaluate_exposure(gray: np.ndarray, thresholds: QualityThresholds) -> ExposureResult:
    total = int(gray.size)
    luma_mean = float(cv2.mean(gray)[0])
    dark_clip_fraction = (
        float(np.count_nonzero(gray <= thresholds.clip_dark_value)) / total if total else 0.0
    )
    bright_clip_fraction = (
        float(np.count_nonzero(gray >= thresholds.clip_bright_value)) / total if total else 0.0
    )

    underexposed = luma_mean < thresholds.luma_mean_min or dark_clip_fraction > thresholds.clip_fraction_max
    overexposed = luma_mean > thresholds.luma_mean_max or bright_clip_fraction > thresholds.clip_fraction_max
    status = "fail" if (underexposed or overexposed) else "pass"
    return ExposureResult(status, luma_mean, dark_clip_fraction, bright_clip_fraction)


def evaluate_blur(gray: np.ndarray, thresholds: QualityThresholds) -> BlurResult:
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = float(laplacian.var())
    status = "pass" if variance >= thresholds.laplacian_variance_min else "fail"
    return BlurResult(status, variance)


def evaluate_quality(
    image: np.ndarray,
    thresholds: QualityThresholds = DEFAULT_THRESHOLDS,
    view: str = "unknown",
) -> QualityCheckResult:
    gray = _to_gray(image)
    exposure = evaluate_exposure(gray, thresholds)
    blur = evaluate_blur(gray, thresholds)

    reasons: list[str] = []
    if exposure.status == "fail":
        if exposure.luma_mean < thresholds.luma_mean_min:
            reasons.append(
                f"underexposed: mean luminance {exposure.luma_mean:.1f} is below the provisional "
                f"minimum {thresholds.luma_mean_min:.1f}"
            )
        if exposure.luma_mean > thresholds.luma_mean_max:
            reasons.append(
                f"overexposed: mean luminance {exposure.luma_mean:.1f} is above the provisional "
                f"maximum {thresholds.luma_mean_max:.1f}"
            )
        if exposure.dark_clip_fraction > thresholds.clip_fraction_max:
            reasons.append(
                f"underexposed: {exposure.dark_clip_fraction:.1%} of pixels are shadow-clipped "
                f"(provisional maximum {thresholds.clip_fraction_max:.1%})"
            )
        if exposure.bright_clip_fraction > thresholds.clip_fraction_max:
            reasons.append(
                f"overexposed: {exposure.bright_clip_fraction:.1%} of pixels are highlight-clipped "
                f"(provisional maximum {thresholds.clip_fraction_max:.1%})"
            )
    if blur.status == "fail":
        reasons.append(
            f"blurry: Laplacian variance {blur.laplacian_variance:.1f} is below the provisional "
            f"minimum {thresholds.laplacian_variance_min:.1f}"
        )

    return QualityCheckResult(exposure=exposure, blur=blur, reasons=tuple(reasons))
