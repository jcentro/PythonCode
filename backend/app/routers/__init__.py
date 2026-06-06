from app.routers.emotions import router as emotions_router
from app.routers.import_tos import router as import_tos_router
from app.routers.setups import router as setups_router
from app.routers.stats import router as stats_router
from app.routers.summary import router as summary_router
from app.routers.tickers import router as tickers_router
from app.routers.trades import router as trades_router

__all__ = [
    "trades_router",
    "summary_router",
    "setups_router",
    "emotions_router",
    "tickers_router",
    "stats_router",
    "import_tos_router",
]
