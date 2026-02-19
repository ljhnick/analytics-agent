# Altar Data Schema Reference

## Part 1: PostgreSQL Database

Database: `altar-production` (PostgreSQL)

## Table: `"user"`

Note: Must be quoted in SQL as `"user"` (reserved word). Primary key is `userid` (not `id`).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `userid` | varchar | NO | — | Primary key (Firebase-style UID) |
| `data` | jsonb | YES | — | Arbitrary user data. Contains `signupTracker` for ad-sourced users, `webOnboarding` for web flow state |
| `created_at` | timestamptz | NO | now() | Account creation time |
| `updated_at` | timestamptz | NO | now() | Last update time |
| `onboarding_chat_status` | enum | NO | `not_started` | Values: `not_started`, `asked_job`, `step_3`, `completed` |
| `onboarding_status` | enum | NO | `not_started` | Values: `not_started`, `initialized`, `completed` |
| `onboarding_suggestions` | jsonb | YES | — | |
| `onboarding_context` | jsonb | YES | — | See structure below |
| `onboarding_task_specific_context` | jsonb | YES | — | |
| `onboarding_follow_up_questions` | jsonb | YES | — | Usually `[]` for completed users |
| `onboarding_space_id` | varchar | YES | — | Space created during onboarding |
| `onboarding_chat_node` | enum | NO | `start_node` | Values: `start_node`, `initial_greeting_node`, `quick_context_node`, `search_goal_selection_node`, `end_node` |
| `onboarding_usecase` | enum | YES | — | Values: `meeting_preparation`, `research`, `marketing_campaign`, `design` |

### `data` JSONB structure

```json
{"signupTracker": "hero-banner"}        // ad-sourced user
{"webOnboarding": "intro_video"}         // web onboarding state
{"onboarding": "add_to_space"}           // legacy onboarding state
```

### `onboarding_context` JSONB structure

```json
{
  "spaceId": "uuid",
  "selectedModuleId": "",
  "conversationHistory": [
    "Agent: {\"type\":\"onboarding_usecase\",\"text\":\"...\",\"options\":[...]}",
    "User: Research",
    "Agent: {\"type\":\"onboarding_options\",\"text\":\"...\"}"
  ],
  "quickContextQuestions": [
    {"question": "What specific area...", "answer": "...", "isAnswered": true}
  ]
}
```

## Table: `module`

~25,000+ rows. Each row = one AI interaction/task created by a user.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | uuid | NO | Primary key |
| `userid` | varchar | — | FK to user.userid |
| `threadid` | uuid | — | Conversation thread |
| `action` | text | — | User prompt/action text |
| `created_at` | timestamptz | — | |
| `updated_at` | timestamptz | — | |
| `input_images` | jsonb | — | |
| `output_text` | text | — | AI response |
| `output_images` | jsonb | — | |
| `inventory_item_ids` | jsonb | — | Related inventory items |
| `mode` | text | — | e.g. `auto` |
| `source_item_ids` | jsonb | — | |
| `processStatus` | text | — | |
| `processErrors` | jsonb | — | |
| `model` | text | — | AI model used |
| `module_output_mode` | text | — | e.g. `chat` |
| `duration` | int | — | |
| `isAgenticWorkflow` | bool | — | |
| `source_mode` | text | — | e.g. `auto` |
| `isFullWorkflow` | bool | — | |
| `bookmarked` | bool | — | |
| `isFullModule` | bool | — | |
| `isCancelled` | text | — | |
| `meeting_session_id` | text | — | |

## Table: `inventory`

~56,000+ rows. Each row = a saved item (URL, note, file, etc.).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | uuid | NO | Primary key |
| `userid` | varchar | — | FK to user.userid |
| `type` | text | — | `NOTE`, `URL`, etc. |
| `description` | text | — | |
| `url` | text | YES | |
| `thumbnailurl` | text | YES | |
| `title` | text | YES | |
| `spaceid` | text | YES | |
| `created_at` | timestamptz | — | |
| `updated_at` | timestamptz | — | |
| `processStatus` | text | — | Values include `DONE` |
| `processError` | text | YES | |
| `accessrestriction` | text | — | |
| `fullItem` | bool | — | |

---

## Part 2: Google Analytics 4 (GA4)

Property ID: `515651705` | Measurement ID: `G-83J1ZCGDJR`

Queried via the GA4 Data API using `ga_connection.py`. The API uses dimensions and metrics (not SQL tables).

### Custom Events

These events are pushed from the webapp via Google Tag Manager:

#### `video_play`

Fired when a user starts watching a video.

| Parameter | GA4 Dimension Name | Values |
|---|---|---|
| `video_id` | `customEvent:video_id` | Video identifier string |
| `video_title` | `customEvent:video_title` | Human-readable video title |
| `device` | `customEvent:device` | Device type |

#### `video_progress`

Fired when a user reaches a progress milestone.

| Parameter | GA4 Dimension Name | Values |
|---|---|---|
| `video_id` | `customEvent:video_id` | Video identifier string |
| `video_title` | `customEvent:video_title` | Human-readable video title |
| `video_percent` | `customEvent:video_percent` | `25`, `50`, or `75` |
| `device` | `customEvent:device` | Device type |

#### `video_complete`

Fired when a user watches the video to the end.

| Parameter | GA4 Dimension Name | Values |
|---|---|---|
| `video_id` | `customEvent:video_id` | Video identifier string |
| `video_title` | `customEvent:video_title` | Human-readable video title |
| `device` | `customEvent:device` | Device type |

### Common GA4 Dimensions

| Dimension | Description |
|---|---|
| `date` | Date in YYYYMMDD format (auto-converted to datetime by `ga_connection.py`) |
| `eventName` | Name of the event (e.g. `video_play`, `page_view`, `session_start`) |
| `landingPage` | URL path of the landing page |
| `sessionSource` | Traffic source (e.g. `google`, `facebook`, `direct`) |
| `sessionMedium` | Traffic medium (e.g. `cpc`, `organic`, `referral`) |
| `sessionCampaignName` | Campaign name from UTM parameters |
| `sessionDefaultChannelGroup` | Channel grouping (e.g. `Organic Search`, `Paid Social`) |
| `deviceCategory` | `desktop`, `mobile`, or `tablet` |
| `customEvent:*` | Custom event parameters (prefix with `customEvent:`) |

### Common GA4 Metrics

| Metric | Description |
|---|---|
| `eventCount` | Number of times the event was triggered |
| `totalUsers` | Total unique users |
| `newUsers` | First-time users |
| `sessions` | Number of sessions |
| `engagedSessions` | Sessions with engagement (>10s, or conversion, or 2+ page views) |
| `engagementRate` | `engagedSessions / sessions` |
| `bounceRate` | `1 - engagementRate` |
| `averageSessionDuration` | Mean session duration in seconds |
