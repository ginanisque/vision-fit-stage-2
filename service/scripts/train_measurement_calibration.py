#!/usr/bin/env python3
"""Fit a versioned VF-3 correction profile from professionally measured cases.

CSV columns are ``subject_id`` plus ``raw_<key>_mm`` and ``tape_<key>_mm`` for
any registry key. The output is deliberately small and auditable: one linear
factor/bias pair and held-in-sample MAE per measurement. Replace this baseline
with cross-validated models only when the dataset is large enough.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.circumference import CORE_KEYS


def fit(rows: list[dict[str, str]], minimum_samples: int = 5) -> dict:
    factors: dict[str, float] = {}
    biases: dict[str, float] = {}
    errors: dict[str, float] = {}
    counts: dict[str, int] = {}
    for key in CORE_KEYS:
        pairs = []
        for row in rows:
            try:
                raw = float(row.get(f"raw_{key}_mm", ""))
                tape = float(row.get(f"tape_{key}_mm", ""))
            except (TypeError, ValueError):
                continue
            if np.isfinite(raw) and np.isfinite(tape) and raw > 0 and tape > 0:
                pairs.append((raw, tape))
        if len(pairs) < minimum_samples:
            continue
        x = np.asarray([pair[0] for pair in pairs], dtype=np.float64)
        y = np.asarray([pair[1] for pair in pairs], dtype=np.float64)
        design = np.column_stack((x, np.ones_like(x)))
        factor, bias = np.linalg.lstsq(design, y, rcond=None)[0]
        predicted = x * factor + bias
        factors[key] = round(float(factor), 8)
        biases[key] = round(float(bias), 3)
        errors[key] = round(float(np.mean(np.abs(predicted - y))), 3)
        counts[key] = len(pairs)
    if not factors:
        raise ValueError(f"No measurement has at least {minimum_samples} valid labelled cases")
    return {
        "version": "vf3-calibration-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "factor": factors, "biasMm": biases, "maeMm": errors, "sampleCount": counts,
        "trainingPolicy": "Professional tape labels; body measurements without garment ease.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--minimum-samples", type=int, default=5)
    args = parser.parse_args()
    with args.input_csv.open(newline="", encoding="utf-8") as source:
        profile = fit(list(csv.DictReader(source)), args.minimum_samples)
    args.output_json.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
