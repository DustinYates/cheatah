#!/bin/bash
# Script to create tenant in production database using Cloud SQL Proxy
# This requires the Cloud SQL Proxy to be running

set -e

echo "======================================================================"
echo "Creating Tenant in Production Database (using Cloud SQL Proxy)"
echo "======================================================================"
echo ""

# Check if cloud-sql-proxy is available
if [ ! -f "./cloud-sql-proxy" ]; then
    echo "❌ Error: cloud-sql-proxy not found in current directory"
    echo ""
    echo "Please download and set it up:"
    echo "1. Download: https://cloud.google.com/sql/docs/postgres/connect-admin-proxy#install"
    echo "2. Or install via: gcloud components install cloud-sql-proxy"
    echo "3. Place it in the project root as 'cloud-sql-proxy'"
    echo ""
    exit 1
fi

# Get GCP project ID
GCP_PROJECT="${GCP_PROJECT_ID:-900139201687}"

# Extract Cloud SQL instance from DATABASE_URL
# The DATABASE_URL format is: postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/project:region:instance
echo "Retrieving DATABASE_URL from Secret Manager..."
if DATABASE_URL=$(gcloud secrets versions access latest --secret="database-url" --project="$GCP_PROJECT" 2>/dev/null); then
    echo "✓ Retrieved DATABASE_URL from Secret Manager"
    
    # Extract instance connection name
    if [[ $DATABASE_URL =~ host=/cloudsql/([^&]+) ]]; then
        INSTANCE_CONNECTION_NAME="${BASH_REMATCH[1]}"
        echo "Found Cloud SQL instance: $INSTANCE_CONNECTION_NAME"
    else
        echo "❌ Error: Could not extract Cloud SQL instance from DATABASE_URL"
        echo "   DATABASE_URL format should include: host=/cloudsql/project:region:instance"
        exit 1
    fi
else
    echo "❌ Error: Failed to retrieve DATABASE_URL from Secret Manager"
    exit 1
fi

# Start Cloud SQL Proxy in background
echo ""
echo "Starting Cloud SQL Proxy on port 5432..."
./cloud-sql-proxy "$INSTANCE_CONNECTION_NAME" --port=5432 > /tmp/cloud-sql-proxy.log 2>&1 &
PROXY_PID=$!

# Wait for proxy to start
echo "Waiting for proxy to start..."
sleep 3

# Check if proxy is running
if ! ps -p $PROXY_PID > /dev/null; then
    echo "❌ Error: Cloud SQL Proxy failed to start"
    echo "Check /tmp/cloud-sql-proxy.log for details"
    exit 1
fi

echo "✓ Cloud SQL Proxy is running (PID: $PROXY_PID)"
echo ""

# Modify DATABASE_URL to use localhost instead of Unix socket
# Format: postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/project:region:instance
# Convert to: postgresql+asyncpg://user:pass@localhost:5432/dbname
if [[ $DATABASE_URL =~ postgresql\+asyncpg://([^@]+)@/([^?]+)(.*) ]]; then
    USER_PASS="${BASH_REMATCH[1]}"
    DB_NAME="${BASH_REMATCH[2]}"
    LOCAL_DATABASE_URL="postgresql+asyncpg://${USER_PASS}@localhost:5432/${DB_NAME}"
    export DATABASE_URL="$LOCAL_DATABASE_URL"
    echo "Modified DATABASE_URL for local connection"
else
    # Try simple replacement if regex doesn't match
    LOCAL_DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|?host=/cloudsql/[^&]*||' | sed 's|@/|@localhost:5432/|')
    export DATABASE_URL="$LOCAL_DATABASE_URL"
    echo "Using simple URL replacement"
fi

echo "Using modified DATABASE_URL for local connection"
echo ""

# Run the add_tenant script
echo "Running add_tenant script..."
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Stopping Cloud SQL Proxy (PID: $PROXY_PID)..."
    kill $PROXY_PID 2>/dev/null || true
    wait $PROXY_PID 2>/dev/null || true
    echo "✓ Cloud SQL Proxy stopped"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Pass all arguments to the Python script
uv run python scripts/add_tenant.py "$@"

EXIT_CODE=$?
exit $EXIT_CODE

