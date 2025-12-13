# Notebooks Directory

This directory contains Jupyter notebooks and Python analysis scripts for testing, EDA, and statistics.

## Deployment

Notebooks and scripts run on **Vertex AI Workbench** (managed Jupyter on GCP).

## Setup

1. Create a Vertex AI Workbench instance in your GCP project
2. Clone this repository into the Workbench environment
3. Install dependencies using `uv`:
   ```bash
   uv sync
   ```
4. Configure environment variables (same as main app)

## Usage

### Importing from the App

Notebooks can directly import from the `app/` package:

```python
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.domain.services.conversation_service import ConversationService
from app.llm.gemini_client import GeminiClient
from app.persistence.database import get_db
```

### Shared Utilities

Use `notebooks/utils.py` for common setup:

```python
from notebooks.utils import get_db_session, set_tenant_context

# Set tenant context
set_tenant_context(tenant_id=1)

# Get database session
async with get_db_session() as session:
    # Use repositories or services
    pass
```

### Example Notebooks

- `test_conversation_flow.ipynb` - Test conversation creation and message flow
- `analyze_tenant_usage.ipynb` - EDA on tenant conversation patterns
- `prompt_performance_stats.ipynb` - Analyze prompt composition and LLM response times
- `lead_capture_analysis.ipynb` - Statistics on lead capture patterns

### Example Scripts

- `scripts/daily_stats.py` - Automated daily statistics generation
- `scripts/tenant_health_check.py` - Health analysis per tenant

## Database Access

Workbench instances can access Cloud SQL and Redis via private networking. Use the same connection settings as the main app.

## Dependencies

All app dependencies are available. Additional analysis libraries:
- `pandas` - Data manipulation
- `matplotlib` - Plotting
- `seaborn` - Statistical visualization

Install with:
```bash
uv add pandas matplotlib seaborn
```

