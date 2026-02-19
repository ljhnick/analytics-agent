# GA4 Event Schema for Altar AI

Property ID: `515651705` | Measurement ID: `G-83J1ZCGDJR`

## Custom Events (pushed via GTM)

### `video_play`

Fired when a user starts watching a video.

| Parameter | GA4 Dimension | Example Values |
|---|---|---|
| `video_id` | `customEvent:video_id` | `"hero-video"` |
| `video_title` | `customEvent:video_title` | `"Altar AI Demo"` |
| `device` | `customEvent:device` | `"desktop"`, `"mobile"` |

### `video_progress`

Fired when a user reaches a progress milestone during video playback.

| Parameter | GA4 Dimension | Example Values |
|---|---|---|
| `video_id` | `customEvent:video_id` | `"hero-video"` |
| `video_title` | `customEvent:video_title` | `"Altar AI Demo"` |
| `video_percent` | `customEvent:video_percent` | `"25"`, `"50"`, `"75"` |
| `device` | `customEvent:device` | `"desktop"`, `"mobile"` |

### `video_complete`

Fired when a user watches the video to the end.

| Parameter | GA4 Dimension | Example Values |
|---|---|---|
| `video_id` | `customEvent:video_id` | `"hero-video"` |
| `video_title` | `customEvent:video_title` | `"Altar AI Demo"` |
| `device` | `customEvent:device` | `"desktop"`, `"mobile"` |

### Other Custom Events

| Event | Description | Key Parameters |
|---|---|---|
| `section_view` | User viewed a landing page section | `section_id` |
| `button_click` | User clicked a CTA button | — |
| `signup_success` | User completed email signup | — |
| `google_signup_success` | User completed Google OAuth signup | — |
| `login_button_click` | User clicked login button | — |

## Standard GA4 Events

| Event | Description |
|---|---|
| `page_view` | Page was loaded/viewed |
| `session_start` | A new session began |
| `first_visit` | User's first visit ever |
| `scroll` | User scrolled >=90% of the page |
| `user_engagement` | App/page was in foreground for >=1 second |

## Video Funnel Order

```
video_play  ->  video_progress (25%)  ->  video_progress (50%)  ->  video_progress (75%)  ->  video_complete
```

Each step is a strict subset of the previous. Measure drop-off between each stage.

## Dimension Reference

### Standard Dimensions

| API Name | Description | Example |
|---|---|---|
| `date` | Date (YYYYMMDD, auto-converted) | `20260214` |
| `eventName` | Event name | `video_play` |
| `landingPage` | Landing page path | `/`, `/create-account` |
| `pagePath` | Current page path | `/`, `/pricing` |
| `sessionSource` | Traffic source | `google`, `facebook` |
| `sessionMedium` | Traffic medium | `cpc`, `organic`, `referral` |
| `sessionCampaignName` | UTM campaign | `spring_launch` |
| `sessionDefaultChannelGroup` | Channel group | `Paid Search`, `Direct` |
| `deviceCategory` | Device type | `desktop`, `mobile`, `tablet` |
| `country` | Country name | `United States` |
| `city` | City name | `San Francisco` |
| `browser` | Browser name | `Chrome`, `Safari` |
| `operatingSystem` | OS | `Windows`, `Macintosh`, `iOS` |

### Custom Dimensions (prefix: `customEvent:`)

| API Name | Scope | Description |
|---|---|---|
| `customEvent:video_id` | Event | Identifies which video |
| `customEvent:video_title` | Event | Human-readable video name |
| `customEvent:video_percent` | Event | Progress milestone (25/50/75) |
| `customEvent:device` | Event | Device from video event |
| `customEvent:section_id` | Event | Landing page section identifier |

## Metric Reference

| API Name | Description |
|---|---|
| `eventCount` | Number of event fires |
| `totalUsers` | Unique user count |
| `newUsers` | First-time users |
| `sessions` | Session count |
| `engagedSessions` | Sessions with >10s, conversion, or 2+ pageviews |
| `engagementRate` | engagedSessions / sessions |
| `bounceRate` | 1 - engagementRate |
| `averageSessionDuration` | Mean seconds per session |
| `screenPageViews` | Page view count |
| `conversions` | Conversion events |
| `userEngagementDuration` | Total engagement time (seconds) |
