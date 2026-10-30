# Electronics-store-inventory-management-system
## Development Setup

### Requirements
- Python 3.12 or a compatible supported Python version
- Git

### Installation

macOS/Linux:

    python3 -m venv venv
    source venv/bin/activate

Install dependencies:

    python -m pip install --upgrade pip
    pip install -r requirements.txt

Copy `.env.example` to `.env` and configure local settings.
Keep `.env` private and never commit secrets.

### Run the Application

    python run.py

Open http://127.0.0.1:5000/ in a browser.

### Run Tests

    python -m pytest -v

Tests use temporary SQLite. Set `DATABASE_URL` to the agreed
MySQL connection string when the MySQL environment is ready.
Never commit secrets.

## Daily Database Backups

The application supports automated daily backups of its SQLite database.

### Manual Backup

Run the following command from the project root:

```bash
python scripts/backup_database.py