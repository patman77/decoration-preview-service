"""Network stack: VPC and security groups.

Creates an isolated VPC with public and private subnets
for secure rendering workload isolation.
"""

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(cdk.Stack):
    """VPC and networking infrastructure.

    Architecture:
    - 2 AZs for high availability
    - Public subnets: NAT Gateways, ALB
    - Private subnets: ECS tasks, RDS (future)
    - Isolated subnets: ElastiCache (future)
    - VPC Flow Logs for security auditing
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC with public and private subnets across 2 AZs
        self.vpc = ec2.Vpc(
            self,
            "DecorationPreviewVpc",
            vpc_name="decoration-preview-vpc",
            max_azs=2,
            nat_gateways=1,  # Cost optimization; increase for HA
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # VPC Flow Logs for security monitoring
        self.vpc.add_flow_log(
            "FlowLog",
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(),
            traffic_type=ec2.FlowLogTrafficType.REJECT,
        )

        # Security group for ECS rendering tasks
        self.render_sg = ec2.SecurityGroup(
            self,
            "RenderSecurityGroup",
            vpc=self.vpc,
            description="Security group for rendering ECS tasks",
            allow_all_outbound=True,
        )

        # Security group for API service
        self.api_sg = ec2.SecurityGroup(
            self,
            "ApiSecurityGroup",
            vpc=self.vpc,
            description="Security group for API service",
            allow_all_outbound=True,
        )

        # Allow API to communicate with renderers
        self.render_sg.add_ingress_rule(
            peer=self.api_sg,
            connection=ec2.Port.tcp(8000),
            description="Allow API to reach render workers",
        )

        # Outputs
        cdk.CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
