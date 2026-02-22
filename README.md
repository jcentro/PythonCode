# Discipline Tracker MVP

Monorepo with a FastAPI backend and a React + Vite + TypeScript frontend.

## Project Structure
- `backend/`: FastAPI service.
- `frontend/`: React app.

## Backend Setup and Run
1. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -r backend\requirements.txt
   ```
3. Run the API:
   ```powershell
   uvicorn app.main:app --reload --app-dir backend
   ```
4. Health check:
   - Open `http://127.0.0.1:8000/health`
   - Expected response: `{ "ok": true }`

## Frontend Setup and Run
1. Install dependencies:
   ```powershell
   cd frontend
   npm install
   ```
2. Start dev server:
   ```powershell
   npm run dev
   ```
3. Open the shown local URL in your browser.
4. Expected homepage text: `Discipline Tracker`

## Run Both Services
Use two terminals:
1. Terminal A (backend):
   ```powershell
   uvicorn app.main:app --reload --app-dir backend
   ```
2. Terminal B (frontend):
   ```powershell
   cd frontend
   npm run dev
   ```