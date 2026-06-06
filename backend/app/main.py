import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_db_and_tables
from app.routers.admin import router as admin_router
from app.routers.backup import router as backup_router
from app.routers.emotions import router as emotions_router
from app.routers.import_batches import router as import_batches_router
from app.routers.import_tos import router as import_tos_router
from app.routers.setups import router as setups_router
from app.routers.stats import router as stats_router
from app.routers.summary import router as summary_router
from app.routers.tickers import router as tickers_router
from app.routers.trades import router as trades_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Discipline Tracker API", lifespan=lifespan)
cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
allowed_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(emotions_router)
app.include_router(setups_router)
app.include_router(trades_router)
app.include_router(tickers_router)
app.include_router(summary_router)
app.include_router(stats_router)
app.include_router(import_tos_router)
app.include_router(import_batches_router)
app.include_router(backup_router)
app.include_router(admin_router)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
