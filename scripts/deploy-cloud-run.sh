#!/bin/bash
# Deploy to Cloud Run
# This script builds and deploys your FastAPI app to Cloud Run

set -e

# Configuration - UPDATE THESE
GCP_PROJECT="${GCP_PROJECT:-your-project-id}"
SERVICE_NAME="${SERVICE_NAME:-chattercheatah}"
REGION="${REGION:-us-central1}"
IMAGE_NAME="gcr.io/${GCP_PROJECT}/${SERVICE_NAME}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}=== Deploying to Cloud Run ===${NC}"
echo -e "Project: ${GREEN}${GCP_PROJECT}${NC}"
echo -e "Service: ${GREEN}${SERVICE_NAME}${NC}"
echo -e "Region: ${GREEN}${REGION}${NC}"

# Build the container
echo -e "\n${BLUE}Building container...${NC}"
gcloud builds submit --tag "${IMAGE_NAME}" --project="${GCP_PROJECT}"

# Deploy to Cloud Run
echo -e "\n${BLUE}Deploying to Cloud Run...${NC}"
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_NAME}" \
  --platform=managed \
  --region="${REGION}" \
  --project="${GCP_PROJECT}" \
  --allow-unauthenticated \
  --port=8080 \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --timeout=300

echo -e "\n${GREEN}✓ Deployment complete!${NC}"
gcloud run services describe "${SERVICE_NAME}" \
  --platform=managed \
  --region="${REGION}" \
  --project="${GCP_PROJECT}" \
  --format='value(status.url)'
