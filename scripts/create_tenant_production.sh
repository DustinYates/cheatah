#!/bin/bash
# Script to create tenant in production database
# This script retrieves DATABASE_URL from GCP Secret Manager and runs the add_tenant script

set -e

echo "======================================================================"
echo "Creating Tenant in Production Database"
echo "======================================================================"
echo ""

# Get GCP project ID
GCP_PROJECT="${GCP_PROJECT_ID:-900139201687}"

echo "Using GCP Project: $GCP_PROJECT"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI is not installed"
    echo "   Install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n1 &> /dev/null; then
    echo "❌ Error: Not authenticated with gcloud"
    echo "   Run: gcloud auth login"
    exit 1
fi

# Get DATABASE_URL from Secret Manager
echo "Retrieving DATABASE_URL from Secret Manager..."
if DATABASE_URL=$(gcloud secrets versions access latest --secret="database-url" --project="$GCP_PROJECT" 2>/dev/null); then
    echo "✓ Retrieved DATABASE_URL from Secret Manager"
    echo ""
    
    # Export for the Python script
    export DATABASE_URL
    
    # Run the add_tenant script with the provided arguments
    echo "Running add_tenant script with production DATABASE_URL..."
    echo ""
    
    # Pass all arguments to the Python script
    uv run python scripts/add_tenant.py "$@"
else
    echo "❌ Error: Failed to retrieve DATABASE_URL from Secret Manager"
    echo ""
    echo "   Make sure:"
    echo "   1. The secret 'database-url' exists in Secret Manager"
    echo "   2. You have permissions to access it"
    echo "   3. The GCP project ID is correct: $GCP_PROJECT"
    echo ""
    echo "   To create the secret:"
    echo "   gcloud secrets create database-url --data-file=- --project=$GCP_PROJECT"
    echo "   (paste your DATABASE_URL and press Ctrl+D)"
    exit 1
fi

