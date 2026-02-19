"""CLI entry-point for analytics-agent.

Commands:
    analytics-agent setup          Full guided wizard
    analytics-agent auth login     Google OAuth2 login
    analytics-agent auth logout    Clear stored tokens
    analytics-agent auth status    Show current auth state
    analytics-agent config show    Print saved config
    analytics-agent clean          Remove all stored config and tokens
"""

import argparse
import json
import logging
import sys

from analytics_agent import __version__
from analytics_agent.config import (
    CONFIG_FILE,
    TOKEN_FILE,
    clear_config,
    clear_tokens,
    load_config,
    update_config,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="analytics-agent",
        description="Connect to GA4, Firebase & PostgreSQL with one Google login.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    sub = parser.add_subparsers(dest="command")

    # ── setup ────────────────────────────────────────────────────────────
    sub.add_parser("setup", help="Guided first-time setup wizard")

    # ── auth ─────────────────────────────────────────────────────────────
    auth_parser = sub.add_parser("auth", help="Manage Google authentication")
    auth_sub = auth_parser.add_subparsers(dest="auth_command")
    auth_sub.add_parser("login", help="Sign in with Google")
    auth_sub.add_parser("logout", help="Clear stored tokens")
    auth_sub.add_parser("status", help="Show current auth state")

    # ── config ───────────────────────────────────────────────────────────
    config_parser = sub.add_parser("config", help="View saved configuration")
    config_sub = config_parser.add_subparsers(dest="config_command")
    config_sub.add_parser("show", help="Print current config")

    # ── clean ────────────────────────────────────────────────────────────
    sub.add_parser("clean", help="Remove all stored config and tokens")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )
    # Quiet noisy libraries unless in verbose mode
    if not args.verbose:
        for name in ("urllib3", "google", "google_auth_oauthlib", "googleapiclient"):
            logging.getLogger(name).setLevel(logging.WARNING)

    if args.command == "setup":
        _cmd_setup()
    elif args.command == "auth":
        if args.auth_command == "login":
            _cmd_auth_login()
        elif args.auth_command == "logout":
            _cmd_auth_logout()
        elif args.auth_command == "status":
            _cmd_auth_status()
        else:
            auth_parser.print_help()
    elif args.command == "config":
        if args.config_command == "show":
            _cmd_config_show()
        else:
            config_parser.print_help()
    elif args.command == "clean":
        _cmd_clean()
    else:
        parser.print_help()


# ═════════════════════════════════════════════════════════════════════════
# Command implementations
# ═════════════════════════════════════════════════════════════════════════

def _cmd_auth_login():
    from analytics_agent.auth import login, get_user_email

    print("\nOpening browser for Google sign-in...\n")
    creds = login()
    email = get_user_email() or "(unknown)"
    print(f"\n  Authenticated as {email}\n")
    return creds


def _cmd_auth_logout():
    from analytics_agent.auth import logout

    logout()
    clear_config()
    print("Logged out — tokens and config cleared.\n")


def _cmd_auth_status():
    from analytics_agent.auth import get_credentials, get_user_email

    creds = get_credentials()
    if creds is None:
        print("Not logged in.  Run:  analytics-agent auth login\n")
        return

    email = get_user_email() or "(unknown)"
    valid = "valid" if creds.valid else "expired"
    print(f"  Signed in as:  {email}")
    print(f"  Token status:  {valid}")
    print(f"  Token file:    {TOKEN_FILE}\n")


def _cmd_clean():
    import questionary
    from analytics_agent.config import CONFIG_DIR, clean_all

    confirm = questionary.confirm(
        f"This will delete all config and tokens in {CONFIG_DIR}. Continue?",
        default=False,
    ).ask()
    if not confirm:
        print("  Aborted.\n")
        return
    clean_all()
    print("  All config and tokens removed.\n")


def _cmd_config_show():
    cfg = load_config()
    if not cfg:
        print("No config saved yet.  Run:  analytics-agent setup\n")
        return
    print(json.dumps(cfg, indent=2))


def _cmd_setup():
    import questionary
    from analytics_agent.auth import get_credentials, get_user_email

    print("\n" + "=" * 56)
    print("  Analytics Agent — First-Time Setup")
    print("=" * 56 + "\n")

    # ── Step 1: Auth ─────────────────────────────────────────────────────
    creds = get_credentials()

    if creds is not None:
        email = get_user_email() or "(unknown)"
        cfg = load_config()
        print(f"  Already signed in as {email}")

        existing = []
        if cfg.get("ga4", {}).get("property_id"):
            existing.append(f"GA4: {cfg['ga4'].get('property_name', cfg['ga4']['property_id'])}")
        if cfg.get("firebase", {}).get("project_id"):
            existing.append(f"Firebase: {cfg['firebase'].get('display_name', cfg['firebase']['project_id'])}")
        if cfg.get("database", {}).get("connection_string"):
            existing.append("Database: configured")

        if existing:
            print("  Current config:")
            for item in existing:
                print(f"    - {item}")
            print()

        reuse = questionary.confirm(
            "Use existing login and config?", default=True
        ).ask()

        if reuse:
            print("  Keeping existing setup.\n")
            reconfigure = questionary.confirm(
                "Re-select GA4 property, Firebase project, or database?", default=False
            ).ask()
            if reconfigure:
                _setup_ga4(creds)
                _setup_firebase(creds)
                _setup_database()
            print("\n" + "=" * 56)
            print("  Setup complete!")
            print(f"  Config saved to {CONFIG_FILE}")
            print("=" * 56 + "\n")
            return
        else:
            print("  Clearing existing config and tokens...\n")
            clear_tokens()
            clear_config()
            creds = None

    if creds is None:
        creds = _cmd_auth_login()

    if creds is None:
        print("Authentication failed — cannot continue.\n")
        sys.exit(1)

    # ── Step 2: GA4 ──────────────────────────────────────────────────────
    _setup_ga4(creds)

    # ── Step 3: Firebase ─────────────────────────────────────────────────
    _setup_firebase(creds)

    # ── Step 4: Database ─────────────────────────────────────────────────
    _setup_database()

    # ── Done ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 56)
    print("  Setup complete!")
    print(f"  Config saved to {CONFIG_FILE}")
    print("=" * 56 + "\n")


# ── GA4 setup ────────────────────────────────────────────────────────────

def _setup_ga4(creds):
    print("-" * 40)
    print("  Step 2: Google Analytics 4")
    print("-" * 40 + "\n")

    from analytics_agent.discovery import list_ga4_properties

    print("  Discovering GA4 properties...\n")
    props = list_ga4_properties(creds)

    if not props:
        print("  No GA4 properties found for your account.")
        prop_id = input("  Enter a GA4 property ID manually (or press Enter to skip): ").strip()
        if prop_id:
            update_config("ga4", {"property_id": prop_id, "property_name": "(manual)"})
            print(f"  GA4 property saved: {prop_id}\n")
        else:
            print("  Skipping GA4 setup.\n")
        return

    import questionary

    choices = [
        questionary.Choice(
            title=f"{p['property_name']}  (ID: {p['property_id']}, Account: {p['account_name']})",
            value=i,
        )
        for i, p in enumerate(props)
    ]
    choices.append(questionary.Choice(title="Skip", value=-1))

    idx = questionary.select("Select a GA4 property:", choices=choices).ask()
    if idx is None or idx == -1:
        print("  Skipping GA4 setup.\n")
        return

    selected = props[idx]

    update_config("ga4", {
        "property_id": selected["property_id"],
        "property_name": selected["property_name"],
        "account_name": selected["account_name"],
    })
    print(f"\n  GA4 property saved: {selected['property_name']} ({selected['property_id']})\n")


# ── Firebase setup ───────────────────────────────────────────────────────

def _setup_firebase(creds):
    print("-" * 40)
    print("  Step 3: Firebase")
    print("-" * 40 + "\n")

    from analytics_agent.discovery import list_firebase_projects

    print("  Discovering Firebase projects...\n")
    projects = list_firebase_projects(creds)

    if not projects:
        print("  No Firebase projects found for your account.")
        project_id = input("  Enter a Firebase project ID manually (or press Enter to skip): ").strip()
        if project_id:
            update_config("firebase", {"project_id": project_id, "display_name": "(manual)"})
            print(f"  Firebase project saved: {project_id}\n")
        else:
            print("  Skipping Firebase setup.\n")
        return

    import questionary

    choices = [
        questionary.Choice(
            title=f"{p['display_name']}  (ID: {p['project_id']})",
            value=i,
        )
        for i, p in enumerate(projects)
    ]
    choices.append(questionary.Choice(title="Skip", value=-1))

    idx = questionary.select("Select a Firebase project:", choices=choices).ask()
    if idx is None or idx == -1:
        print("  Skipping Firebase setup.\n")
        return

    selected = projects[idx]

    update_config("firebase", {
        "project_id": selected["project_id"],
        "display_name": selected["display_name"],
    })
    print(f"\n  Firebase project saved: {selected['display_name']} ({selected['project_id']})\n")


# ── Database setup ───────────────────────────────────────────────────────

def _setup_database():
    print("-" * 40)
    print("  Step 4: PostgreSQL Database")
    print("-" * 40 + "\n")

    print("  Enter a PostgreSQL connection string.")
    print("  Examples:")
    print("    Neon:     postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require")
    print("    Supabase: postgresql://postgres:pass@db.xxx.supabase.co:5432/postgres")
    print("    Local:    postgresql://user:pass@localhost:5432/mydb")
    print()

    import questionary

    conn_string = questionary.text(
        "Connection string (or Enter to skip):",
    ).ask()
    if not conn_string:
        print("  Skipping database setup.\n")
        return

    # Quick connectivity test
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(conn_string)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        print("  Connection test: OK")
    except Exception as e:
        print(f"  Connection test: FAILED ({e})")
        proceed = questionary.confirm("Save anyway?", default=False).ask()
        if not proceed:
            print("  Skipping database setup.\n")
            return

    update_config("database", {"connection_string": conn_string})
    print("  Database connection saved.\n")


if __name__ == "__main__":
    main()
