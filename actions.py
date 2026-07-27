"""
Remediation engine.

Executes the action suggested by a Recommendation against the (simulated)
cloud resource: mutates resource state, records a RemediationAction audit
row, and marks the recommendation REMEDIATED. Since this MVP targets a mock
provider, "executing" an action means updating our own DB state rather than
calling a real cloud API -- but the shape (audit trail, idempotency,
before/after cost delta) mirrors what a real integration would do.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    CloudResource,
    Recommendation,
    RemediationAction,
    ResourceStatus,
    RecommendationStatus,
    ActionType,
    ActionStatus,
)
from app.cli_commands import DOWNSIZE_MAP, build_cli_command

RESIZE_SAVINGS_RATIO = 0.4


class RemediationError(Exception):
    pass


def _apply_action(resource: CloudResource, action: ActionType) -> float:
    """Mutates the resource in place and returns the monthly savings realized."""
    before_cost = resource.monthly_cost

    if action == ActionType.STOP_INSTANCE:
        resource.status = ResourceStatus.STOPPED
        resource.avg_cpu_utilization = 0.0
        resource.monthly_cost = 0.0

    elif action == ActionType.TERMINATE_INSTANCE:
        resource.status = ResourceStatus.TERMINATED
        resource.monthly_cost = 0.0

    elif action == ActionType.DELETE_VOLUME:
        resource.status = ResourceStatus.DELETED
        resource.monthly_cost = 0.0

    elif action == ActionType.DELETE_SNAPSHOT:
        resource.status = ResourceStatus.DELETED
        resource.monthly_cost = 0.0

    elif action == ActionType.RELEASE_EIP:
        resource.status = ResourceStatus.RELEASED
        resource.attached = None
        resource.monthly_cost = 0.0

    elif action == ActionType.DELETE_LOAD_BALANCER:
        resource.status = ResourceStatus.DELETED
        resource.monthly_cost = 0.0

    elif action == ActionType.RESIZE_INSTANCE:
        resource.instance_size = DOWNSIZE_MAP.get(resource.instance_size, resource.instance_size)
        resource.monthly_cost = round(before_cost * (1 - RESIZE_SAVINGS_RATIO), 2)

    elif action == ActionType.STOP_RDS_INSTANCE:
        resource.status = ResourceStatus.STOPPED
        resource.avg_cpu_utilization = 0.0
        resource.monthly_cost = 0.0

    else:
        raise RemediationError(f"Unknown action type: {action}")

    resource.updated_at = datetime.utcnow()
    return round(before_cost - resource.monthly_cost, 2)


def execute_remediation(db: Session, recommendation_id: int) -> RemediationAction:
    recommendation = db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
    if recommendation is None:
        raise RemediationError(f"Recommendation {recommendation_id} not found")
    if recommendation.status != RecommendationStatus.OPEN:
        raise RemediationError(
            f"Recommendation {recommendation_id} is not OPEN (current status: {recommendation.status.value})"
        )

    resource = db.query(CloudResource).filter(CloudResource.id == recommendation.resource_db_id).first()
    if resource is None:
        raise RemediationError(f"Resource {recommendation.resource_db_id} not found")

    try:
        # Must build the CLI command before mutating the resource: RESIZE_INSTANCE
        # needs the pre-mutation instance_size to compute the correct downsize target.
        cli_command = build_cli_command(recommendation.suggested_action, resource)
        savings = _apply_action(resource, recommendation.suggested_action)
        action = RemediationAction(
            recommendation_id=recommendation.id,
            resource_db_id=resource.id,
            action_type=recommendation.suggested_action,
            status=ActionStatus.COMPLETED,
            savings_realized_monthly=savings,
            cli_command=cli_command,
            notes=f"Auto-remediated via {recommendation.suggested_action.value} on {resource.resource_id}.",
        )
        recommendation.status = RecommendationStatus.REMEDIATED
        db.add(action)
        db.commit()
        db.refresh(action)
        return action
    except Exception as exc:
        db.rollback()
        failed_action = RemediationAction(
            recommendation_id=recommendation.id,
            resource_db_id=recommendation.resource_db_id,
            action_type=recommendation.suggested_action,
            status=ActionStatus.FAILED,
            savings_realized_monthly=0.0,
            notes=f"Remediation failed: {exc}",
        )
        db.add(failed_action)
        db.commit()
        db.refresh(failed_action)
        return failed_action


def dismiss_recommendation(db: Session, recommendation_id: int) -> Recommendation:
    recommendation = db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
    if recommendation is None:
        raise RemediationError(f"Recommendation {recommendation_id} not found")
    if recommendation.status != RecommendationStatus.OPEN:
        raise RemediationError(
            f"Recommendation {recommendation_id} is not OPEN (current status: {recommendation.status.value})"
        )
    recommendation.status = RecommendationStatus.DISMISSED
    db.commit()
    db.refresh(recommendation)
    return recommendation
