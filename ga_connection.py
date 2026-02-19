"""
Google Analytics 4 Data API Connection

Provides a GAConnection class that mirrors the pattern of database_connection.py.
Authenticates via service account and queries the GA4 Data API, returning pandas
DataFrames for analysis.

Usage:
    from ga_connection import get_ga_connection

    ga = get_ga_connection()
    ga.connect()

    # Run a report
    df = ga.run_report(
        dimensions=["date", "eventName"],
        metrics=["eventCount"],
        date_range=("2026-02-01", "today"),
    )

    # Video funnel helper
    df = ga.video_funnel(start_date="2026-02-01")
"""

import os
import json
import tempfile
import logging
from datetime import date, timedelta

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "515651705")


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
# GAConnection
# ---------------------------------------------------------------------------
class GAConnection:
    """Thin wrapper around the GA4 Data API (v1beta).

    Mirrors the interface of DatabaseConnection so the two can be used
    interchangeably in analysis scripts.
    """

    def __init__(self, property_id: str | None = None):
        self.property_id = property_id or DEFAULT_PROPERTY_ID
        self.property_path = f"properties/{self.property_id}"
        self.client = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        """Authenticate and create the BetaAnalyticsDataClient."""
        try:
            _ensure_gcp_credentials()
            from google.analytics.data_v1beta import BetaAnalyticsDataClient

            self.client = BetaAnalyticsDataClient()
            logger.info(
                f"Connected to GA4 Data API (property {self.property_id})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to connect to GA4 Data API: {e}")
            return False

    # ------------------------------------------------------------------
    # Core query
    # ------------------------------------------------------------------
    def run_report(
        self,
        dimensions: list[str],
        metrics: list[str],
        date_range: tuple[str, str] = ("30daysAgo", "today"),
        dimension_filter=None,
        metric_filter=None,
        order_bys=None,
        limit: int = 10_000,
        keep_empty_rows: bool = False,
    ) -> pd.DataFrame | None:
        """Run a GA4 Data API report and return a pandas DataFrame.

        Parameters
        ----------
        dimensions : list[str]
            GA4 dimension names, e.g. ["date", "eventName", "customEvent:video_id"]
        metrics : list[str]
            GA4 metric names, e.g. ["eventCount", "totalUsers"]
        date_range : tuple[str, str]
            (start_date, end_date).  Accepts "today", "yesterday", "NdaysAgo",
            or "YYYY-MM-DD" strings.
        dimension_filter : FilterExpression, optional
            A google.analytics.data_v1beta.types.FilterExpression object.
        metric_filter : FilterExpression, optional
        order_bys : list[OrderBy], optional
        limit : int
            Max rows to return (API max is 100 000 per request).
        keep_empty_rows : bool

        Returns
        -------
        pd.DataFrame or None
        """
        if not self.client:
            if not self.connect():
                return None

        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            RunReportRequest,
        )

        request = RunReportRequest(
            property=self.property_path,
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[
                DateRange(start_date=date_range[0], end_date=date_range[1])
            ],
            limit=limit,
            keep_empty_rows=keep_empty_rows,
        )
        if dimension_filter:
            request.dimension_filter = dimension_filter
        if metric_filter:
            request.metric_filter = metric_filter
        if order_bys:
            request.order_bys = order_bys

        try:
            response = self.client.run_report(request)
        except Exception as e:
            logger.error(f"GA4 API error: {e}")
            return None

        # Parse response into a DataFrame
        rows_data = []
        dim_headers = [h.name for h in response.dimension_headers]
        met_headers = [h.name for h in response.metric_headers]
        for row in response.rows:
            record = {}
            for i, dv in enumerate(row.dimension_values):
                record[dim_headers[i]] = dv.value
            for i, mv in enumerate(row.metric_values):
                record[met_headers[i]] = mv.value
            rows_data.append(record)

        df = pd.DataFrame(rows_data)

        # Auto-convert numeric metric columns
        for col in met_headers:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Auto-convert 'date' dimension (YYYYMMDD) to datetime
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")

        logger.info(
            f"GA4 report returned {len(df)} rows "
            f"({len(dim_headers)} dims, {len(met_headers)} metrics)"
        )
        return df

    # ------------------------------------------------------------------
    # Filter helpers
    # ------------------------------------------------------------------
    @staticmethod
    def filter_by_event_name(event_name: str):
        """Return a dimension filter that matches a single eventName."""
        from google.analytics.data_v1beta.types import (
            Filter,
            FilterExpression,
        )

        return FilterExpression(
            filter=Filter(
                field_name="eventName",
                string_filter=Filter.StringFilter(value=event_name),
            )
        )

    @staticmethod
    def filter_by_event_names(event_names: list[str]):
        """Return a dimension filter that matches any of the given eventNames."""
        from google.analytics.data_v1beta.types import (
            Filter,
            FilterExpression,
            FilterExpressionList,
        )

        return FilterExpression(
            or_group=FilterExpressionList(
                expressions=[
                    FilterExpression(
                        filter=Filter(
                            field_name="eventName",
                            string_filter=Filter.StringFilter(value=name),
                        )
                    )
                    for name in event_names
                ]
            )
        )

    # ------------------------------------------------------------------
    # Convenience report methods
    # ------------------------------------------------------------------
    def event_counts(
        self,
        start_date: str = "30daysAgo",
        end_date: str = "today",
    ) -> pd.DataFrame | None:
        """Get event counts grouped by eventName."""
        return self.run_report(
            dimensions=["eventName"],
            metrics=["eventCount"],
            date_range=(start_date, end_date),
        )

    def events_by_date(
        self,
        event_names: list[str] | None = None,
        start_date: str = "30daysAgo",
        end_date: str = "today",
    ) -> pd.DataFrame | None:
        """Get daily event counts, optionally filtered to specific events."""
        dim_filter = (
            self.filter_by_event_names(event_names) if event_names else None
        )
        return self.run_report(
            dimensions=["date", "eventName"],
            metrics=["eventCount", "totalUsers"],
            date_range=(start_date, end_date),
            dimension_filter=dim_filter,
        )

    def video_funnel(
        self,
        start_date: str = "30daysAgo",
        end_date: str = "today",
    ) -> pd.DataFrame | None:
        """Get video engagement funnel: play -> progress (25/50/75) -> complete.

        Returns a DataFrame with columns:
            date, eventName, customEvent:video_id, customEvent:video_title,
            eventCount, totalUsers
        Plus customEvent:video_percent and customEvent:device if those
        custom dimensions are registered in the GA4 property.
        """
        video_events = ["video_play", "video_progress", "video_complete"]

        # Try with all custom dimensions first; fall back if not registered
        full_dims = [
            "date",
            "eventName",
            "customEvent:video_id",
            "customEvent:video_title",
            "customEvent:video_percent",
            "customEvent:device",
        ]
        df = self.run_report(
            dimensions=full_dims,
            metrics=["eventCount", "totalUsers"],
            date_range=(start_date, end_date),
            dimension_filter=self.filter_by_event_names(video_events),
        )
        if df is not None:
            return df

        # Fallback: drop custom dimensions that may not be registered yet
        logger.warning(
            "Retrying video_funnel without custom event parameters "
            "(they may not be registered as GA4 custom dimensions yet)"
        )
        return self.run_report(
            dimensions=["date", "eventName"],
            metrics=["eventCount", "totalUsers"],
            date_range=(start_date, end_date),
            dimension_filter=self.filter_by_event_names(video_events),
        )

    def video_funnel_summary(
        self,
        start_date: str = "30daysAgo",
        end_date: str = "today",
    ) -> pd.DataFrame | None:
        """Summarised video funnel: total plays, progress milestones, completions.

        Returns a single-row-per-event summary suitable for funnel charts.
        """
        video_events = ["video_play", "video_progress", "video_complete"]

        # Try with video_percent first for detailed breakdown
        df = self.run_report(
            dimensions=["eventName", "customEvent:video_percent"],
            metrics=["eventCount", "totalUsers"],
            date_range=(start_date, end_date),
            dimension_filter=self.filter_by_event_names(video_events),
        )

        has_percent = df is not None and not df.empty

        if not has_percent:
            # Fallback without video_percent
            logger.warning(
                "customEvent:video_percent not available; "
                "falling back to eventName-only summary"
            )
            df = self.run_report(
                dimensions=["eventName"],
                metrics=["eventCount", "totalUsers"],
                date_range=(start_date, end_date),
                dimension_filter=self.filter_by_event_names(video_events),
            )

        if df is None or df.empty:
            return df

        # Build a clean funnel label
        def _label(row):
            name = row["eventName"]
            pct = row.get("customEvent:video_percent", "")
            if name == "video_progress" and pct and pct != "(not set)":
                return f"video_progress_{pct}%"
            return name

        df["funnel_step"] = df.apply(_label, axis=1)

        summary = (
            df.groupby("funnel_step")
            .agg(event_count=("eventCount", "sum"), users=("totalUsers", "sum"))
            .reset_index()
        )

        # Order the funnel logically
        order = [
            "video_play",
            "video_progress_25%",
            "video_progress_50%",
            "video_progress_75%",
            "video_complete",
        ]
        summary["_sort"] = summary["funnel_step"].apply(
            lambda x: order.index(x) if x in order else 99
        )
        summary = summary.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)
        return summary

    def landing_page_report(
        self,
        start_date: str = "30daysAgo",
        end_date: str = "today",
    ) -> pd.DataFrame | None:
        """Get landing page performance: sessions, users, engagement."""
        return self.run_report(
            dimensions=["landingPage", "sessionDefaultChannelGroup"],
            metrics=[
                "sessions",
                "totalUsers",
                "newUsers",
                "bounceRate",
                "averageSessionDuration",
                "engagedSessions",
                "engagementRate",
            ],
            date_range=(start_date, end_date),
        )

    def traffic_sources(
        self,
        start_date: str = "30daysAgo",
        end_date: str = "today",
    ) -> pd.DataFrame | None:
        """Get traffic source breakdown."""
        return self.run_report(
            dimensions=[
                "sessionSource",
                "sessionMedium",
                "sessionCampaignName",
            ],
            metrics=["sessions", "totalUsers", "newUsers", "engagementRate"],
            date_range=(start_date, end_date),
        )

    def device_breakdown(
        self,
        start_date: str = "30daysAgo",
        end_date: str = "today",
    ) -> pd.DataFrame | None:
        """Get sessions/users broken down by device category."""
        return self.run_report(
            dimensions=["deviceCategory"],
            metrics=["sessions", "totalUsers", "newUsers", "engagementRate"],
            date_range=(start_date, end_date),
        )

    # ------------------------------------------------------------------
    # Metadata / exploration
    # ------------------------------------------------------------------
    def get_available_metrics_and_dimensions(self) -> pd.DataFrame | None:
        """Fetch the list of available dimensions and metrics for this property.

        Uses the GA4 Metadata API.  Useful for discovery when building new
        reports.
        """
        if not self.client:
            if not self.connect():
                return None

        from google.analytics.data_v1beta.types import GetMetadataRequest

        try:
            response = self.client.get_metadata(
                GetMetadataRequest(name=f"{self.property_path}/metadata")
            )
        except Exception as e:
            logger.error(f"GA4 Metadata API error: {e}")
            return None

        rows = []
        for d in response.dimensions:
            rows.append(
                {
                    "type": "dimension",
                    "api_name": d.api_name,
                    "ui_name": d.ui_name,
                    "description": d.description,
                    "category": d.category,
                    "custom": d.custom_definition,
                }
            )
        for m in response.metrics:
            rows.append(
                {
                    "type": "metric",
                    "api_name": m.api_name,
                    "ui_name": m.ui_name,
                    "description": m.description,
                    "category": m.category,
                    "custom": m.custom_definition,
                }
            )
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def close(self):
        """Close the underlying gRPC transport."""
        if self.client:
            self.client.transport.close()
            logger.info("GA4 client closed")


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------
def get_ga_connection(property_id: str | None = None) -> GAConnection:
    """Get a GAConnection instance (mirrors get_db_connection())."""
    return GAConnection(property_id=property_id)
