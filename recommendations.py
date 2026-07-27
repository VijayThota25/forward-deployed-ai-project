from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RemediationAction
from app.schemas import RemediationActionOut

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("", response_model=list[RemediationActionOut])
def list_actions(db: Session = Depends(get_db)):
    return db.query(RemediationAction).order_by(RemediationAction.performed_at.desc()).all()
