"""Non-production smoke test for Neon DB + private storage workflow.

Creates uniquely identified test records and one small private object, verifies the
admin review path, then removes only the records/object created by this run.
"""
from __future__ import annotations

from uuid import uuid4

import cv2
import numpy as np

from app.auth import SessionUser
from app.capture import capture_decision
from app.capture_store import ensure_session, persist_analysis
from app.database import connection
from app.storage import client, delete_private
from app.settings import get_settings


def main() -> None:
    suffix = uuid4().hex
    customer_id = admin_id = session_id = table_id = None
    storage_key = None
    try:
        with connection() as conn:
            customer = conn.execute(
                """insert into app_users (email, display_name, role, auth_provider, auth_subject)
                   values (%s, 'Flow Test Customer', 'customer', 'flow_test', %s) returning id""",
                (f"visionfit-flow-{suffix}@example.test", f"customer-{suffix}"),
            ).fetchone()
            admin = conn.execute(
                """insert into app_users (email, display_name, role, auth_provider, auth_subject)
                   values (%s, 'Flow Test Admin', 'admin', 'flow_test', %s) returning id""",
                (f"visionfit-admin-{suffix}@example.test", f"admin-{suffix}"),
            ).fetchone()
            customer_id, admin_id = customer["id"], admin["id"]

        customer_user = SessionUser(customer_id, f"customer-{suffix}", f"visionfit-flow-{suffix}@example.test", "customer")
        session_id = ensure_session(customer_user, None, 1700)
        image = np.full((128, 96, 3), 150, dtype=np.uint8)
        image[16:116, 30:66] = 80
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        data = encoded.tobytes()
        record = capture_decision("front", image, data)
        persisted = persist_analysis(
            user=customer_user, session_id=session_id, view="front", data=data,
            content_type="image/png", record=record, width=96, height=128,
        )

        with connection() as conn:
            asset = conn.execute(
                "select storage_key, byte_size from capture_assets where id = %s",
                (persisted["assetId"],),
            ).fetchone()
            storage_key = asset["storage_key"]
            assert asset["byte_size"] == len(data)
            client().head_object(Bucket=get_settings().s3_bucket, Key=storage_key)
            table = conn.execute(
                """insert into measurement_tables
                       (customer_id, capture_session_id, registry_version, preferred_unit, created_by)
                     values (%s, %s, '1.4.0', 'cm', %s) returning id""",
                (customer_id, session_id, admin_id),
            ).fetchone()
            table_id = table["id"]
            assert conn.execute(
                "select count(*) from measurement_values where table_id = %s", (table_id,)
            ).fetchone()["count"] == 13
            conn.execute(
                """update measurement_values
                      set value_mm = 725, status = 'reviewed', method = 'flow_test',
                          source_views = array['front','side','back']::capture_view[],
                          reviewed_by = %s, reviewed_at = now()
                    where table_id = %s and measurement_key = 'waist'""",
                (admin_id, table_id),
            )
            reviewed = conn.execute(
                "select value_mm, status::text from measurement_values where table_id = %s and measurement_key = 'waist'",
                (table_id,),
            ).fetchone()
            assert float(reviewed["value_mm"]) == 725 and reviewed["status"] == "reviewed"
        print("FLOW_OK customer_upload analysis private_storage admin_review measurement_table")
    finally:
        if storage_key:
            delete_private(storage_key)
        with connection() as conn:
            if table_id:
                conn.execute("delete from measurement_tables where id = %s", (table_id,))
            if session_id:
                conn.execute("delete from capture_sessions where id = %s", (session_id,))
            ids = [value for value in (customer_id, admin_id) if value]
            if ids:
                conn.execute("delete from app_users where id = any(%s)", (ids,))


if __name__ == "__main__":
    main()
