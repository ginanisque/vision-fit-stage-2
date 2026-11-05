import csv
import json
import zipfile

from scripts.validate_coco_dataset import EXPECTED_KEYPOINTS, validate


def _archive(path, split_files):
    with zipfile.ZipFile(path, "w") as bundle:
        for split in ("train", "valid", "test"):
            payload = {"images": [
                {"id": index, "file_name": name}
                for index, name in enumerate(split_files.get(split, []), start=1)
            ]}
            bundle.writestr(f"{split}/_annotations.coco.json", json.dumps(payload))


def _manifest(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("source_group", "subject_id", "split"))
        writer.writeheader()
        writer.writerows(rows)


def _keypoint_archive(path, keypoint_names):
    with zipfile.ZipFile(path, "w") as bundle:
        for split in ("train", "valid", "test"):
            payload = {
                "images": [{"id": 1, "file_name": f"{split}.jpg"}],
                "categories": [{"id": 1, "name": "person", "keypoints": keypoint_names}],
            }
            bundle.writestr(f"{split}/_annotations.coco.json", json.dumps(payload))


def _matching_manifest(path):
    _manifest(path, [
        {"source_group": "train", "subject_id": "subject-1", "split": "train"},
        {"source_group": "valid", "subject_id": "subject-2", "split": "valid"},
        {"source_group": "test", "subject_id": "subject-3", "split": "test"},
    ])


def test_rejects_source_sequence_leakage_and_missing_manifest(tmp_path):
    archive = tmp_path / "dataset.zip"
    _archive(archive, {"train": ["turn_frame_1.jpg"], "valid": ["turn_frame_2.jpg"]})

    errors = validate(archive, minimum_images=1, minimum_subjects=1, manifest=None)

    assert any("Source sequences cross" in error for error in errors)
    assert any("subject manifest is required" in error for error in errors)


def test_manifest_must_cover_groups_and_match_dataset_splits(tmp_path):
    archive = tmp_path / "dataset.zip"
    manifest = tmp_path / "subjects.csv"
    _archive(archive, {"train": ["alpha.jpg"], "valid": ["beta.jpg"], "test": ["gamma.jpg"]})
    _manifest(manifest, [
        {"source_group": "alpha", "subject_id": "one", "split": "valid"},
        {"source_group": "unknown", "subject_id": "two", "split": "test"},
    ])

    errors = validate(archive, minimum_images=1, minimum_subjects=1, manifest=manifest)

    assert any("missing dataset source groups" in error and "beta" in error for error in errors)
    assert any("not found in the dataset" in error and "unknown" in error for error in errors)
    assert any("Manifest split for alpha is valid" in error for error in errors)


def test_rejects_missing_expected_keypoint_names(tmp_path):
    archive = tmp_path / "dataset.zip"
    manifest = tmp_path / "subjects.csv"
    _keypoint_archive(archive, ["nape", "center_front_neck"])
    _matching_manifest(manifest)

    errors = validate(archive, minimum_images=1, minimum_subjects=1, manifest=manifest)

    assert any("Keypoint schema is missing expected COCO v6 names" in error for error in errors)


def test_accepts_complete_keypoint_schema(tmp_path):
    archive = tmp_path / "dataset.zip"
    manifest = tmp_path / "subjects.csv"
    _keypoint_archive(archive, list(EXPECTED_KEYPOINTS))
    _matching_manifest(manifest)

    errors = validate(archive, minimum_images=1, minimum_subjects=1, manifest=manifest)

    assert errors == []
