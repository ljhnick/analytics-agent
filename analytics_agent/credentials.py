"""Unified credential resolution.

Priority chain:
  1. OAuth2 user tokens  (from ``analytics-agent auth login``)
  2. GCP service account  (from env vars — for CI / power users)
  3. Application Default Credentials
"""

import json
import logging
import os
import tempfile

import google.auth

from analytics_agent.auth import get_credentials as _get_oauth2
from analytics_agent.config import TOKEN_FILE

logger = logging.getLogger(__name__)


def resolve_credentials():
    """Return a ``google.auth.credentials.Credentials`` instance.

    Tries OAuth2 user tokens first, then service-account env vars, then ADC.
    Raises ``RuntimeError`` if nothing works.
    """
    # 1. OAuth2 tokens
    creds = _get_oauth2()
    if creds is not None:
        logger.debug("Using OAuth2 user credentials")
        return creds

    # 2. Service account from env vars
    creds = _load_service_account()
    if creds is not None:
        logger.debug("Using service-account credentials")
        return creds

    # 3. Application Default Credentials
    try:
        creds, _ = google.auth.default()
        logger.debug("Using Application Default Credentials")
        return creds
    except google.auth.exceptions.DefaultCredentialsError:
        pass

    raise RuntimeError(
        "No credentials found.  Run `analytics-agent auth login` or set "
        "GOOGLE_APPLICATION_CREDENTIALS / GCP_SERVICE_ACCOUNT_JSON."
    )


def resolve_firebase_credential():
    """Return a credential object suitable for ``firebase_admin.initialize_app()``.

    Uses the same priority chain but returns Firebase-compatible types.
    """
    import firebase_admin.credentials as fb_creds

    # 1. OAuth2 — use RefreshToken (token file is already in the right format)
    if TOKEN_FILE.exists():
        try:
            cred = fb_creds.RefreshToken(str(TOKEN_FILE))
            logger.debug("Using OAuth2 RefreshToken for Firebase")
            return cred
        except Exception as exc:
            logger.warning(f"RefreshToken credential failed: {exc}")

    # 2. Service account
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    sa_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")

    if creds_path:
        return fb_creds.Certificate(creds_path)
    if sa_json:
        return fb_creds.Certificate(json.loads(sa_json))

    # 3. ADC
    return fb_creds.ApplicationDefault()


# ── Legacy helper (keeps old env-var flow working) ───────────────────────

def _load_service_account():
    """Load a service account from env vars (backward compat)."""
    _ensure_gcp_credentials_env()

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        return None

    try:
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(creds_path)
    except Exception:
        return None


def _ensure_gcp_credentials_env():
    """If GCP_SERVICE_ACCOUNT_JSON is set inline, materialise it to a temp
    file so that GOOGLE_APPLICATION_CREDENTIALS-based libraries pick it up."""
    sa_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if sa_json and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        data = json.loads(sa_json)
        path = os.path.join(tempfile.gettempdir(), "gcp_sa_key.json")
        with open(path, "w") as f:
            json.dump(data, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        logger.info(f"Materialised service-account JSON to {path}")
