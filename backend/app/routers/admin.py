from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.emotion_option import EmotionOption
from app.models.import_batch import ImportBatch
from app.models.setup_option import SetupOption
from app.models.trade import Trade
from app.models.trade_fill import TradeFill

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/wipe")
def wipe_all_data(db: Session = Depends(get_db)) -> dict[str, str]:
    with db.begin():
        db.query(TradeFill).delete(synchronize_session=False)
        db.query(Trade).delete(synchronize_session=False)
        db.query(ImportBatch).delete(synchronize_session=False)
        db.query(SetupOption).delete(synchronize_session=False)
        db.query(EmotionOption).delete(synchronize_session=False)

    return {"status": "ok"}
