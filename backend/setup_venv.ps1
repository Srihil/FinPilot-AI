# FinPilot AI - Backend Virtual Environment Setup (Windows PowerShell)
Write-Host "Setting up FinPilot AI backend virtual environment..." -ForegroundColor Cyan

# Create venv
python -m venv venv
if (-not $?) { Write-Host "ERROR: Python venv creation failed. Is Python 3.10+ installed?" -ForegroundColor Red; exit 1 }

# Activate venv
.\venv\Scripts\Activate.ps1

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
if (-not $?) { Write-Host "ERROR: pip install failed." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "Virtual environment setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To activate the venv in future sessions:" -ForegroundColor Yellow
Write-Host "  cd backend" -ForegroundColor White
Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Copy .env.example to .env and configure DATABASE_URL" -ForegroundColor White
Write-Host "  2. Run: alembic upgrade head" -ForegroundColor White
Write-Host "  3. Run: python -m app.db.seed" -ForegroundColor White
Write-Host "  4. Run: uvicorn app.main:app --reload --port 8000" -ForegroundColor White
