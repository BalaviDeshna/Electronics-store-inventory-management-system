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

## Browser Compatibility

The application was manually tested in the following browsers:

| Browser | Version | Result |
|---|---|---|
| Google Chrome | 156.0.8078.79 (64-bit) | Passed |
| Mozilla Firefox | 159.0 | Passed |
| Microsoft Edge | 156.0.4314.50 (64-bit) | Passed |

### Tested Application Flows

The following flows were tested in all three browsers:

- User login.
- Inventory table display.
- Product search and category filtering.
- Dynamically adding another sale item.
- Required-field validation on the sale form.

All tested flows worked as expected in the recorded browser versions.

### Limitations

Compatibility has been verified only for the browser versions listed above and the application flows documented here. Other versions and untested functionality have not been independently verified.
