import os
import pandas as pd
import psycopg2
from sqlalchemy import create_engine
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _ensure_gcp_credentials():
    """If GCP_SERVICE_ACCOUNT_JSON is set (inline JSON), write it to a temp
    file and set GOOGLE_APPLICATION_CREDENTIALS so Google auth picks it up."""
    import json
    import tempfile

    sa_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if sa_json and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        creds = json.loads(sa_json)
        creds_path = os.path.join(tempfile.gettempdir(), "gcp_sa_key.json")
        with open(creds_path, "w") as f:
            json.dump(creds, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        logger.info(f"Wrote GCP SA credentials to {creds_path}")


def _create_cloud_sql_engine():
    """Create a SQLAlchemy engine using Cloud SQL Python Connector.
    
    Used when CLOUD_SQL_INSTANCE env var is set (e.g. in Modal sandbox).
    Connects via the Cloud SQL Admin API — no public IP or proxy needed.
    """
    _ensure_gcp_credentials()

    from google.cloud.sql.connector import Connector

    connector = Connector()
    instance = os.getenv("CLOUD_SQL_INSTANCE")  # e.g. "project:region:instance"
    user = os.getenv("DB_USERNAME")
    password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    def getconn():
        return connector.connect(
            instance,
            "pg8000",
            user=user,
            password=password,
            db=db_name,
        )

    engine = create_engine("postgresql+pg8000://", creator=getconn)
    logger.info(f"Created Cloud SQL engine for instance: {instance}")
    return engine


def _create_direct_engine():
    """Create a SQLAlchemy engine using a direct psycopg2 connection string.
    
    Used for local development with port-forwarded database.
    """
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
        self.host = os.getenv('DB_HOST')
        self.port = os.getenv('DB_PORT')
        self.username = os.getenv('DB_USERNAME')
        self.database = os.getenv('DB_NAME')
        self.password = os.getenv('DB_PASSWORD')
        self.connection = None
        self.engine = None
        
    def connect(self):
        """Establish connection to PostgreSQL database.
        
        Auto-detects mode:
          - If CLOUD_SQL_INSTANCE is set, uses cloud-sql-python-connector + pg8000
          - Otherwise, uses psycopg2 direct connection (for local port-forward)
        """
        try:
            cloud_sql_instance = os.getenv("CLOUD_SQL_INSTANCE")

            if cloud_sql_instance:
                self.engine = _create_cloud_sql_engine()
            else:
                self.engine = _create_direct_engine()
            
            logger.info("Successfully connected to the database")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return False
    
    def execute_query(self, query, params=None):
        """Execute a SQL query and return results as pandas DataFrame"""
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
    
    def get_table_info(self, table_name=None):
        """Get information about tables in the database"""
        try:
            if table_name:
                query = """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = %s
                ORDER BY ordinal_position;
                """
                return self.execute_query(query, params=[table_name])
            else:
                query = """
                SELECT table_name, table_type
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
                """
                return self.execute_query(query)
                
        except Exception as e:
            logger.error(f"Error getting table info: {e}")
            return None
    
    def get_table_sample(self, table_name, limit=10):
        """Get a sample of data from a specific table"""
        try:
            query = f"SELECT * FROM {table_name} LIMIT %s"
            return self.execute_query(query, params=[limit])
            
        except Exception as e:
            logger.error(f"Error getting table sample: {e}")
            return None
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

# Convenience function to get a database connection
def get_db_connection():
    """Get a database connection instance"""
    return DatabaseConnection()
