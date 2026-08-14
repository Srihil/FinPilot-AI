# FinPilot AI - Run database migrations (Windows PowerShell)
if (-not (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Host "Virtual environment not found. Run setup_venv.ps1 first." -ForegroundColor Red
    exit 1
}

.\venv\Scripts\Activate.ps1
Write-Host "Running Alembic migrations..." -ForegroundColor Cyan
alembic upgrade head
Write-Host "Seeding demo data..." -ForegroundColor Cyan
python -m app.db.seed
Write-Host "Done!" -ForegroundColor Green
