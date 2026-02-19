---
name: analytics-agent
description: Query Google Analytics 4, Firebase Authentication, and PostgreSQL databases using the analytics-agent package. Use when asked to analyze website traffic, user signups, engagement funnels, video events, landing page performance, traffic sources, campaign ROI, Firebase auth users, daily active users, retention, or any data analysis involving these three sources. Triggers on keywords like GA4, Google Analytics, Firebase, signups, funnel, conversion, traffic, sessions, bounce rate, engagement, page views, DAU, retention, or database queries.
---

# Analytics Agent

Connect to **Google Analytics 4**, **Firebase Auth**, and **PostgreSQL** to analyze data. All authentication is handled via Google OAuth2 — no service accounts or API keys needed.

## Prerequisites

If not already set up, run the one-time setup:

```bash
uv run analytics-agent setup
```

This opens a browser for Google sign-in, auto-discovers GA4 properties and Firebase projects, and saves a database connection string. Config is stored in `~/.analytics-agent/`.

If a connection fails with an authentication error (expired or revoked token), re-login:

```bash
uv run analytics-agent auth login
```

Other auth commands:

| Command | Description |
|---|---|
| `uv run analytics-agent auth login` | Re-authenticate with Google |
| `uv run analytics-agent auth logout` | Clear stored tokens |
| `uv run analytics-agent auth status` | Check current auth state |

## Connecting to Data Sources

### Google Analytics 4

```python
from analytics_agent.connections import get_ga_connection

ga = get_ga_connection()
ga.connect()

# Run any GA4 report (returns pandas DataFrame)
df = ga.run_report(
    dimensions=["date", "eventName"],
    metrics=["eventCount", "totalUsers"],
    date_range=("2026-02-01", "today"),
)

ga.close()
```

The GA4 property ID is loaded automatically from saved config.

### Firebase Authentication

```python
from analytics_agent.connections import get_firebase_connection

fb = get_firebase_connection()
fb.connect()

df = fb.list_users()           # All users as DataFrame
real = fb.list_real_users()    # Excludes test accounts
test = fb.list_test_users()    # Only test accounts

summary = fb.signup_summary(since="2026-02-01")
daily = fb.daily_signups(since="2026-02-01")

user = fb.get_user_by_email("someone@example.com")

fb.close()
```

Test account domains can be configured in `analytics_agent/connections/firebase.py` via the `TEST_EMAIL_DOMAINS` list.

### PostgreSQL

```python
from analytics_agent.connections import get_db_connection

db = get_db_connection()
db.connect()
df = db.execute_query("SELECT * FROM users LIMIT 10")
db.close()
```

**Note:** The `execute_query` method with `params` uses list-style params. Use `%%` to escape `%` in LIKE clauses when embedding values directly in SQL strings.

## GA4 Methods Reference

### Core

| Method | Returns | Description |
|---|---|---|
| `ga.connect()` | `bool` | Authenticate with GA4 Data API |
| `ga.run_report(dimensions, metrics, date_range, ...)` | `DataFrame` | Run any arbitrary GA4 report |
| `ga.close()` | — | Close connection |

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
| `ga.filter_by_event_name("event_name")` | Filter to a single event |
| `ga.filter_by_event_names(["event_a", "event_b"])` | Filter to multiple events (OR) |

All date params accept: `"today"`, `"yesterday"`, `"NdaysAgo"`, or `"YYYY-MM-DD"`.

## Firebase Methods Reference

| Method | Returns | Description |
|---|---|---|
| `fb.connect()` | `bool` | Connect to Firebase Admin SDK |
| `fb.list_users(max_results)` | `DataFrame` | All Firebase Auth users |
| `fb.list_real_users(max_results)` | `DataFrame` | Excludes test accounts |
| `fb.list_test_users(max_results)` | `DataFrame` | Only test accounts |
| `fb.get_user_by_email(email)` | `dict` | Look up user by email |
| `fb.get_user_by_uid(uid)` | `dict` | Look up user by UID |
| `fb.signup_summary(since)` | `DataFrame` | Total/real/test user counts |
| `fb.daily_signups(since, exclude_test)` | `DataFrame` | Daily signup counts |
| `fb.close()` | — | Close connection |

**DataFrame columns from `list_users()`:** `uid`, `email`, `display_name`, `phone_number`, `provider_id`, `email_verified`, `disabled`, `created_at`, `last_sign_in`, `is_test_account`

## Database Methods Reference

| Method | Returns | Description |
|---|---|---|
| `db.connect()` | `bool` | Connect to PostgreSQL |
| `db.execute_query(sql, params)` | `DataFrame` | Execute any SQL query |
| `db.get_table_info(table_name)` | `DataFrame` | Schema introspection |
| `db.get_table_sample(table_name, limit)` | `DataFrame` | Sample rows from a table |
| `db.close()` | — | Close connection |

## Common Analysis Patterns

### Discover what's available

```python
# GA4: list all dimensions and metrics
metadata = ga.get_available_metrics_and_dimensions()
custom = metadata[metadata['custom'] == True]

# Database: list all tables
tables = db.get_table_info()

# Database: inspect a specific table's columns
columns = db.get_table_info("my_table")
```

### Cross-source analysis (GA4 + Database)

```python
from analytics_agent.connections import get_ga_connection, get_db_connection
import pandas as pd

ga = get_ga_connection()
ga.connect()
db = get_db_connection()
db.connect()

# GA4: daily sessions
ga_daily = ga.run_report(
    dimensions=["date"],
    metrics=["sessions", "totalUsers"],
    date_range=("2026-02-01", "today"),
)

# Database: daily signups
db_daily = db.execute_query("""
    SELECT DATE(created_at) as date, COUNT(*) as signups
    FROM users
    WHERE created_at >= '2026-02-01'
    GROUP BY DATE(created_at) ORDER BY date
""")

merged = pd.merge(ga_daily, db_daily, on="date", how="outer")
```

### Cross-source analysis (Firebase + Database)

```python
from analytics_agent.connections import get_firebase_connection, get_db_connection
import pandas as pd

fb = get_firebase_connection()
fb.connect()
db = get_db_connection()
db.connect()

fb_users = fb.list_real_users()
db_users = db.execute_query("SELECT id, created_at FROM users")

# Join to enrich database records with Firebase auth data
merged = pd.merge(db_users, fb_users, left_on="id", right_on="uid", how="left")
```

## Common GA4 Dimensions

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

## Common GA4 Metrics

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

## Output Format

Present results as markdown tables. Include:
- Raw counts and percentages
- Conversion rates at each funnel step where relevant
- Comparisons over time
- Key takeaways with actionable insights
