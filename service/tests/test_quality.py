"""Unit tests for the exposure/blur quality checks.

Synthetic fixtures let us assert the decision flips correctly: a well-exposed,
sharp image passes, while dark / bright / blurred images are rejected.
"""
import cv2
import numpy as np

from app.config import DEFAULT_THRESHOLDS
from app.quality import evaluate_quality


def _structured_image(mean: float = 128.0, amplitude: float = 60.0, seed: int = 0) -> np.ndarray:
    """A sharp, well-exposed synthetic image with strong edges and a little noise."""
    height, width = 300, 400
    yy, xx = np.mgrid[0:height, 0:width]
    rng = np.random.default_rng(seed)
    image = mean + amplitude * np.sin(xx / 12.0) * np.sin(yy / 12.0)
    image = image + rng.normal(0, 8, size=(height, width))
    return np.clip(image, 0, 255).astype(np.uint8)


def test_sharp_well_exposed_image_passes() -> None:
    result = evaluate_quality(_structured_image(), DEFAULT_THRESHOLDS, "front")
    assert result.passed is True
    assert result.exposure.status == "pass"
    assert result.blur.status == "pass"
    assert result.reasons == ()


def test_blurry_image_fails_blur_check() -> None:
    blurred = cv2.GaussianBlur(_structured_image(), (0, 0), 12)
    result = evaluate_quality(blurred, DEFAULT_THRESHOLDS, "front")
    assert result.passed is False
    assert result.blur.status == "fail"
    assert any("blurry" in reason for reason in result.reasons)


def test_underexposed_image_fails_exposure_check() -> None:
    dark = (_structured_image() * 0.07).astype(np.uint8)
    result = evaluate_quality(dark, DEFAULT_THRESHOLDS, "front")
    assert result.passed is False
    assert result.exposure.status == "fail"
    assert any("underexposed" in reason for reason in result.reasons)


def test_overexposed_image_fails_exposure_check() -> None:
    bright = np.clip(_structured_image().astype(np.int32) + 220, 0, 255).astype(np.uint8)
    result = evaluate_quality(bright, DEFAULT_THRESHOLDS, "front")
    assert result.passed is False
    assert result.exposure.status == "fail"
    assert any("overexposed" in reason for reason in result.reasons)


def test_blur_variance_decreases_when_blurred() -> None:
    sharp = evaluate_quality(_structured_image(), DEFAULT_THRESHOLDS, "front")
    blurred = evaluate_quality(cv2.GaussianBlur(_structured_image(), (0, 0), 12), DEFAULT_THRESHOLDS, "front")
    assert blurred.blur.laplacian_variance < sharp.blur.laplacian_variance


def test_gray_and_color_inputs_agree() -> None:
    gray = _structured_image()
    color = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    color_result = evaluate_quality(color, DEFAULT_THRESHOLDS, "side")
    gray_result = evaluate_quality(gray, DEFAULT_THRESHOLDS, "side")
    assert abs(color_result.exposure.luma_mean - gray_result.exposure.luma_mean) < 1e-6
