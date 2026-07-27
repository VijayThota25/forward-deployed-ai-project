"""
Maps each remediation ActionType to the exact AWS CLI v2 command that would
perform the equivalent operation against a real account.

This engine remediates against a simulated fleet (no live AWS account), but
every Recommendation and executed RemediationAction carries the real command
here, so the output is directly actionable/copy-pasteable against a real
account, and the audit trail records exactly what would have run.
"""
from app.models import ActionType, CloudResource

# One tier down for RESIZE_INSTANCE. Shared with app/remediation.py so the
# CLI command's target type always matches what remediation actually applies.
DOWNSIZE_MAP = {
    "m5.2xlarge": "m5.xlarge",
    "m5.xlarge": "m5.large",
    "c5.xlarge": "c5.large",
    "r5.xlarge": "r5.large",
    "t3.large": "t3.medium",
}


def build_cli_command(action: ActionType, resource: CloudResource) -> str:
    rid = resource.resource_id
    region = resource.region

    if action == ActionType.STOP_INSTANCE:
        return f"aws ec2 stop-instances --instance-ids {rid} --region {region}"

    if action == ActionType.TERMINATE_INSTANCE:
        return f"aws ec2 terminate-instances --instance-ids {rid} --region {region}"

    if action == ActionType.DELETE_VOLUME:
        return f"aws ec2 delete-volume --volume-id {rid} --region {region}"

    if action == ActionType.DELETE_SNAPSHOT:
        return f"aws ec2 delete-snapshot --snapshot-id {rid} --region {region}"

    if action == ActionType.RELEASE_EIP:
        return f"aws ec2 release-address --allocation-id {rid} --region {region}"

    if action == ActionType.DELETE_LOAD_BALANCER:
        # resource_id is the load balancer ARN (ELBv2 requires the ARN, not a name)
        return f"aws elbv2 delete-load-balancer --load-balancer-arn {rid} --region {region}"

    if action == ActionType.STOP_RDS_INSTANCE:
        # resource_id is the DB instance identifier, not an ARN or synthetic hex id
        return f"aws rds stop-db-instance --db-instance-identifier {rid} --region {region}"

    if action == ActionType.RESIZE_INSTANCE:
        target_type = DOWNSIZE_MAP.get(resource.instance_size, resource.instance_size)
        inner_json = '{\\"Value\\": \\"' + target_type + '\\"}'
        return "\n".join([
            f"aws ec2 stop-instances --instance-ids {rid} --region {region}",
            f"aws ec2 wait instance-stopped --instance-ids {rid} --region {region}",
            f'aws ec2 modify-instance-attribute --instance-id {rid} '
            f'--instance-type "{inner_json}" --region {region}',
            f"aws ec2 start-instances --instance-ids {rid} --region {region}",
        ])

    raise ValueError(f"No CLI command mapping for action: {action}")
