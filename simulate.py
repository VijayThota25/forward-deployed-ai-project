from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Recommendation, RecommendationStatus, Severity
from app.schemas import RecommendationOut, RemediationActionOut
from app.remediation import execute_remediation, dismiss_recommendation, RemediationError
from app.analyzer import run_analysis

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(
    status_filter: Optional[RecommendationStatus] = None,
    severity: Optional[Severity] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Recommendation).options(joinedload(Recommendation.resource))
    if status_filter:
        q = q.filter(Recommendation.status == status_filter)
    if severity:
        q = q.filter(Recommendation.severity == severity)
    return q.order_by(Recommendation.estimated_monthly_savings.desc()).all()


@router.post("/run-analysis")
def trigger_analysis(db: Session = Depends(get_db)):
    return run_analysis(db)


@router.post("/{recommendation_id}/remediate", response_model=RemediationActionOut)
def remediate(recommendation_id: int, db: Session = Depends(get_db)):
    try:
        return execute_remediation(db, recommendation_id)
    except RemediationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{recommendation_id}/dismiss", response_model=RecommendationOut)
def dismiss(recommendation_id: int, db: Session = Depends(get_db)):
    try:
        return dismiss_recommendation(db, recommendation_id)
    except RemediationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
