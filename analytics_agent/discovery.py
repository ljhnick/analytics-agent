"""Auto-discover GA4 properties and Firebase projects the user has access to."""

import logging

import requests

logger = logging.getLogger(__name__)


def list_ga4_properties(credentials) -> list[dict]:
    """Return a list of GA4 properties the user can access.

    Each item: {"account_name", "account_id", "property_name", "property_id"}.
    Uses the GA4 Admin API (analyticsadmin.googleapis.com).
    """
    try:
        from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
        from google.analytics.admin_v1beta.types import ListAccountSummariesRequest

        client = AnalyticsAdminServiceClient(credentials=credentials)
        summaries = client.list_account_summaries(ListAccountSummariesRequest())

        results = []
        for account in summaries:
            for prop in account.property_summaries:
                prop_id = prop.property.replace("properties/", "")
                results.append({
                    "account_name": account.display_name,
                    "account_id": account.account.replace("accounts/", ""),
                    "property_name": prop.display_name,
                    "property_id": prop_id,
                })
        return results

    except Exception as e:
        logger.error(f"Failed to list GA4 properties: {e}")
        return []


def list_firebase_projects(credentials) -> list[dict]:
    """Return a list of Firebase projects the user can access.

    Each item: {"project_id", "display_name"}.
    Uses the Firebase Management REST API.
    """
    try:
        from google.auth.transport.requests import Request

        if credentials.expired:
            credentials.refresh(Request())

        resp = requests.get(
            "https://firebase.googleapis.com/v1beta1/projects",
            headers={"Authorization": f"Bearer {credentials.token}"},
            params={"pageSize": 100},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for proj in data.get("results", []):
            results.append({
                "project_id": proj.get("projectId", ""),
                "display_name": proj.get("displayName", proj.get("projectId", "")),
            })
        return results

    except Exception as e:
        logger.error(f"Failed to list Firebase projects: {e}")
        return []
