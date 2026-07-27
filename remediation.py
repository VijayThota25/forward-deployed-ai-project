import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ResourceType(str, enum.Enum):
    EC2_INSTANCE = "EC2_INSTANCE"
    EBS_VOLUME = "EBS_VOLUME"
    SNAPSHOT = "SNAPSHOT"
    ELASTIC_IP = "ELASTIC_IP"
    LOAD_BALANCER = "LOAD_BALANCER"
    RDS_INSTANCE = "RDS_INSTANCE"
    S3_BUCKET = "S3_BUCKET"


class ResourceStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    AVAILABLE = "AVAILABLE"  # e.g. unattached volume
    TERMINATED = "TERMINATED"
    RELEASED = "RELEASED"
    DELETED = "DELETED"


class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecommendationStatus(str, enum.Enum):
    OPEN = "OPEN"
    DISMISSED = "DISMISSED"
    REMEDIATED = "REMEDIATED"


class ActionType(str, enum.Enum):
    STOP_INSTANCE = "STOP_INSTANCE"
    TERMINATE_INSTANCE = "TERMINATE_INSTANCE"
    DELETE_VOLUME = "DELETE_VOLUME"
    DELETE_SNAPSHOT = "DELETE_SNAPSHOT"
    RELEASE_EIP = "RELEASE_EIP"
    RESIZE_INSTANCE = "RESIZE_INSTANCE"
    DELETE_LOAD_BALANCER = "DELETE_LOAD_BALANCER"
    STOP_RDS_INSTANCE = "STOP_RDS_INSTANCE"


class ActionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CloudResource(Base):
    __tablename__ = "cloud_resources"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    resource_type = Column(SAEnum(ResourceType), nullable=False, index=True)
    region = Column(String, nullable=False)
    status = Column(SAEnum(ResourceStatus), nullable=False, default=ResourceStatus.RUNNING)
    instance_size = Column(String, nullable=True)  # e.g. m5.xlarge, gp3-100GB
    avg_cpu_utilization = Column(Float, nullable=True)  # % over trailing 14d, instances only
    avg_network_bytes = Column(Float, nullable=True)
    size_gb = Column(Float, nullable=True)  # volumes/snapshots
    attached = Column(Boolean, nullable=True)  # volumes: attached to an instance?
    days_since_last_used = Column(Integer, nullable=True)
    monthly_cost = Column(Float, nullable=False, default=0.0)
    tags = Column(Text, nullable=True)  # JSON-encoded dict
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cost_records = relationship("CostRecord", back_populates="resource", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="resource", cascade="all, delete-orphan")


class CostRecord(Base):
    __tablename__ = "cost_records"

    id = Column(Integer, primary_key=True, index=True)
    resource_db_id = Column(Integer, ForeignKey("cloud_resources.id"), nullable=False)
    date = Column(DateTime, nullable=False, index=True)
    daily_cost = Column(Float, nullable=False)
    service = Column(String, nullable=False)
    region = Column(String, nullable=False)

    resource = relationship("CloudResource", back_populates="cost_records")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    resource_db_id = Column(Integer, ForeignKey("cloud_resources.id"), nullable=False)
    rule_code = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(SAEnum(Severity), nullable=False, default=Severity.MEDIUM)
    suggested_action = Column(SAEnum(ActionType), nullable=False)
    estimated_monthly_savings = Column(Float, nullable=False, default=0.0)
    status = Column(SAEnum(RecommendationStatus), nullable=False, default=RecommendationStatus.OPEN)
    cli_command = Column(Text, nullable=True)  # exact AWS CLI command remediation would run
    created_at = Column(DateTime, default=datetime.utcnow)

    resource = relationship("CloudResource", back_populates="recommendations")
    actions = relationship("RemediationAction", back_populates="recommendation", cascade="all, delete-orphan")


class RemediationAction(Base):
    __tablename__ = "remediation_actions"

    id = Column(Integer, primary_key=True, index=True)
    recommendation_id = Column(Integer, ForeignKey("recommendations.id"), nullable=False)
    resource_db_id = Column(Integer, ForeignKey("cloud_resources.id"), nullable=False)
    action_type = Column(SAEnum(ActionType), nullable=False)
    status = Column(SAEnum(ActionStatus), nullable=False, default=ActionStatus.PENDING)
    savings_realized_monthly = Column(Float, nullable=False, default=0.0)
    performed_at = Column(DateTime, default=datetime.utcnow)
    cli_command = Column(Text, nullable=True)  # exact AWS CLI command executed
    notes = Column(Text, nullable=True)

    recommendation = relationship("Recommendation", back_populates="actions")
