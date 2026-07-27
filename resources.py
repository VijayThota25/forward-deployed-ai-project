from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CloudResource, CostRecord, Recommendation, RemediationAction, RecommendationStatus, ActionStatus
from app.schemas import SummaryOut

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("/summary", response_model=SummaryOut)
def cost_summary(db: Session = Depends(get_db)):
    resources = db.query(CloudResource).all()
    total_monthly_cost = sum(r.monthly_cost for r in resources)

    cost_by_type: dict[str, float] = defaultdict(float)
    cost_by_region: dict[str, float] = defaultdict(float)
    for r in resources:
        cost_by_type[r.resource_type.value] += r.monthly_cost
        cost_by_region[r.region] += r.monthly_cost

    open_recs = db.query(Recommendation).filter(Recommendation.status == RecommendationStatus.OPEN).all()
    total_potential_savings = sum(rc.estimated_monthly_savings for rc in open_recs)

    realized = (
        db.query(func.sum(RemediationAction.savings_realized_monthly))
        .filter(RemediationAction.status == ActionStatus.COMPLETED)
        .scalar()
        or 0.0
    )

    return SummaryOut(
        total_monthly_cost=round(total_monthly_cost, 2),
        total_potential_savings=round(total_potential_savings, 2),
        total_realized_savings=round(realized, 2),
        open_recommendations=len(open_recs),
        resource_count=len(resources),
        cost_by_type={k: round(v, 2) for k, v in cost_by_type.items()},
        cost_by_region={k: round(v, 2) for k, v in cost_by_region.items()},
    )


@router.get("/trend")
def cost_trend(days: int = 30, db: Session = Depends(get_db)):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    since = today - timedelta(days=days)
    rows = (
        db.query(CostRecord.date, func.sum(CostRecord.daily_cost))
        .filter(CostRecord.date >= since)
        .group_by(CostRecord.date)
        .order_by(CostRecord.date.asc())
        .all()
    )
    return [{"date": d.isoformat(), "total_cost": round(c, 2)} for d, c in rows]
