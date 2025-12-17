"""Shared utilities for Vertex AI Workbench notebooks.

This module provides GCP-compatible utilities for data analysis including:
- Cloud SQL database connections (via Cloud SQL Python Connector)
- BigQuery client for analytics
- Async helpers for Jupyter notebooks
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import nest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Apply nest_asyncio to allow async in Jupyter
nest_asyncio.apply()


def get_gcp_project_id() -> str:
    """Get GCP project ID from environment or metadata server."""
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project_id:
        return project_id

    # Try to get from GCP metadata server (works in Vertex AI Workbench)
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"}
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.read().decode()
    except Exception:
        pass

    return "chatbots-466618"  # Default fallback


def create_cloud_sql_engine(
    instance_connection_name: str | None = None,
    database: str | None = None,
    user: str | None = None,
    password: str | None = None,
):
    """Create SQLAlchemy async engine using Cloud SQL Python Connector.

    This is the recommended way to connect from Vertex AI Workbench to Cloud SQL.

    Args:
        instance_connection_name: Cloud SQL instance connection name (project:region:instance)
        database: Database name
        user: Database user
        password: Database password

    Returns:
        AsyncEngine configured for Cloud SQL
    """
    from google.cloud.sql.connector import Connector
    import asyncpg

    instance_connection_name = instance_connection_name or os.environ.get(
        "CLOUD_SQL_INSTANCE_CONNECTION_NAME"
    )
    database = database or os.environ.get("CLOUD_SQL_DATABASE_NAME", "chattercheatah")
    user = user or os.environ.get("DB_USER", "cheatah_user")
    password = password or os.environ.get("DB_PASSWORD")

    connector = Connector()

    async def getconn():
        conn = await connector.connect_async(
            instance_connection_name,
            "asyncpg",
            user=user,
            password=password,
            db=database,
        )
        return conn

    engine = create_async_engine(
        "postgresql+asyncpg://",
        async_creator=getconn,
        echo=False,
    )

    return engine


def create_direct_engine(database_url: str | None = None):
    """Create SQLAlchemy async engine using direct connection string.

    Use this for local development or when DATABASE_URL is set.

    Args:
        database_url: PostgreSQL async connection string

    Returns:
        AsyncEngine configured for direct connection
    """
    database_url = database_url or os.environ.get("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    return create_async_engine(
        database_url,
        echo=False,
        future=True,
    )


def get_engine():
    """Get the appropriate SQLAlchemy engine based on environment.

    Automatically chooses between Cloud SQL Connector and direct connection.
    """
    # Check if we should use Cloud SQL Connector
    instance_name = os.environ.get("CLOUD_SQL_INSTANCE_CONNECTION_NAME")

    if instance_name:
        return create_cloud_sql_engine()
    else:
        return create_direct_engine()


# Create session factory lazily
_session_factory = None


def _get_session_factory():
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for notebooks.

    Usage:
        async with get_db_session() as session:
            result = await session.execute(select(Tenant))
            tenants = result.scalars().all()
    """
    session_factory = _get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


def setup_tenant_context(tenant_id: int | None) -> None:
    """Set tenant context for notebook operations.

    Args:
        tenant_id: Tenant ID to set in context
    """
    from app.core.tenant_context import set_tenant_context
    set_tenant_context(tenant_id)


# BigQuery utilities
def get_bigquery_client():
    """Get a BigQuery client for analytics queries.

    Returns:
        google.cloud.bigquery.Client
    """
    from google.cloud import bigquery

    project_id = get_gcp_project_id()
    return bigquery.Client(project=project_id)


def query_bigquery(query: str, to_dataframe: bool = True):
    """Execute a BigQuery query and optionally return as DataFrame.

    Args:
        query: SQL query string
        to_dataframe: If True, return pandas DataFrame; otherwise return RowIterator

    Returns:
        pandas.DataFrame or BigQuery RowIterator
    """
    client = get_bigquery_client()
    query_job = client.query(query)

    if to_dataframe:
        return query_job.to_dataframe()
    return query_job.result()


def load_dataframe_to_bigquery(
    df,
    table_id: str,
    if_exists: str = "append",
):
    """Load a pandas DataFrame to BigQuery.

    Args:
        df: pandas DataFrame to load
        table_id: Full table ID (project.dataset.table)
        if_exists: What to do if table exists ('append', 'replace', 'fail')
    """
    from google.cloud import bigquery

    client = get_bigquery_client()

    job_config = bigquery.LoadJobConfig()
    if if_exists == "replace":
        job_config.write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE
    elif if_exists == "append":
        job_config.write_disposition = bigquery.WriteDisposition.WRITE_APPEND
    else:
        job_config.write_disposition = bigquery.WriteDisposition.WRITE_EMPTY

    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()  # Wait for job to complete

    return job


# Async helper for notebooks
def run_async(coro):
    """Helper to run async coroutines in Jupyter notebooks.

    Usage:
        df = run_async(fetch_all_tenants())
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


# Cloud Storage utilities
def get_storage_client():
    """Get a Cloud Storage client.

    Returns:
        google.cloud.storage.Client
    """
    from google.cloud import storage
    return storage.Client()


def upload_to_gcs(
    local_path: str,
    bucket_name: str,
    blob_name: str,
):
    """Upload a file to Google Cloud Storage.

    Args:
        local_path: Path to local file
        bucket_name: GCS bucket name
        blob_name: Destination blob name
    """
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)
    return f"gs://{bucket_name}/{blob_name}"


def download_from_gcs(
    bucket_name: str,
    blob_name: str,
    local_path: str,
):
    """Download a file from Google Cloud Storage.

    Args:
        bucket_name: GCS bucket name
        blob_name: Source blob name
        local_path: Destination local path
    """
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(local_path)
    return local_path
