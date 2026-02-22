from fastapi import FastAPI

app = FastAPI(title="Discipline Tracker API")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}