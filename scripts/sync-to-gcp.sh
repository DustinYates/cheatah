#!/bin/bash
# Sync code from local Mac to GCP Vertex AI Workbench instance
# Usage: ./scripts/sync-to-gcp.sh [options]
#   -w: Watch mode - continuously sync on file changes
#   -n: Sync notebooks only
#   -c: Sync code only (exclude notebooks)

set -e

# Configuration - UPDATE THESE
GCP_INSTANCE_NAME="${GCP_INSTANCE_NAME:-your-notebook-instance}"
GCP_ZONE="${GCP_ZONE:-us-central1-a}"
GCP_PROJECT="${GCP_PROJECT:-your-project-id}"
REMOTE_PATH="${REMOTE_PATH:-/home/jupyter/chattercheatah}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default options
WATCH_MODE=false
NOTEBOOKS_ONLY=false
CODE_ONLY=false

# Parse arguments
while getopts "wnc" opt; do
  case $opt in
    w) WATCH_MODE=true ;;
    n) NOTEBOOKS_ONLY=true ;;
    c) CODE_ONLY=true ;;
    \?) echo "Invalid option -$OPTARG" >&2; exit 1 ;;
  esac
done

echo -e "${BLUE}=== Chatter Cheetah GCP Sync ===${NC}"
echo -e "Instance: ${GREEN}${GCP_INSTANCE_NAME}${NC}"
echo -e "Zone: ${GREEN}${GCP_ZONE}${NC}"
echo -e "Remote: ${GREEN}${REMOTE_PATH}${NC}"

# Build exclude list
EXCLUDES=(
  --exclude='.git'
  --exclude='__pycache__'
  --exclude='*.pyc'
  --exclude='.venv'
  --exclude='venv'
  --exclude='.env'
  --exclude='.env.local'
  --exclude='*.db'
  --exclude='*.sqlite'
  --exclude='*.log'
  --exclude='.DS_Store'
  --exclude='cloud-sql-proxy'
  --exclude='.pytest_cache'
  --exclude='.ipynb_checkpoints'
  --exclude='*.egg-info'
  --exclude='dist'
  --exclude='build'
  --exclude='.uv'
  --exclude='uv.lock'
)

# Add notebook or code excludes based on flags
if [ "$NOTEBOOKS_ONLY" = true ]; then
  echo -e "${YELLOW}Syncing notebooks only${NC}"
  INCLUDES=(--include='notebooks/***' --exclude='*')
elif [ "$CODE_ONLY" = true ]; then
  echo -e "${YELLOW}Syncing code only (excluding notebooks)${NC}"
  EXCLUDES+=(--exclude='notebooks')
fi

# Function to perform sync
do_sync() {
  echo -e "${BLUE}Syncing files...${NC}"

  # First ensure remote directory exists
  gcloud compute ssh "${GCP_INSTANCE_NAME}" \
    --zone="${GCP_ZONE}" \
    --project="${GCP_PROJECT}" \
    --command="mkdir -p ${REMOTE_PATH}"

  # Create a wrapper script for SSH via gcloud
  SSH_WRAPPER=$(mktemp)
  cat > "$SSH_WRAPPER" <<'EOF'
#!/bin/bash
exec gcloud compute ssh "$GCP_INSTANCE_NAME" --zone="$GCP_ZONE" --project="$GCP_PROJECT" -- "$@"
EOF
  chmod +x "$SSH_WRAPPER"

  # Export vars for the wrapper script
  export GCP_INSTANCE_NAME GCP_ZONE GCP_PROJECT

  # Use rsync with the wrapper script
  # Note: The ":" prefix is needed but the host is ignored (wrapper handles connection)
  rsync -avz --delete \
    "${EXCLUDES[@]}" \
    "${INCLUDES[@]}" \
    -e "$SSH_WRAPPER" \
    ./ ":${REMOTE_PATH}/"

  # Cleanup
  rm "$SSH_WRAPPER"

  echo -e "${GREEN}✓ Sync complete!${NC}"
  echo -e "${BLUE}Remote path: ${REMOTE_PATH}${NC}"
}

# Watch mode using fswatch (Mac) or inotifywait (Linux)
watch_and_sync() {
  echo -e "${YELLOW}Watching for changes... (Ctrl+C to stop)${NC}"

  # Initial sync
  do_sync

  # Check if fswatch is installed (Mac)
  if command -v fswatch &> /dev/null; then
    fswatch -o -r \
      --exclude='\.git' \
      --exclude='__pycache__' \
      --exclude='\.venv' \
      --exclude='\.env' \
      --exclude='\.pytest_cache' \
      --exclude='\.ipynb_checkpoints' \
      --exclude='\.DS_Store' \
      . | while read; do
        echo -e "\n${YELLOW}Change detected...${NC}"
        do_sync
      done
  else
    echo -e "${YELLOW}fswatch not found. Install with: brew install fswatch${NC}"
    echo "Falling back to manual sync mode"
    do_sync
  fi
}

# Main execution
if [ "$WATCH_MODE" = true ]; then
  watch_and_sync
else
  do_sync
fi
