#!/bin/bash
# Deploy to Cloud Run
# This script builds and deploys your FastAPI app to Cloud Run

set -e

# Configuration - UPDATE THESE
GCP_PROJECT="${GCP_PROJECT:-chatbots-466618}"
SERVICE_NAME="${SERVICE_NAME:-chattercheatah}"
REGION="${REGION:-us-central1}"
REPO_NAME="cloud-run-builds"

# Use Artifact Registry instead of Container Registry (gcr.io is deprecated)
IMAGE_NAME="${REGION}-docker.pkg.dev/${GCP_PROJECT}/${REPO_NAME}/${SERVICE_NAME}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}=== Deploying to Cloud Run ===${NC}"
echo -e "Project: ${GREEN}${GCP_PROJECT}${NC}"
echo -e "Service: ${GREEN}${SERVICE_NAME}${NC}"
echo -e "Region: ${GREEN}${REGION}${NC}"
echo -e "Image: ${GREEN}${IMAGE_NAME}${NC}"

# Ensure Artifact Registry API is enabled and repo exists
echo -e "\n${BLUE}Setting up Artifact Registry...${NC}"
gcloud services enable artifactregistry.googleapis.com --project="${GCP_PROJECT}" 2>/dev/null || true

# Create repository if it doesn't exist
gcloud artifacts repositories create "${REPO_NAME}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${GCP_PROJECT}" \
  --description="Docker images for Cloud Run" 2>/dev/null || echo "Repository already exists"

# Build the container
echo -e "\n${BLUE}Building container...${NC}"
gcloud builds submit --tag "${IMAGE_NAME}" --project="${GCP_PROJECT}"

# Cloud SQL instance (update this if you have one)
CLOUD_SQL_INSTANCE="${CLOUD_SQL_INSTANCE:-}"

# Deploy to Cloud Run
echo -e "\n${BLUE}Deploying to Cloud Run...${NC}"

# Build the deploy command
DEPLOY_CMD="gcloud run deploy ${SERVICE_NAME} \
  --image=${IMAGE_NAME} \
  --platform=managed \
  --region=${REGION} \
  --project=${GCP_PROJECT} \
  --allow-unauthenticated \
  --port=8080 \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=1 \
  --max-instances=10 \
  --timeout=300 \
  --set-env-vars=ENVIRONMENT=production \
  --set-env-vars=GCP_PROJECT_ID=${GCP_PROJECT} \
  --set-env-vars=GCP_REGION=${REGION} \
  --set-env-vars=GEMINI_MODEL=gemini-3-flash-preview \
  --set-env-vars=REDIS_ENABLED=false \
  --set-env-vars=TWILIO_WEBHOOK_URL_BASE=https://${SERVICE_NAME}-900139201687.${REGION}.run.app \
  --set-env-vars=CLOUD_TASKS_WORKER_URL=https://${SERVICE_NAME}-900139201687.${REGION}.run.app/workers \
  --set-secrets=JWT_SECRET_KEY=jwt-secret:latest \
  --set-secrets=GEMINI_API_KEY=gemini-api-key:latest \
  --set-secrets=GMAIL_CLIENT_ID=gmail-client-id:latest \
  --set-secrets=GMAIL_CLIENT_SECRET=gmail-client-secret:latest \
  --set-secrets=FIELD_ENCRYPTION_KEY=field-encryption-key:latest \
  --set-secrets=TELNYX_API_KEY=telnyx-api-key:latest \
  --set-env-vars=GMAIL_OAUTH_REDIRECT_URI=https://${SERVICE_NAME}-900139201687.${REGION}.run.app/api/v1/email/oauth/callback \
  --set-env-vars=GMAIL_PUBSUB_TOPIC=projects/${GCP_PROJECT}/topics/gmail-push-notifications \
  --set-env-vars=GCS_WIDGET_ASSETS_BUCKET=chattercheetah-widget-assets"

# Add Cloud SQL connection if specified
if [ -n "${CLOUD_SQL_INSTANCE}" ]; then
  echo -e "${YELLOW}Using Cloud SQL instance: ${CLOUD_SQL_INSTANCE}${NC}"
  DEPLOY_CMD="${DEPLOY_CMD} \
    --add-cloudsql-instances=${CLOUD_SQL_INSTANCE} \
    --set-env-vars=CLOUD_SQL_INSTANCE_CONNECTION_NAME=${CLOUD_SQL_INSTANCE}"

  # If DATABASE_URL secret exists, use it
  if gcloud secrets describe database-url --project="${GCP_PROJECT}" &>/dev/null; then
    DEPLOY_CMD="${DEPLOY_CMD} --set-secrets=DATABASE_URL=database-url:latest"
  fi
else
  echo -e "${YELLOW}No Cloud SQL instance specified. Set CLOUD_SQL_INSTANCE env var if needed.${NC}"
  # Use DATABASE_URL secret if it exists
  if gcloud secrets describe database-url --project="${GCP_PROJECT}" &>/dev/null; then
    DEPLOY_CMD="${DEPLOY_CMD} --set-secrets=DATABASE_URL=database-url:latest"
  else
    echo -e "${YELLOW}Warning: No DATABASE_URL secret found. App may fail to connect to database.${NC}"
  fi
fi

# Execute the deploy command
eval ${DEPLOY_CMD}

echo -e "\n${GREEN}✓ Deployment complete!${NC}"
gcloud run services describe "${SERVICE_NAME}" \
  --platform=managed \
  --region="${REGION}" \
  --project="${GCP_PROJECT}" \
  --format='value(status.url)'
