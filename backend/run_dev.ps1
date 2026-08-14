# FinPilot AI - Start backend dev server (Windows PowerShell)
# Run from the backend directory

if (-not (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Host "Virtual environment not found. Run setup_venv.ps1 first." -ForegroundColor Red
    exit 1
}

.\venv\Scripts\Activate.ps1
Write-Host "Starting FinPilot AI backend on http://localhost:8000" -ForegroundColor Cyan
Write-Host "API docs: http://localhost:8000/api/docs" -ForegroundColor Cyan
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
