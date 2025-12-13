#!/bin/bash
# Pull notebooks from GCP Vertex AI Workbench to local Mac
# This allows you to review notebook changes made on GCP

set -e

# Configuration - UPDATE THESE
GCP_INSTANCE_NAME="${GCP_INSTANCE_NAME:-your-notebook-instance}"
GCP_ZONE="${GCP_ZONE:-us-central1-a}"
GCP_PROJECT="${GCP_PROJECT:-your-project-id}"
REMOTE_PATH="${REMOTE_PATH:-/home/jupyter/chattercheatah}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}=== Pulling Notebooks from GCP ===${NC}"
echo -e "Instance: ${GREEN}${GCP_INSTANCE_NAME}${NC}"

# Pull only notebooks directory
rsync -avz \
  --include='notebooks/***' \
  --exclude='*' \
  --exclude='.ipynb_checkpoints' \
  -e "gcloud compute ssh ${GCP_INSTANCE_NAME} --zone=${GCP_ZONE} --project=${GCP_PROJECT} --" \
  :${REMOTE_PATH}/ ./

echo -e "${GREEN}✓ Notebooks pulled successfully!${NC}"
echo -e "${YELLOW}Review changes and commit if needed${NC}"
