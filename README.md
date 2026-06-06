# Discipline Tracker MVP

Monorepo with:
- `backend/`: FastAPI + SQLite
- `frontend/`: React + Vite + TypeScript

## 5-Minute Local Setup
1. Prerequisites:
   - Python 3.11+
   - Node.js 20+ (includes npm)
2. Create Python env and install backend deps:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r backend\requirements.txt
   pip install -r backend\requirements-dev.txt
   ```
3. Install frontend deps:
   ```powershell
   cd frontend
   npm install
   cd ..
   ```
4. Create backend env file:
   ```powershell
   Copy-Item backend\.env.example backend\.env
   ```
5. Start both services:
   ```powershell
   .\run-dev.ps1
   ```

`run-dev.ps1` starts backend and frontend in separate PowerShell windows.

## Backend Environment Variables
`backend/.env.example` includes:
- `DISCIPLINE_DB_PATH`: SQLite file path (relative to `backend/` if not absolute)
- `BACKEND_PORT`: API port used by `run-dev.ps1`
- `CORS_ORIGINS`: comma-separated allowed frontend origins

Default CORS config allows:
- `http://localhost:5173`
- `http://127.0.0.1:5173`

This prevents CORS errors when using Vite locally.

## Manual Two-Terminal Workflow
If you do not want to use `run-dev.ps1`:

Terminal A (backend):
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --app-dir backend --env-file backend/.env --port 8000
```

Terminal B (frontend):
```powershell
cd frontend
npm run dev
```

## Verify App
- Frontend: open the Vite URL (usually `http://localhost:5173`)
- Backend health: `http://127.0.0.1:8000/health`

## Backend Tests
```powershell
.\.venv\Scripts\python -m pytest backend\tests -q
```

## Formatting and Linting
Backend (ruff):
```powershell
.\.venv\Scripts\python -m ruff check backend
.\.venv\Scripts\python -m ruff format backend
```

Frontend (eslint + prettier):
```powershell
cd frontend
npm run lint
npm run format
```

## Trade API Quick Examples
List active setups:
```powershell
curl "http://127.0.0.1:8000/api/setups"
```

Create a setup:
```powershell
curl -X POST "http://127.0.0.1:8000/api/setups" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"BREAKOUT_RETEST\",\"sort_order\":10}"
```

Deactivate a setup (hide from default dropdown list):
```powershell
curl -X PATCH "http://127.0.0.1:8000/api/setups/1" ^
  -H "Content-Type: application/json" ^
  -d "{\"is_active\":false}"
```

List active emotions:
```powershell
curl "http://127.0.0.1:8000/api/emotions"
```

Create an emotion:
```powershell
curl -X POST "http://127.0.0.1:8000/api/emotions" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"PATIENT\",\"sort_order\":10}"
```

Create trade (use valid `setup_id` and `emotion_id`):
```powershell
curl -X POST "http://127.0.0.1:8000/api/trades" ^
  -H "Content-Type: application/json" ^
  -d "{\"date\":\"2026-02-21\",\"ticker\":\"SPY\",\"direction\":\"CALL\",\"entry_price\":1.25,\"exit_price\":1.75,\"quantity\":2,\"setup_id\":1,\"emotion_id\":1,\"rule_followed\":true,\"notes\":\"Clean breakout setup.\"}"
```

List by date:
```powershell
curl "http://127.0.0.1:8000/api/trades?date=2026-02-21"
```

Daily summary:
```powershell
curl "http://127.0.0.1:8000/api/summary/daily?date=2026-02-21"
```

Stats summary (all-time by default when start/end are omitted):
```powershell
curl "http://127.0.0.1:8000/api/stats/summary"
```

Stats summary with date range:
```powershell
curl "http://127.0.0.1:8000/api/stats/summary?start=2026-02-01&end=2026-02-28"
```

Equity curve points for charting (gap days with no trades are omitted in MVP):
```powershell
curl "http://127.0.0.1:8000/api/stats/equity"
```

Equity curve with date range:
```powershell
curl "http://127.0.0.1:8000/api/stats/equity?start=2026-02-01&end=2026-02-28"
```
