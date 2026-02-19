# Analytics Agent

Connect to **Google Analytics 4**, **Firebase Auth**, and **PostgreSQL** with a single Google login — then use AI (Claude, ChatGPT, etc.) to analyse your data.

No service accounts. No JSON key files. No measurement IDs to hunt down.

## Quick Start

```bash
git clone https://github.com/ljhnick/analytics-agent.git
cd analytics-agent
uv sync
uv run analytics-agent setup
```

> **Don't have `uv`?** Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh`

The setup wizard will:

1. Open your browser for **Google sign-in**
2. Auto-discover your **GA4 properties** — pick one from a list
3. Auto-discover your **Firebase projects** — pick one from a list
4. Ask for a **PostgreSQL connection string** (Neon, Supabase, or any Postgres)

That's it. Configuration is saved to `~/.analytics-agent/` and reused automatically.

## Usage

### With an AI agent (recommended)

After setup, run an AI coding agent in the project folder and start asking questions in natural language. We recommend [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or [OpenCode](https://opencode.ai):

```bash
# Using Claude Code
cd analytics-agent
claude

# Or using OpenCode
cd analytics-agent
opencode
```

Then just ask:

- "How many users signed up this week?"
- "Show me the full funnel from landing page to first purchase"
- "List the top 10 power users and show how they use the app"

The agent reads the skill files in `.claude/skills/` and knows how to connect to your GA4, Firebase, and database automatically — no code needed on your end.

### As a Python library

You can also use the connections directly in Python:

```python
from analytics_agent.connections import get_ga_connection, get_firebase_connection, get_db_connection

ga = get_ga_connection()
ga.connect()
df = ga.video_funnel(start_date="2026-02-01")

fb = get_firebase_connection()
fb.connect()
users = fb.list_real_users()

db = get_db_connection()
db.connect()
data = db.execute_query("SELECT * FROM signups LIMIT 100")
```

## CLI Commands

| Command | Description |
|---|---|
| `uv run analytics-agent setup` | Full guided setup wizard |
| `uv run analytics-agent auth login` | Sign in with Google |
| `uv run analytics-agent auth logout` | Clear stored tokens and config |
| `uv run analytics-agent auth status` | Show auth state |
| `uv run analytics-agent config show` | Print saved config |
| `uv run analytics-agent clean` | Remove all stored config and tokens |

## How It Works

- **OAuth2 Desktop App flow**: the CLI opens your browser for Google sign-in. Tokens are stored locally in `~/.analytics-agent/tokens.json` (file permissions `600`).
- **GA4**: uses the [GA4 Data API](https://developers.google.com/analytics/devguides/reporting/data/v1) with your OAuth2 credentials. The setup wizard uses the GA4 Admin API to list properties you have access to.
- **Firebase**: uses the [Firebase Admin SDK](https://firebase.google.com/docs/admin/setup) with a `RefreshToken` credential derived from your OAuth2 login.
- **PostgreSQL**: connects via a standard connection string you provide (works with Neon, Supabase, Cloud SQL, or any Postgres host).

## Customizing for Your Product

Analytics Agent provides general-purpose connectors. To teach an AI agent about **your specific product** — database schema, funnels, key events, domain concepts — create a product skill using the bundled **skill-creator**.

Just tell the AI agent something like:

> "Create a skill for analyzing user behavior in my app. We track signups through GA4, store user profiles and search history in Postgres, and use Firebase for auth. I want to analyze the full journey: landing page → signup → onboarding → first search."

The agent will use the `skill-creator` skill (at `.claude/skills/skill-creator/`) to generate a well-structured skill file under `.claude/skills/`, capturing your database schema, key funnels, event mappings, and example queries. Once created, the AI agent will automatically read this skill alongside the base analytics-agent skill — so it can answer product-specific questions like "what's our signup-to-activation rate this week?" without you having to explain the schema every time.

## Advanced: Service Account (CI / Automation)

For headless environments, set these environment variables instead of running the setup wizard:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GA4_PROPERTY_ID=123456789
export DB_HOST=... DB_PORT=... DB_USERNAME=... DB_PASSWORD=... DB_NAME=...
```

The credential chain is: **OAuth2 tokens → service account → Application Default Credentials**.

## Requirements

- Python 3.11+
- A Google account with access to your GA4 property and/or Firebase project
- A PostgreSQL database (optional)

## Privacy

See our [Privacy Policy](https://ljhnick.github.io/analytics-agent/privacy.html). Analytics Agent runs entirely on your machine — no data is sent to any third-party server.
