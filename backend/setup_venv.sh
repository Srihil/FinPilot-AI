#!/bin/bash
# FinPilot AI - Backend Virtual Environment Setup (Linux/macOS)
set -e

echo "Setting up FinPilot AI backend virtual environment..."

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Virtual environment setup complete!"
echo ""
echo "To activate the venv in future sessions:"
echo "  cd backend && source venv/bin/activate"
echo ""
echo "Next steps:"
echo "  1. cp ../.env.example ../.env  (and configure DATABASE_URL)"
echo "  2. alembic upgrade head"
echo "  3. python -m app.db.seed"
echo "  4. uvicorn app.main:app --reload --port 8000"
