# Agent Standards

## Formatting
- Python: follow PEP 8 and keep line length near 100 chars.
- TypeScript/React: use strict typing and ES module imports.
- Prefer small, focused functions and files.

## Naming
- Python files and modules: `snake_case`.
- Python classes: `PascalCase`.
- Functions/variables: `snake_case` in Python, `camelCase` in TS.
- React components: `PascalCase`.

## Tests
- Backend tests: place under `backend/tests` using `pytest`.
- Frontend tests: place under `frontend/src` with `*.test.ts(x)` naming.
- Add tests for bug fixes and API behavior changes.

## Run Commands
- Backend setup: `python -m venv .venv` then `.venv\\Scripts\\activate` then `pip install -r backend/requirements.txt`.
- Backend run: `uvicorn app.main:app --reload --app-dir backend`.
- Frontend setup: `cd frontend && npm install`.
- Frontend run: `npm run dev`.