"""Google Analytics 4 Data API connection.

Authenticates via the unified credential chain (OAuth2 -> service account ->
ADC) and queries the GA4 Data API, returning pandas DataFrames.

Usage::

    from analytics_agent.connections import get_ga_connection

    ga = get_ga_connection()
    ga.connect()
    df = ga.run_report(
        dimensions=["date", "eventName"],
        metrics=["eventCount"],
        date_range=("2026-02-01", "today"),
    )
"""

import logging
import os

import pandas as pd
from dotenv import load_dotenv

from analytics_agent.config import get_config_value
from analytics_agent.credentials import resolve_credentials

load_dotenv()

logger = logging.getLogger(__name__)


def _resolve_property_id(explicit: str | None = None) -> str:
    """Property ID priority: explicit arg > env var > saved config."""
    if explicit:
        return explicit
    from_env = os.getenv("GA4_PROPERTY_ID")
    if from_env:
        return from_env
    from_cfg = get_config_value("ga4", "property_id")
    if from_cfg:
        return str(from_cfg)
    raise RuntimeError(
        "No GA4 property ID found.  Run `analytics-agent setup` or pass "
        "property_id= explicitly."
    )


class GAConnection:
    """Thin wrapper around the GA4 Data API (v1beta)."""

    def __init__(self, property_id: str | None = None):
        self.property_id = _resolve_property_id(property_id)
        self.property_path = f"properties/{self.property_id}"
        self.client = None

    # ── Connection ───────────────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient

            creds = resolve_credentials()
            self.client = BetaAnalyticsDataClient(credentials=creds)
            logger.info(f"Connected to GA4 Data API (property {self.property_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to GA4 Data API: {e}")
            return False

    # ── Core query ───────────────────────────────────────────────────────

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
        """Run a GA4 Data API report and return a pandas DataFrame."""
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

        for col in met_headers:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")

        logger.info(
            f"GA4 report returned {len(df)} rows "
            f"({len(dim_headers)} dims, {len(met_headers)} metrics)"
        )
        return df

    # ── Filter helpers ───────────────────────────────────────────────────

    @staticmethod
    def filter_by_event_name(event_name: str):
        from google.analytics.data_v1beta.types import Filter, FilterExpression

        return FilterExpression(
            filter=Filter(
                field_name="eventName",
                string_filter=Filter.StringFilter(value=event_name),
            )
        )

    @staticmethod
    def filter_by_event_names(event_names: list[str]):
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

    # ── Convenience reports ──────────────────────────────────────────────

    def event_counts(
        self, start_date: str = "30daysAgo", end_date: str = "today"
    ) -> pd.DataFrame | None:
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
        self, start_date: str = "30daysAgo", end_date: str = "today"
    ) -> pd.DataFrame | None:
        """Video engagement funnel: play -> progress (25/50/75) -> complete."""
        video_events = ["video_play", "video_progress", "video_complete"]

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
        self, start_date: str = "30daysAgo", end_date: str = "today"
    ) -> pd.DataFrame | None:
        """Aggregated video funnel suitable for funnel charts."""
        video_events = ["video_play", "video_progress", "video_complete"]

        df = self.run_report(
            dimensions=["eventName", "customEvent:video_percent"],
            metrics=["eventCount", "totalUsers"],
            date_range=(start_date, end_date),
            dimension_filter=self.filter_by_event_names(video_events),
        )
        has_percent = df is not None and not df.empty

        if not has_percent:
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
        return summary.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)

    def landing_page_report(
        self, start_date: str = "30daysAgo", end_date: str = "today"
    ) -> pd.DataFrame | None:
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
        self, start_date: str = "30daysAgo", end_date: str = "today"
    ) -> pd.DataFrame | None:
        return self.run_report(
            dimensions=["sessionSource", "sessionMedium", "sessionCampaignName"],
            metrics=["sessions", "totalUsers", "newUsers", "engagementRate"],
            date_range=(start_date, end_date),
        )

    def device_breakdown(
        self, start_date: str = "30daysAgo", end_date: str = "today"
    ) -> pd.DataFrame | None:
        return self.run_report(
            dimensions=["deviceCategory"],
            metrics=["sessions", "totalUsers", "newUsers", "engagementRate"],
            date_range=(start_date, end_date),
        )

    # ── Metadata ─────────────────────────────────────────────────────────

    def get_available_metrics_and_dimensions(self) -> pd.DataFrame | None:
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
            rows.append({
                "type": "dimension",
                "api_name": d.api_name,
                "ui_name": d.ui_name,
                "description": d.description,
                "category": d.category,
                "custom": d.custom_definition,
            })
        for m in response.metrics:
            rows.append({
                "type": "metric",
                "api_name": m.api_name,
                "ui_name": m.ui_name,
                "description": m.description,
                "category": m.category,
                "custom": m.custom_definition,
            })
        return pd.DataFrame(rows)

    # ── Teardown ─────────────────────────────────────────────────────────

    def close(self):
        if self.client:
            self.client.transport.close()
            logger.info("GA4 client closed")


def get_ga_connection(property_id: str | None = None) -> GAConnection:
    return GAConnection(property_id=property_id)
