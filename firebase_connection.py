"""
Firebase Authentication Connection

Provides a FirebaseConnection class that mirrors the pattern of
database_connection.py and ga_connection.py.  Authenticates via the same
GCP service account and queries Firebase Auth users, returning pandas
DataFrames for analysis.

Primary use-case: list signed-up users and filter out internal test
accounts (e.g. emails ending with @altar.inc).

Usage:
    from firebase_connection import get_firebase_connection

    fb = get_firebase_connection()
    fb.connect()

    # Get all Firebase Auth users as a DataFrame
    df = fb.list_users()

    # Get only real (non-test) users
    real = fb.list_real_users()

    # Get only internal test accounts
    test = fb.list_test_users()

    fb.close()
"""

import os
import json
import tempfile
import logging
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal test-account domains to exclude from "real" user counts.
# Add more domains here as needed.
# ---------------------------------------------------------------------------
TEST_EMAIL_DOMAINS = [
    "@altar.inc",
]


def _ensure_gcp_credentials():
    """Reuse the same logic from database_connection.py: if
    GCP_SERVICE_ACCOUNT_JSON is set inline, write it to a temp file and point
    GOOGLE_APPLICATION_CREDENTIALS at it."""
    sa_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if sa_json and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        creds = json.loads(sa_json)
        creds_path = os.path.join(tempfile.gettempdir(), "gcp_sa_key.json")
        with open(creds_path, "w") as f:
            json.dump(creds, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        logger.info(f"Wrote GCP SA credentials to {creds_path}")


# ---------------------------------------------------------------------------
# FirebaseConnection
# ---------------------------------------------------------------------------
class FirebaseConnection:
    """Thin wrapper around the Firebase Admin SDK (Auth).

    Mirrors the interface of DatabaseConnection / GAConnection so all three
    can be used side-by-side in analysis scripts.
    """

    def __init__(self):
        self.app = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        """Initialise the Firebase Admin app using the GCP service account."""
        try:
            _ensure_gcp_credentials()

            import firebase_admin
            from firebase_admin import credentials as fb_credentials

            # Avoid re-initialising if already done in this process
            if firebase_admin._apps:
                self.app = firebase_admin.get_app()
                logger.info("Reusing existing Firebase Admin app")
                return True

            # Resolve credentials
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            sa_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")

            if creds_path:
                cred = fb_credentials.Certificate(creds_path)
            elif sa_json:
                cred = fb_credentials.Certificate(json.loads(sa_json))
            else:
                # Try Application Default Credentials
                cred = fb_credentials.ApplicationDefault()

            self.app = firebase_admin.initialize_app(cred)
            logger.info("Connected to Firebase Admin SDK")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Firebase: {e}")
            return False

    # ------------------------------------------------------------------
    # Core queries
    # ------------------------------------------------------------------
    def list_users(self, max_results: int | None = None) -> pd.DataFrame | None:
        """List all Firebase Auth users and return as a DataFrame.

        Iterates through all pages of users.  For large user bases this may
        take a while — use ``max_results`` to cap the number returned.

        Columns returned:
            uid, email, display_name, phone_number, provider_id,
            email_verified, disabled, created_at, last_sign_in,
            is_test_account
        """
        if not self.app:
            if not self.connect():
                return None

        from firebase_admin import auth

        users_data = []
        count = 0

        try:
            page = auth.list_users()
            while page:
                for user in page.users:
                    email = user.email or ""
                    is_test = self._is_test_email(email)

                    users_data.append({
                        "uid": user.uid,
                        "email": email,
                        "display_name": user.display_name or "",
                        "phone_number": user.phone_number or "",
                        "provider_id": (
                            user.provider_data[0].provider_id
                            if user.provider_data else ""
                        ),
                        "email_verified": user.email_verified,
                        "disabled": user.disabled,
                        "created_at": (
                            datetime.fromtimestamp(
                                user.user_metadata.creation_timestamp / 1000
                            )
                            if user.user_metadata.creation_timestamp
                            else None
                        ),
                        "last_sign_in": (
                            datetime.fromtimestamp(
                                user.user_metadata.last_sign_in_timestamp / 1000
                            )
                            if user.user_metadata.last_sign_in_timestamp
                            else None
                        ),
                        "is_test_account": is_test,
                    })

                    count += 1
                    if max_results and count >= max_results:
                        break

                if max_results and count >= max_results:
                    break

                page = page.get_next_page()

        except Exception as e:
            logger.error(f"Error listing Firebase users: {e}")
            return None

        df = pd.DataFrame(users_data)
        logger.info(
            f"Listed {len(df)} Firebase Auth users "
            f"({df['is_test_account'].sum()} test accounts)"
        )
        return df

    def list_real_users(self, max_results: int | None = None) -> pd.DataFrame | None:
        """List only real (non-test) users — excludes @altar.inc etc."""
        df = self.list_users(max_results=max_results)
        if df is None or df.empty:
            return df
        return df[~df["is_test_account"]].reset_index(drop=True)

    def list_test_users(self, max_results: int | None = None) -> pd.DataFrame | None:
        """List only internal test accounts (@altar.inc etc.)."""
        df = self.list_users(max_results=max_results)
        if df is None or df.empty:
            return df
        return df[df["is_test_account"]].reset_index(drop=True)

    def get_user_by_email(self, email: str) -> dict | None:
        """Look up a single Firebase Auth user by email."""
        if not self.app:
            if not self.connect():
                return None

        from firebase_admin import auth

        try:
            user = auth.get_user_by_email(email)
            return {
                "uid": user.uid,
                "email": user.email,
                "display_name": user.display_name,
                "email_verified": user.email_verified,
                "disabled": user.disabled,
                "created_at": (
                    datetime.fromtimestamp(
                        user.user_metadata.creation_timestamp / 1000
                    )
                    if user.user_metadata.creation_timestamp
                    else None
                ),
                "last_sign_in": (
                    datetime.fromtimestamp(
                        user.user_metadata.last_sign_in_timestamp / 1000
                    )
                    if user.user_metadata.last_sign_in_timestamp
                    else None
                ),
                "is_test_account": self._is_test_email(user.email or ""),
            }
        except auth.UserNotFoundError:
            logger.warning(f"No Firebase user found with email: {email}")
            return None
        except Exception as e:
            logger.error(f"Error fetching user by email: {e}")
            return None

    def get_user_by_uid(self, uid: str) -> dict | None:
        """Look up a single Firebase Auth user by UID."""
        if not self.app:
            if not self.connect():
                return None

        from firebase_admin import auth

        try:
            user = auth.get_user(uid)
            return {
                "uid": user.uid,
                "email": user.email,
                "display_name": user.display_name,
                "email_verified": user.email_verified,
                "disabled": user.disabled,
                "created_at": (
                    datetime.fromtimestamp(
                        user.user_metadata.creation_timestamp / 1000
                    )
                    if user.user_metadata.creation_timestamp
                    else None
                ),
                "last_sign_in": (
                    datetime.fromtimestamp(
                        user.user_metadata.last_sign_in_timestamp / 1000
                    )
                    if user.user_metadata.last_sign_in_timestamp
                    else None
                ),
                "is_test_account": self._is_test_email(user.email or ""),
            }
        except auth.UserNotFoundError:
            logger.warning(f"No Firebase user found with uid: {uid}")
            return None
        except Exception as e:
            logger.error(f"Error fetching user by uid: {e}")
            return None

    def signup_summary(
        self,
        since: str | None = None,
    ) -> pd.DataFrame | None:
        """Summary stats: total users, real vs test, signups over time.

        Parameters
        ----------
        since : str, optional
            ISO date string (e.g. "2026-02-01"). Only include users created
            on or after this date.
        """
        df = self.list_users()
        if df is None or df.empty:
            return df

        if since:
            cutoff = pd.Timestamp(since)
            df = df[df["created_at"] >= cutoff]

        summary_rows = []

        # Overall counts
        total = len(df)
        real = (~df["is_test_account"]).sum()
        test = df["is_test_account"].sum()
        summary_rows.append({"metric": "total_users", "value": total})
        summary_rows.append({"metric": "real_users", "value": real})
        summary_rows.append({"metric": "test_accounts", "value": test})
        summary_rows.append({
            "metric": "test_pct",
            "value": round(test / total * 100, 1) if total else 0,
        })

        return pd.DataFrame(summary_rows)

    def daily_signups(
        self,
        since: str | None = None,
        exclude_test: bool = True,
    ) -> pd.DataFrame | None:
        """Daily signup counts from Firebase Auth creation timestamps.

        Parameters
        ----------
        since : str, optional
            ISO date string filter.
        exclude_test : bool
            If True (default), exclude @altar.inc accounts.
        """
        df = self.list_users()
        if df is None or df.empty:
            return df

        if exclude_test:
            df = df[~df["is_test_account"]]

        if since:
            cutoff = pd.Timestamp(since)
            df = df[df["created_at"] >= cutoff]

        df["date"] = df["created_at"].dt.date
        daily = (
            df.groupby("date")
            .size()
            .reset_index(name="signups")
            .sort_values("date")
        )
        return daily

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _is_test_email(email: str) -> bool:
        """Check if an email belongs to an internal test domain."""
        email_lower = email.lower()
        return any(email_lower.endswith(domain) for domain in TEST_EMAIL_DOMAINS)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def close(self):
        """Delete the Firebase Admin app to release resources."""
        if self.app:
            import firebase_admin

            try:
                firebase_admin.delete_app(self.app)
                self.app = None
                logger.info("Firebase Admin app closed")
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------
def get_firebase_connection() -> FirebaseConnection:
    """Get a FirebaseConnection instance (mirrors get_db_connection())."""
    return FirebaseConnection()
