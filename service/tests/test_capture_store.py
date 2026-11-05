import csv
import io
import os
from datetime import datetime, timezone
from uuid import uuid4
from zipfile import ZipFile

import pytest

from app import capture_store


class QueryResult:
    def __init__(self, row=None, rows=None, rowcount=0):
        self.row = row
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, _params):
        normalized = " ".join(query.split())
        self.events.append(normalized)
        if normalized.startswith("select id from capture_sessions"):
            return QueryResult(row={"id": "session-1"})
        if normalized.startswith("select storage_key from capture_assets"):
            return QueryResult(rows=[{"storage_key": "private/object-1"}])
        if normalized.startswith("update capture_sessions set status"):
            return QueryResult(rowcount=1)
        if normalized.startswith("delete from measurement_tables"):
            return QueryResult(rowcount=2)
        if normalized.startswith("delete from capture_sessions"):
            return QueryResult(row={"id": "session-1"})
        raise AssertionError(f"Unexpected SQL: {normalized}")


def test_session_deletion_marks_retryable_state_before_removing_objects(monkeypatch):
    events = []
    monkeypatch.setattr(capture_store, "connection", lambda: FakeConnection(events))
    monkeypatch.setattr(
        capture_store, "delete_private",
        lambda key: events.append(f"delete-object:{key}"),
    )

    result = capture_store.delete_capture_session("session-1", owner_id=uuid4())

    assert result == {"assetsDeleted": 1, "measurementTablesDeleted": 2}
    assert events[2].startswith("update capture_sessions set status")
    assert events[3] == "delete-object:private/object-1"
    assert events[4].startswith("select id from capture_sessions")
    assert events[5].startswith("delete from measurement_tables")
    assert events[6].startswith("delete from capture_sessions")


def test_failed_object_deletion_preserves_database_rows(monkeypatch):
    events = []
    monkeypatch.setattr(capture_store, "connection", lambda: FakeConnection(events))

    def fail_delete(_key):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(capture_store, "delete_private", fail_delete)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        capture_store.delete_capture_session("session-1", owner_id=uuid4())

    assert not any(event.startswith("delete from ") for event in events)


def test_retention_retries_sessions_already_marked_for_deletion(monkeypatch):
    events = []
    monkeypatch.setattr(capture_store, "connection", lambda: FakeConnection(events))
    monkeypatch.setattr(capture_store, "delete_private", lambda _key: None)

    capture_store.delete_capture_session(
        "session-1",
        owner_id=uuid4(),
        older_than=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )

    assert "status = 'deleting' or updated_at < %s" in events[0]


def test_retention_worker_selects_deleting_sessions_for_retry(monkeypatch):
    queries = []
    session = {"id": "session-1", "customer_id": uuid4()}

    class RetentionConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params):
            queries.append(" ".join(query.split()))
            return QueryResult(rows=[session])

    retried = []
    monkeypatch.setattr(capture_store, "connection", lambda: RetentionConnection())
    monkeypatch.setattr(
        capture_store, "delete_capture_session",
        lambda session_id, **kwargs: retried.append((session_id, kwargs)) or {"assetsDeleted": 1},
    )

    removed = capture_store.purge_expired_capture_sessions(30)

    assert removed == 1
    assert "where status = 'deleting' or updated_at < now()" in queries[0]
    assert retried[0][0] == "session-1"
    assert retried[0][1]["older_than"] is not None


@pytest.mark.parametrize("training_consent", [False, True])
def test_admin_capture_media_download_requires_training_consent(monkeypatch, training_consent):
    created_at = datetime(2026, 11, 4, tzinfo=timezone.utc)
    queries = []
    session = {
        "id": "session-1", "customer_id": uuid4(), "email": "customer@example.test",
        "display_name": "Customer", "role": "customer", "height_mm": 1700,
        "status": "complete", "consented_at": created_at, "consent_version": "visionfit-v3",
        "training_consent": training_consent, "external_vision_consent": False, "notes": "",
        "created_at": created_at, "updated_at": created_at,
    }
    asset = {
        "id": "asset-1", "view": "front", "storage_key": "private/front",
        "content_type": "image/jpeg", "byte_size": 1024, "sha256": "hash",
        "width_px": 100, "height_px": 200, "duration_seconds": None,
        "captured_at": created_at, "created_at": created_at,
    }

    class DetailConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params):
            normalized = " ".join(query.split())
            queries.append(normalized)
            if normalized.startswith("select cs.id, cs.customer_id"):
                return QueryResult(row=session)
            if normalized.startswith("select id, view::text"):
                return QueryResult(rows=[asset])
            return QueryResult(rows=[])

    signed_keys = []
    monkeypatch.setattr(capture_store, "connection", lambda: DetailConnection())
    monkeypatch.setattr(
        capture_store, "signed_download_url",
        lambda key: signed_keys.append(key) or "https://private.example.test/image",
    )

    detail = capture_store.admin_capture_session("session-1")

    assert detail["trainingConsent"] is training_consent
    assert queries[0].find("cs.training_consent") >= 0
    assert detail["assets"][0]["reviewUrl"] == (
        "https://private.example.test/image" if training_consent else None
    )
    assert signed_keys == (["private/front"] if training_consent else [])


def test_training_export_contains_anonymized_images_and_consent_manifest(monkeypatch):
    customer_id = uuid4()
    consented_at = datetime(2026, 11, 4, tzinfo=timezone.utc)
    rows = [
        {
            "session_id": "session-1", "customer_id": customer_id,
            "consent_version": "visionfit-v3", "consented_at": consented_at,
            "asset_id": "asset-1", "view": "front", "storage_key": "private/front",
            "content_type": "image/jpeg", "sha256": "front-hash",
        },
        {
            "session_id": "session-2", "customer_id": customer_id,
            "consent_version": "visionfit-v3", "consented_at": consented_at,
            "asset_id": "asset-2", "view": "side", "storage_key": "private/side",
            "content_type": "image/png; charset=binary", "sha256": "side-hash",
        },
    ]
    queries = []

    class ExportConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query):
            queries.append(" ".join(query.split()))
            return QueryResult(rows=rows)

    monkeypatch.setattr(capture_store, "connection", lambda: ExportConnection())
    monkeypatch.setattr(
        capture_store, "get_private",
        lambda key: {"private/front": b"front-image", "private/side": b"side-image"}[key],
    )

    export_path, image_count = capture_store.create_training_export()
    try:
        assert image_count == 2
        assert "where cs.training_consent = true" in queries[0]
        assert "like 'image/%'" in queries[0]
        with ZipFile(export_path) as archive:
            manifest = list(csv.DictReader(io.StringIO(archive.read("manifest.csv").decode())))
            assert len(manifest) == 2
            assert manifest[0]["subject_id"] == manifest[1]["subject_id"]
            assert manifest[0]["source_group"] != manifest[1]["source_group"]
            assert all(row["training_consent"] == "true" for row in manifest)
            assert all(row["consent_version"] == "visionfit-v3" for row in manifest)
            assert archive.read(manifest[0]["path"]) == b"front-image"
            assert archive.read(manifest[1]["path"]) == b"side-image"
            assert str(customer_id).encode() not in archive.read("manifest.csv")
    finally:
        os.unlink(export_path)
