"""Firebase Authentication connection.

When OAuth2 user tokens are available, queries the Identity Toolkit REST API
directly (works with the ``firebase`` scope — no ``identitytoolkit`` scope
needed).  Falls back to the Firebase Admin SDK when using service-account
credentials.

Usage::

    from analytics_agent.connections import get_firebase_connection

    fb = get_firebase_connection()
    fb.connect()
    df = fb.list_users()
"""

import logging
import os
from datetime import datetime

import pandas as pd
import requests
from dotenv import load_dotenv

from analytics_agent.auth import get_credentials as _get_oauth2
from analytics_agent.config import get_config_value

load_dotenv()

logger = logging.getLogger(__name__)

TEST_EMAIL_DOMAINS: list[str] = [
    # Add your internal/test email domains here, e.g. "@yourcompany.com"
]

_V3_BASE = "https://www.googleapis.com/identitytoolkit/v3/relyingparty"


def _resolve_project_id() -> str | None:
    from_env = os.getenv("FIREBASE_PROJECT_ID")
    if from_env:
        return from_env
    return get_config_value("firebase", "project_id")


# ═════════════════════════════════════════════════════════════════════════
# REST API helpers (used when OAuth2 tokens are available)
# ═════════════════════════════════════════════════════════════════════════

def _get_auth_header(creds) -> dict:
    """Return Authorization header, refreshing the token if needed."""
    if creds.expired:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}


def _rest_list_users(project_id: str, creds, max_results: int | None = None) -> list[dict]:
    """List users via the v3 Identity Toolkit ``downloadAccount`` endpoint.

    This endpoint works with the ``firebase`` scope (no ``identitytoolkit``
    scope required).
    """
    url = f"{_V3_BASE}/downloadAccount"
    headers = _get_auth_header(creds)
    all_users: list[dict] = []
    next_page_token = None

    while True:
        body: dict = {
            "targetProjectId": project_id,
            "maxResults": min(max_results or 1000, 1000),
        }
        if next_page_token:
            body["nextPageToken"] = next_page_token

        resp = requests.post(url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for u in data.get("users", []):
            all_users.append(_raw_user_to_dict(u))
            if max_results and len(all_users) >= max_results:
                return all_users

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return all_users


def _rest_lookup_users(project_id: str, creds, *, email: str | None = None, uid: str | None = None) -> dict | None:
    """Look up a single user by scanning downloadAccount results.

    The v3 ``getAccountInfo`` endpoint requires the ``identitytoolkit``
    scope, so we use ``downloadAccount`` with a full scan instead.  For
    projects with very large user bases this is slower but avoids needing
    a restricted scope.
    """
    all_users = _rest_list_users(project_id, creds)
    for u in all_users:
        if email and u.get("email", "").lower() == email.lower():
            return u
        if uid and u.get("uid") == uid:
            return u
    return None


def _raw_user_to_dict(u: dict) -> dict:
    """Convert a raw REST API user record to our standard dict format."""
    ts_created = int(u.get("createdAt", 0))
    ts_login = int(u.get("lastLoginAt", 0))
    providers = u.get("providerUserInfo", [])
    return {
        "uid": u.get("localId", ""),
        "email": u.get("email", ""),
        "display_name": u.get("displayName", ""),
        "phone_number": u.get("phoneNumber", ""),
        "provider_id": providers[0].get("providerId", "") if providers else "",
        "email_verified": u.get("emailVerified", False),
        "disabled": u.get("disabled", False),
        "created_at": datetime.fromtimestamp(ts_created / 1000) if ts_created else None,
        "last_sign_in": datetime.fromtimestamp(ts_login / 1000) if ts_login else None,
    }


# ═════════════════════════════════════════════════════════════════════════
# FirebaseConnection
# ═════════════════════════════════════════════════════════════════════════

class FirebaseConnection:
    """Wrapper around Firebase Auth — uses REST API for OAuth2, Admin SDK for
    service-account credentials."""

    def __init__(self):
        self.project_id = _resolve_project_id()
        self._oauth_creds = None  # set if using OAuth2 path
        self._admin_app = None    # set if using Admin SDK path
        self._mode: str | None = None  # "oauth2" or "admin_sdk"

    # ── Connection ───────────────────────────────────────────────────────

    def connect(self) -> bool:
        # Try OAuth2 first (REST API path)
        creds = _get_oauth2()
        if creds is not None:
            if not self.project_id:
                logger.error(
                    "Firebase project ID required for OAuth2 mode. "
                    "Run `analytics-agent setup` to select a project."
                )
                return False
            self._oauth_creds = creds
            self._mode = "oauth2"
            logger.info(f"Firebase: using OAuth2 REST API (project: {self.project_id})")
            return True

        # Fall back to Admin SDK (service account)
        try:
            import firebase_admin
            from analytics_agent.credentials import resolve_firebase_credential

            if firebase_admin._apps:
                self._admin_app = firebase_admin.get_app()
                self._mode = "admin_sdk"
                logger.info("Reusing existing Firebase Admin app")
                return True

            cred = resolve_firebase_credential()
            options = {"projectId": self.project_id} if self.project_id else None
            self._admin_app = firebase_admin.initialize_app(cred, options=options)
            self._mode = "admin_sdk"
            logger.info("Connected to Firebase Admin SDK")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Firebase: {e}")
            return False

    # ── Core queries ─────────────────────────────────────────────────────

    def list_users(self, max_results: int | None = None) -> pd.DataFrame | None:
        if not self._mode:
            if not self.connect():
                return None

        try:
            if self._mode == "oauth2":
                raw = _rest_list_users(self.project_id, self._oauth_creds, max_results)
                users_data = raw  # already in the right format
            else:
                users_data = self._admin_list_users(max_results)
        except Exception as e:
            logger.error(f"Error listing Firebase users: {e}")
            return None

        for u in users_data:
            u["is_test_account"] = self._is_test_email(u.get("email", ""))

        df = pd.DataFrame(users_data)
        if df.empty:
            return df
        logger.info(
            f"Listed {len(df)} Firebase Auth users "
            f"({df['is_test_account'].sum()} test accounts)"
        )
        return df

    def list_real_users(self, max_results: int | None = None) -> pd.DataFrame | None:
        df = self.list_users(max_results=max_results)
        if df is None or df.empty:
            return df
        return df[~df["is_test_account"]].reset_index(drop=True)

    def list_test_users(self, max_results: int | None = None) -> pd.DataFrame | None:
        df = self.list_users(max_results=max_results)
        if df is None or df.empty:
            return df
        return df[df["is_test_account"]].reset_index(drop=True)

    def get_user_by_email(self, email: str) -> dict | None:
        if not self._mode:
            if not self.connect():
                return None
        try:
            if self._mode == "oauth2":
                raw = _rest_lookup_users(self.project_id, self._oauth_creds, email=email)
                if not raw:
                    logger.warning(f"No Firebase user found with email: {email}")
                    return None
                result = _raw_user_to_dict(raw)
            else:
                from firebase_admin import auth
                user = auth.get_user_by_email(email)
                result = self._admin_user_to_dict(user)
            result["is_test_account"] = self._is_test_email(result.get("email", ""))
            return result
        except Exception as e:
            logger.error(f"Error fetching user by email: {e}")
            return None

    def get_user_by_uid(self, uid: str) -> dict | None:
        if not self._mode:
            if not self.connect():
                return None
        try:
            if self._mode == "oauth2":
                raw = _rest_lookup_users(self.project_id, self._oauth_creds, uid=uid)
                if not raw:
                    logger.warning(f"No Firebase user found with uid: {uid}")
                    return None
                result = _raw_user_to_dict(raw)
            else:
                from firebase_admin import auth
                user = auth.get_user(uid)
                result = self._admin_user_to_dict(user)
            result["is_test_account"] = self._is_test_email(result.get("email", ""))
            return result
        except Exception as e:
            logger.error(f"Error fetching user by uid: {e}")
            return None

    def signup_summary(self, since: str | None = None) -> pd.DataFrame | None:
        df = self.list_users()
        if df is None or df.empty:
            return df
        if since:
            df = df[df["created_at"] >= pd.Timestamp(since)]
        total = len(df)
        real = int((~df["is_test_account"]).sum())
        test = int(df["is_test_account"].sum())
        return pd.DataFrame([
            {"metric": "total_users", "value": total},
            {"metric": "real_users", "value": real},
            {"metric": "test_accounts", "value": test},
            {"metric": "test_pct", "value": round(test / total * 100, 1) if total else 0},
        ])

    def daily_signups(
        self, since: str | None = None, exclude_test: bool = True
    ) -> pd.DataFrame | None:
        df = self.list_users()
        if df is None or df.empty:
            return df
        if exclude_test:
            df = df[~df["is_test_account"]]
        if since:
            df = df[df["created_at"] >= pd.Timestamp(since)]
        df["date"] = df["created_at"].dt.date
        return df.groupby("date").size().reset_index(name="signups").sort_values("date")

    # ── Admin SDK helpers (service-account path) ─────────────────────────

    def _admin_list_users(self, max_results: int | None = None) -> list[dict]:
        from firebase_admin import auth
        users_data: list[dict] = []
        count = 0
        page = auth.list_users()
        while page:
            for user in page.users:
                users_data.append(self._admin_user_to_dict(user))
                count += 1
                if max_results and count >= max_results:
                    return users_data
            if max_results and count >= max_results:
                break
            page = page.get_next_page()
        return users_data

    @staticmethod
    def _admin_user_to_dict(user) -> dict:
        return {
            "uid": user.uid,
            "email": user.email or "",
            "display_name": user.display_name or "",
            "phone_number": user.phone_number or "",
            "provider_id": (
                user.provider_data[0].provider_id if user.provider_data else ""
            ),
            "email_verified": user.email_verified,
            "disabled": user.disabled,
            "created_at": (
                datetime.fromtimestamp(user.user_metadata.creation_timestamp / 1000)
                if user.user_metadata.creation_timestamp else None
            ),
            "last_sign_in": (
                datetime.fromtimestamp(user.user_metadata.last_sign_in_timestamp / 1000)
                if user.user_metadata.last_sign_in_timestamp else None
            ),
        }

    # ── Shared helpers ───────────────────────────────────────────────────

    @staticmethod
    def _is_test_email(email: str) -> bool:
        email_lower = email.lower()
        return any(email_lower.endswith(domain) for domain in TEST_EMAIL_DOMAINS)

    # ── Teardown ─────────────────────────────────────────────────────────

    def close(self):
        if self._admin_app:
            import firebase_admin
            try:
                firebase_admin.delete_app(self._admin_app)
                self._admin_app = None
            except Exception:
                pass
        self._oauth_creds = None
        self._mode = None
        logger.info("Firebase connection closed")


def get_firebase_connection() -> FirebaseConnection:
    return FirebaseConnection()
