"""
Unit tests for app/cli_commands.py: each ActionType must produce the correct
AWS service, the correct flag name, and must embed the resource's real
identifier. These are direct regression guards for the bugs found and fixed
in this session: RDS idle-instance recommendations sharing EC2's ActionType
(would emit `aws ec2 stop-instances` against an RDS resource), and load
balancers/RDS instances using synthetic ids AWS's real CLI wouldn't accept.
"""
import re

import pytest

from app.cli_commands import DOWNSIZE_MAP, build_cli_command
from app.models import ActionType, CloudResource

EC2_ID_RE = re.compile(r"^i-[0-9a-f]{17}$")
VOL_ID_RE = re.compile(r"^vol-[0-9a-f]{17}$")
SNAP_ID_RE = re.compile(r"^snap-[0-9a-f]{17}$")
EIP_ID_RE = re.compile(r"^eipalloc-[0-9a-f]{17}$")
LB_ARN_RE = re.compile(
    r"^arn:aws:elasticloadbalancing:[a-z0-9-]+:\d{12}:loadbalancer/app/[a-zA-Z0-9-]+/[0-9a-f]{16}$"
)
# AWS's real DB instance identifier constraint: starts with a letter, only
# alphanumerics/hyphens, no consecutive hyphens, doesn't end with a hyphen.
RDS_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*(-[a-zA-Z0-9]+)*$")


def _resource(**kwargs):
    defaults = dict(region="us-east-1", name="test-resource", monthly_cost=10.0)
    defaults.update(kwargs)
    return CloudResource(**defaults)


CASES = [
    pytest.param(
        ActionType.STOP_INSTANCE, "i-0123456789abcdef0", "aws ec2", "--instance-ids", EC2_ID_RE,
        id="stop-ec2-instance",
    ),
    pytest.param(
        ActionType.TERMINATE_INSTANCE, "i-0123456789abcdef0", "aws ec2", "--instance-ids", EC2_ID_RE,
        id="terminate-ec2-instance",
    ),
    pytest.param(
        ActionType.DELETE_VOLUME, "vol-0123456789abcdef0", "aws ec2", "--volume-id", VOL_ID_RE,
        id="delete-ebs-volume",
    ),
    pytest.param(
        ActionType.DELETE_SNAPSHOT, "snap-0123456789abcdef0", "aws ec2", "--snapshot-id", SNAP_ID_RE,
        id="delete-snapshot",
    ),
    pytest.param(
        ActionType.RELEASE_EIP, "eipalloc-0123456789abcdef0", "aws ec2", "--allocation-id", EIP_ID_RE,
        id="release-elastic-ip",
    ),
    pytest.param(
        ActionType.DELETE_LOAD_BALANCER,
        "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/50dc6c495c0c9188",
        "aws elbv2", "--load-balancer-arn", LB_ARN_RE,
        id="delete-load-balancer",
    ),
    pytest.param(
        ActionType.STOP_RDS_INSTANCE, "prod-orders-db", "aws rds", "--db-instance-identifier", RDS_ID_RE,
        id="stop-rds-instance",
    ),
]


@pytest.mark.parametrize("action, resource_id, expected_service, expected_flag, id_re", CASES)
def test_cli_command_uses_correct_service_flag_and_id_format(
    action, resource_id, expected_service, expected_flag, id_re
):
    assert id_re.match(resource_id), f"test fixture id {resource_id!r} isn't itself AWS-valid -- fix the test"

    resource = _resource(resource_id=resource_id)
    command = build_cli_command(action, resource)

    assert command.startswith(expected_service), f"expected {expected_service!r} service, got: {command}"
    assert expected_flag in command
    assert resource_id in command


def test_rds_stop_command_never_uses_ec2_service():
    """Regression guard: idle RDS and idle EC2 used to share one ActionType,
    which would have produced `aws ec2 stop-instances` against an RDS resource."""
    resource = _resource(resource_id="prod-orders-db", instance_size="db.t3.medium")
    command = build_cli_command(ActionType.STOP_RDS_INSTANCE, resource)
    assert command == "aws rds stop-db-instance --db-instance-identifier prod-orders-db --region us-east-1"
    assert "ec2" not in command


def test_load_balancer_delete_requires_arn_not_bare_id():
    """Regression guard: load balancers used to get a fake `elb-{hex}` id;
    ELBv2's real CLI requires the load balancer's full ARN to delete it."""
    arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/50dc6c495c0c9188"
    resource = _resource(resource_id=arn)
    command = build_cli_command(ActionType.DELETE_LOAD_BALANCER, resource)
    assert command == f"aws elbv2 delete-load-balancer --load-balancer-arn {arn} --region us-east-1"


def test_resize_instance_is_a_stop_modify_start_sequence():
    """AWS requires an instance to be stopped before its instance type can
    change -- a single modify-instance-attribute call would fail on a running
    instance, so the command must be the full sequence, in order."""
    resource = _resource(resource_id="i-0123456789abcdef0", instance_size="m5.xlarge")
    command = build_cli_command(ActionType.RESIZE_INSTANCE, resource)
    lines = command.splitlines()

    assert len(lines) == 4
    assert lines[0] == "aws ec2 stop-instances --instance-ids i-0123456789abcdef0 --region us-east-1"
    assert lines[1] == "aws ec2 wait instance-stopped --instance-ids i-0123456789abcdef0 --region us-east-1"
    assert "modify-instance-attribute" in lines[2]
    assert DOWNSIZE_MAP["m5.xlarge"] in lines[2]
    assert lines[3] == "aws ec2 start-instances --instance-ids i-0123456789abcdef0 --region us-east-1"


def test_unknown_action_raises():
    resource = _resource(resource_id="i-0123456789abcdef0")
    with pytest.raises(ValueError):
        build_cli_command("NOT_A_REAL_ACTION", resource)
