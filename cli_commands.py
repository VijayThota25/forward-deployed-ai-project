"""
Rules-based cost/waste analysis engine.

Scans all CloudResources and emits Recommendation rows for detected waste
patterns. Safe to re-run: it will not create a duplicate recommendation for
a (resource, rule_code) pair that has already been raised (open, dismissed,
or remediated).
"""
from sqlalchemy.orm import Session

from app.models import (
    CloudResource,
    Recommendation,
    ResourceType,
    ResourceStatus,
    Severity,
    ActionType,
)
from app.cli_commands import build_cli_command

LARGE_INSTANCE_TIERS = {"m5.xlarge", "m5.2xlarge", "c5.xlarge", "r5.xlarge", "t3.large"}
IDLE_CPU_THRESHOLD = 5.0
OVERSIZED_CPU_LOW = 5.0
OVERSIZED_CPU_HIGH = 20.0
STALE_SNAPSHOT_DAYS = 90
IDLE_LB_NETWORK_BYTES = 1e5
RESIZE_SAVINGS_RATIO = 0.4  # assume downsizing one tier saves ~40%


def _severity_for(savings: float) -> Severity:
    if savings >= 100:
        return Severity.CRITICAL
    if savings >= 50:
        return Severity.HIGH
    if savings >= 15:
        return Severity.MEDIUM
    return Severity.LOW


def _already_flagged(db: Session, resource_db_id: int, rule_code: str) -> bool:
    return (
        db.query(Recommendation)
        .filter(
            Recommendation.resource_db_id == resource_db_id,
            Recommendation.rule_code == rule_code,
        )
        .first()
        is not None
    )


def _create_recommendation(db: Session, resource: CloudResource, rule_code, title, description, action, savings):
    if savings <= 0 or _already_flagged(db, resource.id, rule_code):
        return None
    rec = Recommendation(
        resource_db_id=resource.id,
        rule_code=rule_code,
        title=title,
        description=description,
        severity=_severity_for(savings),
        suggested_action=action,
        estimated_monthly_savings=round(savings, 2),
        cli_command=build_cli_command(action, resource),
    )
    db.add(rec)
    return rec


def _rule_idle_instance(db: Session, r: CloudResource):
    if (
        r.resource_type == ResourceType.EC2_INSTANCE
        and r.status == ResourceStatus.RUNNING
        and r.avg_cpu_utilization is not None
        and r.avg_cpu_utilization < IDLE_CPU_THRESHOLD
    ):
        _create_recommendation(
            db, r, "IDLE_INSTANCE",
            f"Idle EC2 instance '{r.name}'",
            f"Instance {r.resource_id} ({r.instance_size}) has averaged "
            f"{r.avg_cpu_utilization:.1f}% CPU over the last 14 days. Stop it to eliminate compute cost.",
            ActionType.STOP_INSTANCE,
            r.monthly_cost,
        )


def _rule_oversized_instance(db: Session, r: CloudResource):
    if (
        r.resource_type == ResourceType.EC2_INSTANCE
        and r.status == ResourceStatus.RUNNING
        and r.instance_size in LARGE_INSTANCE_TIERS
        and r.avg_cpu_utilization is not None
        and OVERSIZED_CPU_LOW <= r.avg_cpu_utilization < OVERSIZED_CPU_HIGH
    ):
        savings = r.monthly_cost * RESIZE_SAVINGS_RATIO
        _create_recommendation(
            db, r, "OVERSIZED_INSTANCE",
            f"Oversized EC2 instance '{r.name}'",
            f"Instance {r.resource_id} ({r.instance_size}) only uses "
            f"{r.avg_cpu_utilization:.1f}% CPU on average. Right-sizing to a smaller "
            f"instance type could cut its cost by roughly {int(RESIZE_SAVINGS_RATIO * 100)}%.",
            ActionType.RESIZE_INSTANCE,
            savings,
        )


def _rule_unattached_volume(db: Session, r: CloudResource):
    if r.resource_type == ResourceType.EBS_VOLUME and r.attached is False:
        _create_recommendation(
            db, r, "UNATTACHED_VOLUME",
            f"Unattached EBS volume '{r.name}'",
            f"Volume {r.resource_id} ({r.size_gb:.0f} GB, {r.instance_size}) has been "
            f"unattached for {r.days_since_last_used} days. Delete it to stop paying for unused storage.",
            ActionType.DELETE_VOLUME,
            r.monthly_cost,
        )


def _rule_stale_snapshot(db: Session, r: CloudResource):
    if (
        r.resource_type == ResourceType.SNAPSHOT
        and r.days_since_last_used is not None
        and r.days_since_last_used > STALE_SNAPSHOT_DAYS
    ):
        _create_recommendation(
            db, r, "STALE_SNAPSHOT",
            f"Stale snapshot '{r.name}'",
            f"Snapshot {r.resource_id} ({r.size_gb:.0f} GB) is {r.days_since_last_used} days old. "
            f"Snapshots older than {STALE_SNAPSHOT_DAYS} days are rarely needed for recovery -- delete it.",
            ActionType.DELETE_SNAPSHOT,
            r.monthly_cost,
        )


def _rule_unused_elastic_ip(db: Session, r: CloudResource):
    if r.resource_type == ResourceType.ELASTIC_IP and r.attached is False:
        _create_recommendation(
            db, r, "UNUSED_ELASTIC_IP",
            f"Unassociated Elastic IP '{r.name}'",
            f"Elastic IP {r.resource_id} is not attached to any running instance "
            f"({r.days_since_last_used} days idle). AWS bills idle EIPs hourly -- release it.",
            ActionType.RELEASE_EIP,
            r.monthly_cost,
        )


def _rule_idle_load_balancer(db: Session, r: CloudResource):
    if (
        r.resource_type == ResourceType.LOAD_BALANCER
        and r.avg_network_bytes is not None
        and r.avg_network_bytes < IDLE_LB_NETWORK_BYTES
    ):
        _create_recommendation(
            db, r, "IDLE_LOAD_BALANCER",
            f"Idle load balancer '{r.name}'",
            f"Load balancer {r.resource_id} has processed almost no traffic "
            f"({r.days_since_last_used} days with negligible throughput). Delete it if it's no longer routing traffic.",
            ActionType.DELETE_LOAD_BALANCER,
            r.monthly_cost,
        )


def _rule_idle_rds(db: Session, r: CloudResource):
    if (
        r.resource_type == ResourceType.RDS_INSTANCE
        and r.status == ResourceStatus.RUNNING
        and r.avg_cpu_utilization is not None
        and r.avg_cpu_utilization < IDLE_CPU_THRESHOLD
    ):
        _create_recommendation(
            db, r, "IDLE_RDS_INSTANCE",
            f"Idle RDS instance '{r.name}'",
            f"Database {r.resource_id} ({r.instance_size}) has averaged "
            f"{r.avg_cpu_utilization:.1f}% CPU over the last 14 days. Stop or downsize it.",
            ActionType.STOP_RDS_INSTANCE,
            r.monthly_cost,
        )


ALL_RULES = [
    _rule_idle_instance,
    _rule_oversized_instance,
    _rule_unattached_volume,
    _rule_stale_snapshot,
    _rule_unused_elastic_ip,
    _rule_idle_load_balancer,
    _rule_idle_rds,
]


def run_analysis(db: Session) -> dict:
    resources = db.query(CloudResource).all()
    for r in resources:
        for rule in ALL_RULES:
            rule(db, r)
    created = len(db.new)
    db.commit()
    return {"resources_scanned": len(resources), "recommendations_created": created}
