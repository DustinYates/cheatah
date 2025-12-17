#!/bin/bash
# Setup script for GCP sync
# Run this once to configure your environment

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== Chatter Cheetah GCP Sync Setup ===${NC}\n"

# Prompt for GCP configuration
read -p "Enter your GCP Project ID: " GCP_PROJECT
read -p "Enter your Vertex AI Workbench instance name: " GCP_INSTANCE_NAME
read -p "Enter the GCP zone (default: us-central1-a): " GCP_ZONE
GCP_ZONE=${GCP_ZONE:-us-central1-a}
read -p "Enter remote path on instance (default: /home/jupyter/chattercheatah): " REMOTE_PATH
REMOTE_PATH=${REMOTE_PATH:-/home/jupyter/chattercheatah}

# Create .env.sync file
cat > .env.sync <<EOF
# GCP Sync Configuration
export GCP_PROJECT="${GCP_PROJECT}"
export GCP_INSTANCE_NAME="${GCP_INSTANCE_NAME}"
export GCP_ZONE="${GCP_ZONE}"
export REMOTE_PATH="${REMOTE_PATH}"
export SERVICE_NAME="chattercheatah"
export REGION="us-central1"
EOF

echo -e "${GREEN}✓ Created .env.sync${NC}"

# Add to .gitignore if not already there
if ! grep -q ".env.sync" .gitignore 2>/dev/null; then
  echo ".env.sync" >> .gitignore
  echo -e "${GREEN}✓ Added .env.sync to .gitignore${NC}"
fi

# Make scripts executable
chmod +x scripts/sync-to-gcp.sh
chmod +x scripts/pull-notebooks.sh
chmod +x scripts/deploy-cloud-run.sh
echo -e "${GREEN}✓ Made scripts executable${NC}"

# Check for fswatch (for watch mode)
if ! command -v fswatch &> /dev/null; then
  echo -e "\n${YELLOW}⚠ fswatch not installed${NC}"
  echo -e "For watch mode (-w), install with: ${BLUE}brew install fswatch${NC}"
fi

# Check for gcloud
if ! command -v gcloud &> /dev/null; then
  echo -e "\n${RED}✗ gcloud CLI not found${NC}"
  echo -e "Install from: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

# Test gcloud connection
echo -e "\n${BLUE}Testing GCP connection...${NC}"
if gcloud compute instances describe "${GCP_INSTANCE_NAME}" \
  --zone="${GCP_ZONE}" \
  --project="${GCP_PROJECT}" &> /dev/null; then
  echo -e "${GREEN}✓ Successfully connected to ${GCP_INSTANCE_NAME}${NC}"
else
  echo -e "${YELLOW}⚠ Could not connect to instance${NC}"
  echo -e "Make sure you're authenticated: ${BLUE}gcloud auth login${NC}"
fi

echo -e "\n${GREEN}=== Setup Complete! ===${NC}"
echo -e "\nUsage:"
echo -e "  ${BLUE}source .env.sync${NC}                    # Load configuration"
echo -e "  ${BLUE}./scripts/sync-to-gcp.sh${NC}            # One-time sync to GCP"
echo -e "  ${BLUE}./scripts/sync-to-gcp.sh -w${NC}         # Watch mode (auto-sync on changes)"
echo -e "  ${BLUE}./scripts/pull-notebooks.sh${NC}         # Pull notebooks from GCP"
echo -e "  ${BLUE}./scripts/deploy-cloud-run.sh${NC}       # Deploy to Cloud Run"
echo -e "\nAdd to your shell profile (~/.zshrc or ~/.bashrc):"
echo -e "  ${BLUE}source $(pwd)/.env.sync${NC}"
