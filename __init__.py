from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CloudResource, CostRecord, ResourceType, ResourceStatus
from app.schemas import ResourceOut, CostRecordOut

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("", response_model=list[ResourceOut])
def list_resources(
    resource_type: Optional[ResourceType] = None,
    status_filter: Optional[ResourceStatus] = Query(None, alias="status"),
    region: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(CloudResource)
    if resource_type:
        q = q.filter(CloudResource.resource_type == resource_type)
    if status_filter:
        q = q.filter(CloudResource.status == status_filter)
    if region:
        q = q.filter(CloudResource.region == region)
    return q.order_by(CloudResource.monthly_cost.desc()).all()


@router.get("/{resource_db_id}", response_model=ResourceOut)
def get_resource(resource_db_id: int, db: Session = Depends(get_db)):
    resource = db.query(CloudResource).filter(CloudResource.id == resource_db_id).first()
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@router.get("/{resource_db_id}/costs", response_model=list[CostRecordOut])
def get_resource_costs(resource_db_id: int, days: int = 30, db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    records = (
        db.query(CostRecord)
        .filter(CostRecord.resource_db_id == resource_db_id, CostRecord.date >= since)
        .order_by(CostRecord.date.asc())
        .all()
    )
    return records
