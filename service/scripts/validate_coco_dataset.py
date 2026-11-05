#!/usr/bin/env python3
"""Reject COCO exports that cannot support honest measurement evaluation.

Checks split isolation, minimum image/subject counts, the subject manifest, and
that the keypoint class names cover the exact COCO v6 tailoring schema the
measurement runtime executes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from pathlib import Path


SPLITS = ("train", "valid", "test")

# The exact COCO v6 tailoring keypoint names the measurement runtime depends on.
# Keep in sync with docs/ROBOFLOW_MEASUREMENT_MODELS.md and the ordered point
# names in service/migrations/*_tailoring_keypoint_paths.sql. When a new
# measurement adds a new landmark, add its name here too.
EXPECTED_KEYPOINTS = (
    "nape", "center_front_neck", "side_neck_left", "side_neck_right",
    "bust_point_left", "bust_point_right", "underbust_left", "underbust_right",
    "waist_below_bust_left", "waist_below_bust_right",
    "waist_center_front", "waist_center_back", "waist_left_side", "waist_right_side",
    "hip_center_front", "hip_center_back", "hip_side_right", "hip_side_left",
    "bust_level_center_front", "bust_level_center_back",
    "bust_level_left_side", "bust_level_right_side",
    "across_chest_right", "across_chest_left",
    "shoulder_point_left", "shoulder_point_right",
    "knee_right", "knee_left", "ankle_left", "ankle_right",
    "across_back_right", "across_back_left",
    "elbow_right", "wrist_right", "elbow_left", "wrist_left",
)


def source_group(filename: str) -> str:
    name = Path(filename).stem
    name = re.sub(r"\.rf\.[0-9a-f]+$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"_(jpg|jpeg|png)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[_-]frame[_-]?\d+$", "", name, flags=re.IGNORECASE)
    return name.lower()


def keypoint_names(payload: dict) -> list[str]:
    """Return the dataset's keypoint class names (empty when none are declared).

    Roboflow keypoint exports can include an object-detection category alongside
    the keypoint category; only categories that declare a ``keypoints`` list are
    considered, so a bounding-box-only category is ignored.
    """
    names: list[str] = []
    for category in payload.get("categories", []):
        keypoints = category.get("keypoints")
        if isinstance(keypoints, list) and keypoints:
            names.extend(str(name) for name in keypoints)
    return names


def validate(archive: Path, minimum_images: int, minimum_subjects: int, manifest: Path | None) -> list[str]:
    errors: list[str] = []
    groups: dict[str, set[str]] = {}
    total = 0
    keypoints_by_split: dict[str, list[str]] = {}
    with zipfile.ZipFile(archive) as bundle:
        for split in SPLITS:
            member = f"{split}/_annotations.coco.json"
            try:
                payload = json.loads(bundle.read(member))
            except KeyError:
                errors.append(f"Missing {member}")
                continue
            images = payload.get("images", [])
            total += len(images)
            for image in images:
                groups.setdefault(source_group(str(image.get("file_name", ""))), set()).add(split)
            keypoints_by_split[split] = keypoint_names(payload)
    leaked = {group: sorted(splits) for group, splits in groups.items() if len(splits) > 1}
    if leaked:
        details = "; ".join(f"{group}: {','.join(splits)}" for group, splits in sorted(leaked.items()))
        errors.append(f"Source sequences cross dataset splits ({details})")
    if total < minimum_images:
        errors.append(f"Dataset has {total} images; at least {minimum_images} are required")
    present = set()
    for names in keypoints_by_split.values():
        present.update(names)
    if not present:
        errors.append("Dataset has no keypoint category with a keypoints list")
    else:
        missing = sorted(set(EXPECTED_KEYPOINTS) - present)
        if missing:
            errors.append("Keypoint schema is missing expected COCO v6 names: " + ", ".join(missing))
    if manifest is None:
        errors.append("A subject manifest is required to prove subject-level split isolation")
    else:
        with manifest.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        required = {"source_group", "subject_id", "split"}
        if not rows or not required.issubset(rows[0]):
            errors.append("Manifest must contain source_group, subject_id and split columns")
        else:
            subject_splits: dict[str, set[str]] = {}
            manifest_groups: dict[str, tuple[str, str]] = {}
            for row in rows:
                group = row["source_group"].strip().lower()
                subject = row["subject_id"].strip()
                split = row["split"].strip()
                if not group or not subject or split not in SPLITS:
                    errors.append(f"Invalid manifest row: {row}")
                    continue
                if group in manifest_groups:
                    errors.append(f"Manifest contains duplicate source_group: {group}")
                    continue
                manifest_groups[group] = (subject, split)
                subject_splits.setdefault(subject, set()).add(split)
            missing_groups = sorted(set(groups) - set(manifest_groups))
            if missing_groups:
                errors.append("Manifest is missing dataset source groups: " + ", ".join(missing_groups))
            unknown_groups = sorted(set(manifest_groups) - set(groups))
            if unknown_groups:
                errors.append("Manifest contains source groups not found in the dataset: " + ", ".join(unknown_groups))
            for group, split_set in groups.items():
                if group in manifest_groups and manifest_groups[group][1] not in split_set:
                    errors.append(
                        f"Manifest split for {group} is {manifest_groups[group][1]}, "
                        f"but the dataset contains it in {','.join(sorted(split_set))}"
                    )
            crossed = sorted(subject for subject, splits in subject_splits.items() if len(splits) > 1)
            if crossed:
                errors.append("Subjects cross dataset splits: " + ", ".join(crossed))
            if len(subject_splits) < minimum_subjects:
                errors.append(f"Manifest has {len(subject_splits)} subjects; at least {minimum_subjects} are required")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--minimum-images", type=int, default=50)
    parser.add_argument("--minimum-subjects", type=int, default=5)
    args = parser.parse_args()
    errors = validate(args.archive, args.minimum_images, args.minimum_subjects, args.manifest)
    if errors:
        raise SystemExit("Dataset validation failed:\n- " + "\n- ".join(errors))
    print("Dataset validation passed.")


if __name__ == "__main__":
    main()
