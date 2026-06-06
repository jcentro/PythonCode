# Agent Standards

## Formatting
- Python: follow PEP 8, keep line length near 100 chars, and use `ruff format`.
- TypeScript/React: use strict typing and ES module imports.
- Prefer small, focused functions and files.
- Frontend formatting: use `prettier`.

## Naming
- Python files and modules: `snake_case`.
- Python classes: `PascalCase`.
- Functions/variables: `snake_case` in Python, `camelCase` in TS.
- React components: `PascalCase`.

## Tests
- Backend tests: place under `backend/tests` using `pytest`.
- Frontend tests: place under `frontend/src` with `*.test.ts(x)` naming.
- Add tests for bug fixes and API behavior changes.

## Linting
- Backend lint: `ruff check backend`.
- Frontend lint: `npm run lint` in `frontend/`.

## Run Commands
- Backend setup: `python -m venv .venv` then `.venv\\Scripts\\activate` then `pip install -r backend/requirements.txt` and `pip install -r backend/requirements-dev.txt`.
- Backend run: `uvicorn app.main:app --reload --app-dir backend --env-file backend/.env --port 8000`.
- Frontend setup: `cd frontend && npm install`.
- Frontend run: `npm run dev`.
