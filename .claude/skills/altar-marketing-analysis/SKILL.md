---
name: altar-marketing-analysis
description: Analyze Altar AI marketing and user acquisition data from PostgreSQL, Google Analytics 4, and Firebase Authentication. Use when asked to query signups, onboarding funnels, conversion rates, ad campaign performance, signup tracker analysis, DAU, retention, marketing funnel optimization, video engagement, landing page analytics, traffic sources, or Firebase user verification. Triggers on requests involving marketing metrics, acquisition channels, campaign ROI, GA4 events, video funnel analysis, Firebase auth users, or filtering test accounts.
---

# Altar Marketing Data Analysis

Analyze marketing and user acquisition data from the Altar AI production PostgreSQL database, Google Analytics 4 (GA4) Data API, **and** Firebase Authentication. This project supports both local development (port-forward) and remote execution in Modal sandbox with OpenCode.

## Environment Setup

### Local mode (with port-forward)

1. Activate the virtualenv: `source venv/bin/activate`
2. Database credentials are in `.env` (loaded automatically by `database_connection.py`)
3. Connection: PostgreSQL at `127.0.0.1:9998` (port-forwarded from production)

### Modal sandbox mode (OpenCode)

1. Set up the virtual environment using uv: `uv venv && source .venv/bin/activate && uv pip install -r requirements.txt`
2. Set `CLOUD_SQL_INSTANCE` env var (e.g. `your-project:your-region:your-instance`)
3. Set `DB_USERNAME`, `DB_PASSWORD`, `DB_NAME` env vars
4. Set `GOOGLE_APPLICATION_CREDENTIALS` to the service account key path
5. The `database_connection.py` auto-detects Cloud SQL mode` and uses `cloud-sql-python-connector`

### Common usage — PostgreSQL

```python
import sys
sys.path.insert(0, '.')
from database_connection import get_db_connection

db = get_db_connection()
db.connect()
df = db.execute_query("SELECT ...")
db.close()
```

**Important:** The `execute_query` method with `params` uses list-style params, but parameterized queries with `%s` can cause SQLAlchemy errors. Prefer embedding safe values directly in SQL strings. Use `%%` to escape `%` in LIKE clauses.

### Common usage — Google Analytics 4

```python
import sys
sys.path.insert(0, '.')
from ga_connection import get_ga_connection

ga = get_ga_connection()
ga.connect()

# Run any GA4 report (returns pandas DataFrame)
df = ga.run_report(
    dimensions=["date", "eventName"],
    metrics=["eventCount", "totalUsers"],
    date_range=("2026-02-01", "today"),
)

# Convenience methods
events_df = ga.event_counts()
video_df = ga.video_funnel_summary()
landing_df = ga.landing_page_report()
traffic_df = ga.traffic_sources()

ga.close()
```

**Auth:** Uses the same GCP service account (`altards-background-agent@...`). Credentials are resolved from `GCP_SERVICE_ACCOUNT_JSON` in `.env` or `GOOGLE_APPLICATION_CREDENTIALS` env var. The GA4 property ID is set via `GA4_PROPERTY_ID` in `.env` (default: `515651705`).

### Common usage — Firebase Authentication

```python
import sys
sys.path.insert(0, '.')
from firebase_connection import get_firebase_connection

fb = get_firebase_connection()
fb.connect()

# All users as DataFrame
df = fb.list_users()

# Only real users (excludes @altar.inc test accounts)
real = fb.list_real_users()

# Only internal test accounts
test = fb.list_test_users()

# Summary stats
summary = fb.signup_summary(since="2026-02-01")

# Daily signups (excluding test accounts)
daily = fb.daily_signups(since="2026-02-01")

# Look up a specific user
user = fb.get_user_by_email("someone@example.com")

fb.close()
```

**Auth:** Reuses the same GCP service account. The service account needs the **Firebase Authentication Admin** role (or `firebaseauth.users.get` + `firebaseauth.users.list` permissions).

**Test account filtering:** Emails ending with `@altar.inc` are automatically flagged as `is_test_account=True`. Edit the `TEST_EMAIL_DOMAINS` list in `firebase_connection.py` to add more internal domains.

## Database Schema

See `references/schema.md` for full table schemas and column details.

Key tables: `"user"` (quoted — reserved word), `module`, `inventory`.

**IMPORTANT — The `"user"` table does NOT have an `email` column.** It only stores `userid` (which corresponds to the Firebase Auth UID). To get a user's email address, you **must** look up the `userid` in Firebase Authentication. Any query that needs to filter or display user emails requires joining PostgreSQL data with Firebase Auth data in Python:

```python
from database_connection import get_db_connection
from firebase_connection import get_firebase_connection

db = get_db_connection()
db.connect()
pg_users = db.execute_query('SELECT userid, created_at FROM "user" WHERE ...')
db.close()

fb = get_firebase_connection()
fb.connect()
fb_users = fb.list_users()  # returns DataFrame with uid, email, is_test_account, etc.
fb.close()

import pandas as pd
merged = pd.merge(pg_users, fb_users[['uid', 'email', 'is_test_account']],
                  left_on='userid', right_on='uid', how='left')

# Filter external vs internal users
external = merged[merged['is_test_account'] == False]
internal = merged[merged['is_test_account'] == True]
```

This applies to any request involving: filtering by email domain (e.g. excluding `@altar.inc`), listing user emails, counting external vs internal users, or any email-based analysis.

## Common Analysis Workflows

### 1. Signup & Acquisition Analysis

Filter real users (from ads/organic) vs test agents using the `data` JSONB column:

```sql
-- Real users have signupTracker in their data
SELECT * FROM "user"
WHERE created_at >= '2026-02-11'
AND data IS NOT NULL
AND data::text LIKE '%%signupTracker%%'
```

Extract tracker source: `data->>'signupTracker'` (values: `hero-banner`, `navbar`, `customers`, `interest-desktop-app`, `accordion-2-button`).

### 2. Onboarding Funnel Analysis

Key columns on `"user"` table:
- `onboarding_status`: `not_started` | `initialized` | `completed`
- `onboarding_usecase`: `meeting_preparation` | `research` | `marketing_campaign` | `design` | NULL
- `onboarding_chat_node`: tracks where user stopped — `start_node` → `initial_greeting_node` → `quick_context_node` → `search_goal_selection_node` → `end_node`
- `onboarding_chat_status`: `not_started` | `asked_job` | `step_3` | `completed`
- `onboarding_context`: JSONB with `spaceId`, `selectedModuleId`, `conversationHistory` (array of `"Agent: ..."` / `"User: ..."` strings), `quickContextQuestions` (array of `{question, answer, isAnswered}`)

Funnel query pattern:

```sql
SELECT
    COUNT(*) as total_signups,
    SUM(CASE WHEN onboarding_usecase IS NOT NULL THEN 1 ELSE 0 END) as chose_usecase,
    SUM(CASE WHEN onboarding_status = 'completed' THEN 1 ELSE 0 END) as completed_onboarding,
    SUM(CASE WHEN onboarding_chat_node = 'initial_greeting_node' THEN 1 ELSE 0 END) as dropped_at_greeting,
    SUM(CASE WHEN onboarding_chat_node = 'quick_context_node' THEN 1 ELSE 0 END) as reached_context,
    SUM(CASE WHEN onboarding_chat_node = 'end_node' THEN 1 ELSE 0 END) as reached_end
FROM "user"
WHERE created_at >= '2026-02-11'
AND data IS NOT NULL AND data::text LIKE '%%signupTracker%%'
```

### 3. Engagement Quality from Onboarding Context

Parse `onboarding_context` JSONB in Python to categorize user engagement:

```python
ctx = row['onboarding_context']  # dict with conversationHistory
history = ctx.get('conversationHistory', [])
user_msgs = [m for m in history if isinstance(m, str) and m.startswith('User:')]
```

Categorize into: no interaction, gibberish, usecase-only click, meaningful input, skip onboarding.

### 4. DAU & Retention

A "daily active user" = user who created a module OR created an inventory item with `processStatus='DONE'` on that day.

```sql
-- Module-based DAU
SELECT DATE(created_at) as day, COUNT(DISTINCT userid) as dau
FROM module GROUP BY DATE(created_at)

-- Combined DAU (modules + inventory)
SELECT day, COUNT(DISTINCT userid) as dau FROM (
    SELECT DATE(created_at) as day, userid FROM module
    UNION
    SELECT DATE(created_at) as day, userid FROM inventory WHERE "processStatus" = 'DONE'
) combined GROUP BY day ORDER BY day
```

### 5. Post-Onboarding Product Usage

Join `"user"` with `module` to measure actual product usage:

```sql
SELECT u.onboarding_status, u.onboarding_usecase,
    COUNT(DISTINCT u.userid) as users, COUNT(m.id) as total_modules
FROM "user" u
LEFT JOIN module m ON u.userid = m.userid
WHERE u.created_at >= '2026-02-11'
GROUP BY u.onboarding_status, u.onboarding_usecase
```

### 6. Tracker Source Conversion

Cross-tabulate signup source against funnel metrics:

```sql
SELECT data->>'signupTracker' as tracker, COUNT(*) as total,
    SUM(CASE WHEN onboarding_usecase IS NOT NULL THEN 1 ELSE 0 END) as chose_usecase,
    SUM(CASE WHEN onboarding_status = 'completed' THEN 1 ELSE 0 END) as completed,
    ROUND(SUM(CASE WHEN onboarding_status = 'completed' THEN 1 ELSE 0 END)::numeric / COUNT(*)::numeric * 100, 1) as completed_pct
FROM "user"
WHERE created_at >= '2026-02-11'
AND data IS NOT NULL AND data::text LIKE '%%signupTracker%%'
GROUP BY data->>'signupTracker' ORDER BY total DESC
```

## Google Analytics 4 Workflows

The GA4 Data API provides website analytics data (traffic, engagement, video events) that complements the PostgreSQL product data. Use `ga_connection.py` for all GA4 queries.

### 7. Video Engagement Funnel

The webapp tracks three custom events via GTM -> GA4: `video_play`, `video_progress` (with `video_percent` = 25, 50, 75), and `video_complete`.

```python
from ga_connection import get_ga_connection
ga = get_ga_connection()
ga.connect()

# Quick summary: plays -> 25% -> 50% -> 75% -> complete
summary = ga.video_funnel_summary(start_date="2026-02-01")
print(summary)
# Columns: funnel_step, event_count, users

# Detailed daily breakdown with video_id / video_title
detail = ga.video_funnel(start_date="2026-02-01")
```

Key analysis patterns:
- **Drop-off rate:** Compare `video_play` users to `video_complete` users
- **Progress milestones:** Where do most viewers stop? (25%, 50%, 75%)
- **Video-to-signup correlation:** Join GA4 video data dates with PostgreSQL signup dates to measure if video viewers convert

### 8. Landing Page Performance

```python
landing = ga.landing_page_report(start_date="2026-02-01")
# Columns: landingPage, sessionDefaultChannelGroup, sessions, totalUsers,
#           newUsers, bounceRate, averageSessionDuration, engagedSessions, engagementRate
```

Key analysis: bounce rate by page, engagement rate by channel, session duration trends.

### 9. Traffic Sources & Campaign Performance

```python
traffic = ga.traffic_sources(start_date="2026-02-01")
# Columns: sessionSource, sessionMedium, sessionCampaignName,
#           sessions, totalUsers, newUsers, engagementRate
```

Cross-reference with PostgreSQL `data->>'signupTracker'` to connect website traffic to actual signups.

### 10. Daily Event Trends

```python
# All events by day
events = ga.events_by_date(start_date="2026-02-01")

# Specific events only
video_events = ga.events_by_date(
    event_names=["video_play", "video_complete"],
    start_date="2026-02-01",
)
```

### 11. Custom GA4 Reports

For any query not covered by convenience methods, use `run_report()` directly:

```python
df = ga.run_report(
    dimensions=["date", "eventName", "customEvent:video_id"],
    metrics=["eventCount", "totalUsers"],
    date_range=("2026-02-01", "today"),
    dimension_filter=ga.filter_by_event_names(["video_play", "video_complete"]),
)
```

Available filter helpers:
- `ga.filter_by_event_name("video_play")` — single event
- `ga.filter_by_event_names(["video_play", "video_complete"])` — multiple events (OR)

For discovering all available dimensions/metrics:
```python
metadata = ga.get_available_metrics_and_dimensions()
# Columns: type, api_name, ui_name, description, category, custom
```

### 12. Cross-Source Analysis (GA4 + PostgreSQL)

Combine GA4 website data with PostgreSQL product data for full-funnel analysis:

```python
from ga_connection import get_ga_connection
from database_connection import get_db_connection

ga = get_ga_connection()
ga.connect()
db = get_db_connection()
db.connect()

# GA4: daily video engagement
video_daily = ga.events_by_date(
    event_names=["video_play", "video_complete"],
    start_date="2026-02-01",
)

# PostgreSQL: daily signups
signups_daily = db.execute_query("""
    SELECT DATE(created_at) as date, COUNT(*) as signups
    FROM "user"
    WHERE created_at >= '2026-02-01'
    AND data IS NOT NULL AND data::text LIKE '%%%%signupTracker%%%%'
    GROUP BY DATE(created_at) ORDER BY date
""")

# Merge on date for correlation analysis
import pandas as pd
merged = pd.merge(video_daily, signups_daily, on="date", how="outer")
```

## Firebase Authentication Workflows

### 13. Firebase User Verification & Test Account Filtering

Check whether signed-up users are real or internal test accounts:

```python
from firebase_connection import get_firebase_connection

fb = get_firebase_connection()
fb.connect()

# Get all users and see the breakdown
df = fb.list_users()
print(f"Total: {len(df)}, Real: {(~df['is_test_account']).sum()}, Test: {df['is_test_account'].sum()}")

# List only the test accounts
test_df = fb.list_test_users()
print(test_df[['email', 'created_at', 'last_sign_in']])
```

### 14. Cross-Source: Firebase Auth + PostgreSQL

Match Firebase Auth users with PostgreSQL `"user"` table to find discrepancies or enrich data. Note: the `"user"` table does **not** have an `email` column — join on `userid` = Firebase `uid` instead:

```python
from firebase_connection import get_firebase_connection
from database_connection import get_db_connection

fb = get_firebase_connection()
fb.connect()
db = get_db_connection()
db.connect()

# Firebase Auth users (email lives here, not in PostgreSQL)
fb_users = fb.list_real_users()

# PostgreSQL users (no email column — only userid)
pg_users = db.execute_query("""
    SELECT userid, created_at, onboarding_status
    FROM "user"
    WHERE created_at >= '2026-02-01'
""")

# Join on userid (PG) = uid (Firebase) to get emails
import pandas as pd
merged = pd.merge(
    pg_users, fb_users,
    left_on="userid", right_on="uid",
    how="outer", indicator=True, suffixes=("_pg", "_firebase")
)
only_firebase = merged[merged["_merge"] == "right_only"]
only_pg = merged[merged["_merge"] == "left_only"]
```

### 15. Firebase Daily Signups vs PostgreSQL Signups

Compare signup counts between the two sources to validate data consistency:

```python
fb_daily = fb.daily_signups(since="2026-02-01", exclude_test=True)
pg_daily = db.execute_query("""
    SELECT DATE(created_at) as date, COUNT(*) as signups
    FROM "user"
    WHERE created_at >= '2026-02-01'
    AND data IS NOT NULL AND data::text LIKE '%%%%signupTracker%%%%'
    GROUP BY DATE(created_at) ORDER BY date
""")

comparison = pd.merge(fb_daily, pg_daily, on="date", how="outer", suffixes=("_firebase", "_pg"))
```

## Output Format

Present results as markdown tables with clear section headers. Include:
- Raw counts and percentages
- Funnel conversion rates at each step
- Breakdowns by signup source and usecase
- Key takeaways highlighting actionable insights
