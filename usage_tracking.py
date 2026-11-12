"""Optional Google sign-in and owner-only activity history for the chatbot."""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

_LOG = logging.getLogger(__name__)
_CREATE = """
CREATE TABLE IF NOT EXISTS campen_chatbot_activity (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    email text NOT NULL,
    action text NOT NULL,
    details jsonb NOT NULL
)
"""
_IST = ZoneInfo("Asia/Kolkata")


def _email(value):
    return str(value or "").strip().casefold()


def _verified_email(claims):
    if claims.get("email_verified") is not True:
        return ""
    expiry = claims.get("exp")
    if not isinstance(expiry, (float, int)) or expiry <= datetime.now(timezone.utc).timestamp():
        return ""
    return _email(claims.get("email"))


def _connect(dsn):
    import psycopg

    return psycopg.connect(dsn, connect_timeout=5, options="-c statement_timeout=5000")


def record_event(action, **details):
    """Record one completed UI action. Omit raw prompts and document contents."""
    email = st.session_state.get("campen_usage_email")
    if not email:
        return
    try:
        with _connect(st.secrets["usage_tracking"]["database_url"]) as conn:
            conn.execute(
                "INSERT INTO campen_chatbot_activity (email, action, details) VALUES (%s, %s, %s::jsonb)",
                (email, action, json.dumps(details, ensure_ascii=False, default=str)),
            )
    except Exception:
        _LOG.warning("Could not store a chatbot activity event.")
        st.session_state["campen_usage_write_failed"] = True


def _show_owner_history(dsn):
    with st.sidebar.expander("Usage history"):
        if st.button("Load latest activity", key="campen_usage_load"):
            st.session_state["campen_usage_loaded"] = True
        if not st.session_state.get("campen_usage_loaded"):
            return
        try:
            with _connect(dsn) as conn:
                rows = conn.execute(
                    "SELECT occurred_at, email, action, details FROM campen_chatbot_activity "
                    "ORDER BY occurred_at DESC, id DESC LIMIT 1000"
                ).fetchall()
        except Exception:
            st.error("Usage history is unavailable. Check the database settings.")
            return
        entries = [{"Time (IST)": time.astimezone(_IST).strftime("%d %b %Y %H:%M:%S"),
                    "Account": email, "Action": action,
                    "Details": ", ".join(f"{key}={value}" for key, value in details.items())}
                   for time, email, action, details in rows]
        if not entries:
            st.caption("No activity recorded yet.")
            return
        st.caption("Showing up to 50 recent events. Download the CSV for up to 1,000.")
        st.text("\n\n".join(f"{entry['Time (IST)']} · {entry['Account']}\n"
                            f"{entry['Action']} {entry['Details']}".rstrip()
                            for entry in entries[:50]))
        data = io.StringIO()
        writer = csv.DictWriter(data, fieldnames=list(entries[0]))
        writer.writeheader()
        writer.writerows(entries)
        st.download_button("Download latest activity CSV", data.getvalue(), "chatbot-activity.csv", "text/csv")


def require_configured_login():
    """Enable sign-in only when the usage configuration is explicitly present."""
    try:
        config = st.secrets.get("usage_tracking")
    except (FileNotFoundError, KeyError):
        config = None
    if config is None:
        return False
    owner = _email(config.get("owner_email"))
    allowed = {_email(value) for value in config.get("allowed_emails", [])} - {""}
    dsn = config.get("database_url")
    if not owner or owner not in allowed or not dsn:
        st.error("Usage tracking setup is incomplete. Ask the owner to check the app settings.")
        st.stop()
    if not st.user.is_logged_in:
        st.info("Sign in with your approved Google account to use the chatbot. Usage actions are visible to the owner.")
        st.button("Sign in with Google", on_click=st.login)
        st.stop()
    email = _verified_email(st.user)
    if not email or email not in allowed:
        st.error("This Google account is not approved, or its sign-in has expired.")
        st.button("Switch Google account", on_click=st.logout)
        st.stop()
    if st.session_state.get("campen_usage_email") != email:
        try:
            with _connect(dsn) as conn:
                conn.execute(_CREATE)
        except Exception:
            st.error("Activity storage is unavailable. Ask the owner to check the database settings.")
            st.stop()
        st.session_state["campen_usage_email"] = email
        record_event("Opened chatbot")
    st.sidebar.caption(f"Signed in as {email}")
    st.sidebar.button("Sign out", on_click=st.logout)
    if st.session_state.pop("campen_usage_write_failed", False):
        st.sidebar.warning("An activity event could not be recorded.")
    if email == owner:
        _show_owner_history(dsn)
    return True
