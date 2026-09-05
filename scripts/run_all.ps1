Write-Host "Starting RecoverAI stack..." -ForegroundColor Cyan

$ROOT = (Get-Location).Path

Write-Host "Starting Docker (PostgreSQL + Redis)..." -ForegroundColor Yellow
docker compose up -d

Start-Sleep -Seconds 5

Write-Host "Running migrations..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m alembic upgrade head

Write-Host "Starting Celery worker..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT'; .\.venv\Scripts\Activate.ps1; python -m celery -A app.celery_app:celery_app worker --loglevel=info --pool=solo --concurrency=1 -Q recoverai"

Write-Host "Starting outbox dispatcher..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT'; .\.venv\Scripts\Activate.ps1; python scripts/run_outbox_dispatcher.py"

Write-Host "Starting FastAPI..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT'; .\.venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

Write-Host "Starting Streamlit dashboard..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT'; .\.venv\Scripts\Activate.ps1; python -m streamlit run dashboard/Overview.py"

Write-Host ""
Write-Host "All services starting in separate windows." -ForegroundColor Green
Write-Host "Dashboard: http://localhost:8501" -ForegroundColor Green
Write-Host "API Docs:  http://127.0.0.1:8000/docs" -ForegroundColor Green