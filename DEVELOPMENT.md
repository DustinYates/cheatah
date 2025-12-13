# Development Workflow

This guide covers the development workflow for Chatter Cheetah when working between your Mac (using Cursor) and GCP.

## Overview

- **Local Development**: Use Cursor on Mac for code editing and debugging
- **GCP Vertex AI Workbench**: Run and develop Jupyter notebooks
- **GCP Cloud Run**: Deploy the FastAPI application
- **Sync Strategy**: Push code changes to GCP, pull notebook changes back

## Initial Setup

1. **Run the setup script once**:
   ```bash
   ./scripts/setup-sync.sh
   ```

   This will:
   - Prompt for your GCP configuration
   - Create `.env.sync` with your settings
   - Make all scripts executable
   - Test your GCP connection

2. **Load configuration** (add to `~/.zshrc` or `~/.bashrc`):
   ```bash
   source ~/path/to/chattercheatah/.env.sync
   ```

## Daily Workflow

### Option 1: Manual Sync (Simple)

1. **Edit code in Cursor** on your Mac
2. **Push to GCP** when ready to test notebooks or deploy:
   ```bash
   ./scripts/sync-to-gcp.sh
   ```
3. **Work on notebooks** in Vertex AI Workbench
4. **Pull notebooks back** to commit changes:
   ```bash
   ./scripts/pull-notebooks.sh
   git add notebooks/
   git commit -m "Update notebooks"
   ```

### Option 2: Watch Mode (Automatic)

For active development, use watch mode to automatically sync changes:

```bash
./scripts/sync-to-gcp.sh -w
```

This watches for file changes and syncs automatically. Leave it running in a terminal.

**Requirements**: Install `fswatch` first:
```bash
brew install fswatch
```

### Option 3: Git-based Workflow (Traditional)

If you prefer Git:

1. **On Mac**: Commit and push changes
   ```bash
   git add .
   git commit -m "Your changes"
   git push
   ```

2. **On GCP Vertex AI Workbench**: Pull changes
   ```bash
   cd /home/jupyter/chattercheatah
   git pull
   ```

## Sync Options

### Sync Everything
```bash
./scripts/sync-to-gcp.sh
```

### Sync Code Only (exclude notebooks)
```bash
./scripts/sync-to-gcp.sh -c
```

### Sync Notebooks Only
```bash
./scripts/sync-to-gcp.sh -n
```

### Watch Mode (auto-sync on changes)
```bash
./scripts/sync-to-gcp.sh -w
```

### Pull Notebooks from GCP
```bash
./scripts/pull-notebooks.sh
```

## Deployment

### Deploy to Cloud Run

```bash
./scripts/deploy-cloud-run.sh
```

This will:
- Build a container using Cloud Build
- Deploy to Cloud Run
- Output the service URL

### Deploy via Git (Alternative)

If you have Cloud Build triggers set up:

```bash
git push origin main  # Triggers automatic deployment
```

## Recommended Workflow for Different Tasks

### Working on FastAPI Backend
1. Edit code in Cursor
2. Test locally: `uv run uvicorn app.main:app --reload`
3. Run tests: `uv run pytest`
4. When ready to deploy: `./scripts/deploy-cloud-run.sh`

### Working on Notebooks
1. Sync latest code to GCP: `./scripts/sync-to-gcp.sh`
2. Open Vertex AI Workbench
3. Develop/run notebooks on GCP
4. Pull notebooks back: `./scripts/pull-notebooks.sh`
5. Review and commit changes

### Hybrid Development (Code + Notebooks)
1. Start watch mode: `./scripts/sync-to-gcp.sh -w`
2. Edit code in Cursor
3. Changes sync automatically to GCP
4. Test in notebooks on Vertex AI Workbench
5. Pull notebooks periodically: `./scripts/pull-notebooks.sh`

## Tips

### Faster Iteration with Notebooks

If you're heavily iterating on notebooks:
- Keep a terminal with watch mode running
- Make small code changes in Cursor
- Test immediately in your notebook on GCP
- No manual sync needed!

### Testing Before Deployment

Before deploying to Cloud Run:
```bash
# Build and test locally
docker build -t chattercheatah-test .
docker run -p 8080:8080 chattercheatah-test

# Test the endpoint
curl http://localhost:8080/health
```

### Handling .env Files

The sync script excludes `.env` files by default for security.

To sync environment variables:
1. Use GCP Secret Manager (recommended)
2. Manually copy `.env` once:
   ```bash
   gcloud compute scp .env $GCP_INSTANCE_NAME:/home/jupyter/chattercheatah/
   ```

### Debugging Sync Issues

Check what would be synced without actually syncing:
```bash
rsync -avz --dry-run \
  --exclude='.git' --exclude='__pycache__' \
  -e "gcloud compute ssh $GCP_INSTANCE_NAME --zone=$GCP_ZONE --project=$GCP_PROJECT --" \
  ./ :$REMOTE_PATH/
```

## Troubleshooting

### "Command not found: gcloud"
Install the Google Cloud SDK:
- Mac: `brew install google-cloud-sdk`
- Or: https://cloud.google.com/sdk/docs/install

### "Permission denied"
Authenticate with GCP:
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### "Cannot connect to instance"
Make sure your Vertex AI Workbench instance is running:
```bash
gcloud notebooks instances list --location=$GCP_ZONE
```

### Watch mode not working
Install fswatch:
```bash
brew install fswatch
```

## Configuration

All configuration is stored in `.env.sync`:
- `GCP_PROJECT`: Your GCP project ID
- `GCP_INSTANCE_NAME`: Vertex AI Workbench instance name
- `GCP_ZONE`: GCP zone (e.g., us-central1-a)
- `REMOTE_PATH`: Path on the GCP instance
- `SERVICE_NAME`: Cloud Run service name
- `REGION`: Cloud Run region

Edit `.env.sync` to change settings, or re-run `./scripts/setup-sync.sh`.
