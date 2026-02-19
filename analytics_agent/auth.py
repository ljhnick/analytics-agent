"""Google OAuth2 browser-based login flow for Desktop / CLI apps."""

import json
import logging

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from analytics_agent.config import TOKEN_FILE, load_tokens, save_tokens, clear_tokens

logger = logging.getLogger(__name__)

# Embedded OAuth2 Desktop Application client (safe to ship in open-source).
# See: https://developers.google.com/identity/protocols/oauth2/native-app
CLIENT_CONFIG = {
    "installed": {
        "client_id": "1057128499704-e64gr7i7j3oh9mjsp7kblfrktibept6d.apps.googleusercontent.com",
        "client_secret": "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",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/firebase",
]


def login() -> Credentials:
    """Run the full OAuth2 browser flow and persist the tokens.

    Opens the user's default browser for Google sign-in.  After consent the
    tokens are saved to ~/.analytics-agent/tokens.json and a Credentials
    object is returned.
    """
    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    creds = flow.run_local_server(
        port=0,  # pick any free port
        prompt="consent",
        success_message="Authentication complete — you can close this tab.",
    )

    _persist(creds)
    logger.info("OAuth2 login successful")
    return creds


def get_credentials() -> Credentials | None:
    """Load stored OAuth2 credentials, refreshing if expired.

    Returns None if no tokens are stored (user hasn't logged in yet).
    """
    token_data = load_tokens()
    if not token_data:
        return None

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes", SCOPES),
    )

    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
        _persist(creds)
        logger.info("OAuth2 token refreshed")

    if not creds.valid:
        logger.warning("Stored OAuth2 tokens are invalid — run `analytics-agent auth login`")
        return None

    return creds


def get_user_email() -> str | None:
    """Return the email of the currently authenticated user, or None."""
    token_data = load_tokens()
    return token_data.get("email") if token_data else None


def logout():
    """Clear stored tokens."""
    clear_tokens()
    logger.info("Logged out")


# ── Internal ─────────────────────────────────────────────────────────────

def _persist(creds: Credentials):
    """Save credentials to disk in a format compatible with both
    google.oauth2.credentials and firebase_admin.credentials.RefreshToken."""
    email = _extract_email(creds)

    token_data = {
        "type": "authorized_user",
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "token": creds.token,
        "token_uri": creds.token_uri,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    if email:
        token_data["email"] = email

    save_tokens(token_data)


def _extract_email(creds: Credentials) -> str | None:
    """Decode email from the ID token if available."""
    try:
        from google.oauth2 import id_token
        from google.auth.transport.requests import Request

        info = id_token.verify_oauth2_token(
            creds.token, Request(), audience=CLIENT_CONFIG["installed"]["client_id"]
        )
        return info.get("email")
    except Exception:
        return None
