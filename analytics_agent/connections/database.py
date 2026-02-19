"""PostgreSQL database connection.

Supports three modes (auto-detected):
  1. Connection string from ``~/.analytics-agent/config.json`` (new)
  2. Cloud SQL Python Connector (when CLOUD_SQL_INSTANCE is set)
  3. Direct psycopg2 connection (from DB_* env vars)

Usage::

    from analytics_agent.connections import get_db_connection

    db = get_db_connection()
    db.connect()
    df = db.execute_query("SELECT * FROM users LIMIT 10")
"""

import logging
import os

import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

from analytics_agent.config import get_config_value
from analytics_agent.credentials import _ensure_gcp_credentials_env

load_dotenv()

logger = logging.getLogger(__name__)


def _create_engine_from_config():
    """Create engine from the connection string stored during setup."""
    conn_string = get_config_value("database", "connection_string")
    if not conn_string:
        return None
    engine = create_engine(conn_string)
    logger.info("Created engine from saved config")
    return engine


def _create_cloud_sql_engine():
    _ensure_gcp_credentials_env()
    from google.cloud.sql.connector import Connector

    connector = Connector()
    instance = os.getenv("CLOUD_SQL_INSTANCE")
    user = os.getenv("DB_USERNAME")
    password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    def getconn():
        return connector.connect(instance, "pg8000", user=user, password=password, db=db_name)

    engine = create_engine("postgresql+pg8000://", creator=getconn)
    logger.info(f"Created Cloud SQL engine for instance: {instance}")
    return engine


def _create_direct_engine():
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    username = os.getenv("DB_USERNAME")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME")

    conn_string = f"postgresql://{username}:{password}@{host}:{port}/{database}"
    engine = create_engine(conn_string)
    logger.info(f"Created direct engine for {host}:{port}/{database}")
    return engine


class DatabaseConnection:
    def __init__(self):
        self.engine = None

    def connect(self) -> bool:
        """Establish connection to PostgreSQL.

        Priority: saved config > Cloud SQL connector > direct env vars.
        """
        try:
            # 1. Saved connection string from setup wizard
            self.engine = _create_engine_from_config()
            if self.engine:
                logger.info("Connected via saved config")
                return True

            # 2. Cloud SQL connector
            if os.getenv("CLOUD_SQL_INSTANCE"):
                self.engine = _create_cloud_sql_engine()
                logger.info("Connected via Cloud SQL connector")
                return True

            # 3. Direct connection from env vars
            if os.getenv("DB_HOST"):
                self.engine = _create_direct_engine()
                logger.info("Connected via direct connection")
                return True

            logger.error(
                "No database configuration found.  Run `analytics-agent setup` "
                "or set DB_HOST / CLOUD_SQL_INSTANCE env vars."
            )
            return False

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return False

    def execute_query(self, query, params=None) -> pd.DataFrame | None:
        try:
            if not self.engine:
                if not self.connect():
                    return None
            df = pd.read_sql_query(query, self.engine, params=params)
            logger.info(f"Query executed successfully. Returned {len(df)} rows.")
            return df
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return None

    def get_table_info(self, table_name=None) -> pd.DataFrame | None:
        if table_name:
            query = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
            """
            return self.execute_query(query, params=[table_name])
        query = """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
        """
        return self.execute_query(query)

    def get_table_sample(self, table_name, limit=10) -> pd.DataFrame | None:
        query = f"SELECT * FROM {table_name} LIMIT %s"
        return self.execute_query(query, params=[limit])

    def close(self):
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")


def get_db_connection() -> DatabaseConnection:
    return DatabaseConnection()
