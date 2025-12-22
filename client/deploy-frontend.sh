#!/bin/bash
set -e

GCP_PROJECT="${GCP_PROJECT:-chatbots-466618}"
# Explicitly set to frontend service - don't inherit from environment
SERVICE_NAME="chattercheatah-frontend"
REGION="${REGION:-us-central1}"
REPO_NAME="cloud-run-builds"
API_URL="${API_URL:-https://chattercheatah-900139201687.us-central1.run.app}"
IMAGE_NAME="${REGION}-docker.pkg.dev/${GCP_PROJECT}/${REPO_NAME}/${SERVICE_NAME}"

echo "=== Deploying Frontend to Cloud Run ==="
echo "Project: ${GCP_PROJECT}"
echo "Service: ${SERVICE_NAME}"
echo "API URL: ${API_URL}"

gcloud artifacts repositories create "${REPO_NAME}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${GCP_PROJECT}" 2>/dev/null || echo "Repository already exists"

echo "Building container..."
gcloud builds submit --tag "${IMAGE_NAME}" --project="${GCP_PROJECT}"

echo "Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_NAME}" \
  --platform=managed \
  --region="${REGION}" \
  --project="${GCP_PROJECT}" \
  --allow-unauthenticated \
  --port=8080 \
  --memory=256Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5 \
  --set-env-vars="API_URL=${API_URL}"

echo "Frontend URL:"
gcloud run services describe "${SERVICE_NAME}" \
  --platform=managed \
  --region="${REGION}" \
  --project="${GCP_PROJECT}" \
  --format='value(status.url)'
