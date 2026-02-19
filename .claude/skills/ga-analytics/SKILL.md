---
name: ga-analytics
description: Analyze Google Analytics 4 (GA4) website and video engagement data for Altar AI. Use when asked about video watch rates, landing page performance, traffic sources, campaign ROI, bounce rates, session metrics, event tracking, or any GA4-related question. Triggers on keywords like GA, Google Analytics, video funnel, landing page, traffic, sessions, bounce rate, engagement rate, page views, or website analytics.
---

# GA4 Analytics for Altar AI

Query the Google Analytics 4 Data API for the Altar AI website. All queries go through `ga_connection.py` which returns pandas DataFrames.

## Environment Setup

```python
import sys
sys.path.insert(0, '.')
from ga_connection import get_ga_connection

ga = get_ga_connection()
ga.connect()
# ... run queries ...
ga.close()
```

**Auth:** Uses the GCP service account. Credentials resolve automatically from `GCP_SERVICE_ACCOUNT_JSON` in `.env` (inline JSON) or `GOOGLE_APPLICATION_CREDENTIALS` env var. Property ID comes from `GA4_PROPERTY_ID` in `.env` (default: `515651705`).

**Sandbox setup:** `uv venv && source .venv/bin/activate && uv pip install -r requirements.txt`

## GA4 Property Info

| Key | Value |
|---|---|
| Property ID | `515651705` |
| Measurement ID | `G-83J1ZCGDJR` |
| Service Account | `altards-background-agent@bright-drake-427707-t3.iam.gserviceaccount.com` |

## Available Methods on `GAConnection`

### Core

| Method | Returns | Description |
|---|---|---|
| `ga.connect()` | `bool` | Authenticate with GA4 Data API |
| `ga.run_report(dimensions, metrics, date_range, ...)` | `DataFrame` | Run any arbitrary GA4 report |
| `ga.close()` | — | Close gRPC transport |

### Convenience Reports

| Method | Returns | Description |
|---|---|---|
| `ga.event_counts(start_date, end_date)` | `DataFrame` | Event counts grouped by `eventName` |
| `ga.events_by_date(event_names, start_date, end_date)` | `DataFrame` | Daily event counts, optionally filtered |
| `ga.video_funnel(start_date, end_date)` | `DataFrame` | Detailed video events with custom params |
| `ga.video_funnel_summary(start_date, end_date)` | `DataFrame` | Aggregated funnel: play -> 25% -> 50% -> 75% -> complete |
| `ga.landing_page_report(start_date, end_date)` | `DataFrame` | Landing page sessions, bounce rate, engagement |
| `ga.traffic_sources(start_date, end_date)` | `DataFrame` | Source / medium / campaign breakdown |
| `ga.device_breakdown(start_date, end_date)` | `DataFrame` | Desktop vs mobile vs tablet |
| `ga.get_available_metrics_and_dimensions()` | `DataFrame` | Discover all available dims & metrics |

### Filter Helpers

| Method | Description |
|---|---|
| `ga.filter_by_event_name("video_play")` | Filter to a single event |
| `ga.filter_by_event_names(["video_play", "video_complete"])` | Filter to multiple events (OR) |

All `start_date` / `end_date` params accept: `"today"`, `"yesterday"`, `"NdaysAgo"`, or `"YYYY-MM-DD"`.

## Custom Events (pushed via GTM)

The Altar webapp fires these custom events:

### Video Events

| Event | When Fired | Key Parameters |
|---|---|---|
| `video_play` | User starts the video | `video_id`, `video_title`, `device` |
| `video_progress` | User reaches a milestone | `video_id`, `video_title`, `video_percent` (25/50/75), `device` |
| `video_complete` | User finishes the video | `video_id`, `video_title`, `device` |

Custom event parameters are accessed as dimensions with prefix `customEvent:`, e.g. `customEvent:video_id`, `customEvent:video_percent`.

### Other Tracked Events

| Event | Description |
|---|---|
| `page_view` | Standard page view |
| `session_start` | Session begins |
| `first_visit` | First-time visitor |
| `scroll` | User scrolled page |
| `section_view` | User viewed a section of the landing page |
| `button_click` | User clicked a button |
| `signup_success` | User completed email signup |
| `google_signup_success` | User completed Google OAuth signup |
| `login_button_click` | User clicked login |

## Common Analysis Patterns

### 1. Video Engagement Funnel

```python
ga = get_ga_connection()
ga.connect()

# Aggregated funnel
summary = ga.video_funnel_summary(start_date="2026-02-11")
# Columns: funnel_step, event_count, users
# funnel_step values: video_play, video_progress_25%, video_progress_50%, video_progress_75%, video_complete

# Calculate drop-off
if summary is not None and not summary.empty:
    plays = summary.loc[summary['funnel_step'] == 'video_play', 'users'].values
    completes = summary.loc[summary['funnel_step'] == 'video_complete', 'users'].values
    if len(plays) > 0 and len(completes) > 0 and plays[0] > 0:
        completion_rate = completes[0] / plays[0] * 100
        print(f"Completion rate: {completion_rate:.1f}%")
```

### 2. Daily Video Trends

```python
daily = ga.events_by_date(
    event_names=["video_play", "video_progress", "video_complete"],
    start_date="2026-02-11",
)
# Columns: date, eventName, eventCount, totalUsers

# Pivot for a clean daily view
if daily is not None and not daily.empty:
    pivot = daily.pivot_table(
        index='date', columns='eventName',
        values='eventCount', aggfunc='sum', fill_value=0
    )
    print(pivot)
```

### 3. Landing Page Performance

```python
landing = ga.landing_page_report(start_date="2026-02-11")
# Columns: landingPage, sessionDefaultChannelGroup, sessions, totalUsers,
#           newUsers, bounceRate, averageSessionDuration, engagedSessions, engagementRate

# Best performing pages by engagement
if landing is not None and not landing.empty:
    by_page = landing.groupby('landingPage').agg({
        'sessions': 'sum',
        'totalUsers': 'sum',
        'bounceRate': 'mean',
        'engagementRate': 'mean',
    }).sort_values('sessions', ascending=False)
    print(by_page)
```

### 4. Traffic Sources & Campaign Performance

```python
traffic = ga.traffic_sources(start_date="2026-02-11")
# Columns: sessionSource, sessionMedium, sessionCampaignName,
#           sessions, totalUsers, newUsers, engagementRate

# Group by source/medium
if traffic is not None and not traffic.empty:
    by_source = traffic.groupby(['sessionSource', 'sessionMedium']).agg({
        'sessions': 'sum',
        'totalUsers': 'sum',
        'newUsers': 'sum',
        'engagementRate': 'mean',
    }).sort_values('sessions', ascending=False)
    print(by_source)
```

### 5. Device Breakdown

```python
devices = ga.device_breakdown(start_date="2026-02-11")
# Columns: deviceCategory, sessions, totalUsers, newUsers, engagementRate
```

### 6. Signup Conversion from Website

```python
# Get signup events from GA4
signups = ga.events_by_date(
    event_names=["signup_success", "google_signup_success"],
    start_date="2026-02-11",
)
# Columns: date, eventName, eventCount, totalUsers

# Compare with total sessions for conversion rate
all_sessions = ga.run_report(
    dimensions=["date"],
    metrics=["sessions", "totalUsers"],
    date_range=("2026-02-11", "today"),
)
```

### 7. Custom Reports with `run_report()`

For any query not covered by convenience methods:

```python
df = ga.run_report(
    dimensions=["date", "eventName", "customEvent:video_id"],
    metrics=["eventCount", "totalUsers"],
    date_range=("2026-02-11", "today"),
    dimension_filter=ga.filter_by_event_names(["video_play", "video_complete"]),
)
```

### 8. Discover Available Dimensions & Metrics

When you need to explore what's queryable:

```python
metadata = ga.get_available_metrics_and_dimensions()
# Columns: type, api_name, ui_name, description, category, custom

# Find custom dimensions
custom = metadata[metadata['custom'] == True]
print(custom[['type', 'api_name', 'ui_name']])

# Search for specific keywords
video_related = metadata[metadata['api_name'].str.contains('video', case=False)]
```

### 9. Cross-Source Analysis (GA4 + PostgreSQL)

Combine GA4 website data with PostgreSQL product data:

```python
from ga_connection import get_ga_connection
from database_connection import get_db_connection
import pandas as pd

ga = get_ga_connection()
ga.connect()
db = get_db_connection()
db.connect()

# GA4: daily video plays
video_daily = ga.events_by_date(
    event_names=["video_play"],
    start_date="2026-02-11",
)

# PostgreSQL: daily signups (real users only)
signups_daily = db.execute_query("""
    SELECT DATE(created_at) as date, COUNT(*) as signups
    FROM "user"
    WHERE created_at >= '2026-02-11'
    AND data IS NOT NULL AND data::text LIKE '%%%%signupTracker%%%%'
    GROUP BY DATE(created_at) ORDER BY date
""")

# Merge for correlation
merged = pd.merge(video_daily, signups_daily, on="date", how="outer")

ga.close()
db.close()
```

## Common GA4 Dimensions Reference

| Dimension | Description |
|---|---|
| `date` | YYYYMMDD (auto-converted to datetime) |
| `eventName` | Event name |
| `landingPage` | Landing page URL path |
| `sessionSource` | Traffic source (google, facebook, direct) |
| `sessionMedium` | Traffic medium (cpc, organic, referral) |
| `sessionCampaignName` | UTM campaign name |
| `sessionDefaultChannelGroup` | Channel (Organic Search, Paid Social, etc.) |
| `deviceCategory` | desktop, mobile, tablet |
| `country` | User country |
| `city` | User city |
| `customEvent:video_id` | Video identifier |
| `customEvent:video_title` | Video title |
| `customEvent:video_percent` | Video progress milestone (25, 50, 75) |
| `customEvent:device` | Device from video event |

## Common GA4 Metrics Reference

| Metric | Description |
|---|---|
| `eventCount` | Number of event occurrences |
| `totalUsers` | Unique users |
| `newUsers` | First-time users |
| `sessions` | Session count |
| `engagedSessions` | Sessions >10s, or conversion, or 2+ page views |
| `engagementRate` | engagedSessions / sessions |
| `bounceRate` | 1 - engagementRate |
| `averageSessionDuration` | Mean session duration (seconds) |
| `screenPageViews` | Page view count |
| `conversions` | Conversion event count |

## Output Format

Present results as markdown tables. Include:
- Raw counts and percentages
- Funnel conversion rates at each step (e.g. play-to-complete %)
- Comparisons over time where relevant
- Key takeaways with actionable insights
