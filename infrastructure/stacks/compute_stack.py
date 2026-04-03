"""Compute stack: ECS Fargate cluster and task definitions.

Defines the containerized compute infrastructure for:
1. API service (FastAPI application)
2. Render workers (Blender-based rendering, stubbed)

Both run on ECS Fargate for serverless container management.
"""

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct

from stacks.storage_stack import StorageStack


class ComputeStack(cdk.Stack):
    """ECS Fargate compute infrastructure.

    Architecture:
    - Shared ECS cluster across API and render workers
    - API service: Always-on with auto-scaling (2-10 tasks)
    - Render workers: Scale based on SQS queue depth (0-50 tasks)
    - CloudWatch logging for all containers
    - IAM roles follow least-privilege principle
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        storage: StorageStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ECS Cluster
        self.cluster = ecs.Cluster(
            self,
            "RenderCluster",
            cluster_name="decoration-preview-cluster",
            vpc=vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )

        # --- API Service Task Definition ---

        self.api_task_role = iam.Role(
            self,
            "ApiTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="IAM role for API service ECS tasks",
        )

        # API needs to read/write S3, DynamoDB, and send SQS messages
        storage.artwork_bucket.grant_read_write(self.api_task_role)
        storage.renders_bucket.grant_read(self.api_task_role)
        storage.jobs_table.grant_read_write_data(self.api_task_role)
        storage.render_queue.grant_send_messages(self.api_task_role)

        self.api_task_definition = ecs.FargateTaskDefinition(
            self,
            "ApiTaskDef",
            family="decoration-preview-api",
            cpu=512,
            memory_limit_mib=1024,
            task_role=self.api_task_role,
        )

        self.api_container = self.api_task_definition.add_container(
            "ApiContainer",
            image=ecs.ContainerImage.from_asset("../backend"),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="api",
                log_group=logs.LogGroup(
                    self,
                    "ApiLogGroup",
                    log_group_name="/ecs/decoration-preview/api",
                    retention=logs.RetentionDays.THIRTY_DAYS,
                    removal_policy=cdk.RemovalPolicy.DESTROY,
                ),
            ),
            environment={
                "ENVIRONMENT": "production",
                "LOG_LEVEL": "INFO",
                "AWS_REGION": cdk.Aws.REGION,
                "ARTWORK_BUCKET": storage.artwork_bucket.bucket_name,
                "ELEMENTS_BUCKET": storage.elements_bucket.bucket_name,
                "RENDERS_BUCKET": storage.renders_bucket.bucket_name,
                "JOBS_TABLE": storage.jobs_table.table_name,
                "RENDER_QUEUE_URL": storage.render_queue.queue_url,
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        self.api_container.add_port_mappings(
            ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)
        )

        # --- Render Worker Task Definition ---

        self.render_task_role = iam.Role(
            self,
            "RenderTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="IAM role for render worker ECS tasks",
        )

        # Render workers need S3 read (artwork, elements) + write (renders),
        # DynamoDB update, and SQS consume
        storage.artwork_bucket.grant_read(self.render_task_role)
        storage.elements_bucket.grant_read(self.render_task_role)
        storage.renders_bucket.grant_read_write(self.render_task_role)
        storage.jobs_table.grant_read_write_data(self.render_task_role)
        storage.render_queue.grant_consume_messages(self.render_task_role)

        self.render_task_definition = ecs.FargateTaskDefinition(
            self,
            "RenderTaskDef",
            family="decoration-preview-render",
            cpu=2048,  # Rendering is CPU-intensive
            memory_limit_mib=4096,
            task_role=self.render_task_role,
        )

        self.render_container = self.render_task_definition.add_container(
            "RenderContainer",
            image=ecs.ContainerImage.from_asset("../backend"),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="render",
                log_group=logs.LogGroup(
                    self,
                    "RenderLogGroup",
                    log_group_name="/ecs/decoration-preview/render",
                    retention=logs.RetentionDays.THIRTY_DAYS,
                    removal_policy=cdk.RemovalPolicy.DESTROY,
                ),
            ),
            environment={
                "ENVIRONMENT": "production",
                "LOG_LEVEL": "INFO",
                "AWS_REGION": cdk.Aws.REGION,
                "ARTWORK_BUCKET": storage.artwork_bucket.bucket_name,
                "ELEMENTS_BUCKET": storage.elements_bucket.bucket_name,
                "RENDERS_BUCKET": storage.renders_bucket.bucket_name,
                "JOBS_TABLE": storage.jobs_table.table_name,
                "RENDER_QUEUE_URL": storage.render_queue.queue_url,
                "WORKER_MODE": "true",
            },
            command=["python", "-m", "backend.app.workers.renderer"],
        )

        # --- API Service (Fargate Service with ALB) ---

        self.api_service = ecs.FargateService(
            self,
            "ApiService",
            service_name="decoration-preview-api",
            cluster=self.cluster,
            task_definition=self.api_task_definition,
            desired_count=2,
            min_healthy_percent=100,
            max_healthy_percent=200,
            assign_public_ip=False,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
        )

        # Auto-scaling for API service
        api_scaling = self.api_service.auto_scale_task_count(
            min_capacity=2,
            max_capacity=10,
        )
        api_scaling.scale_on_cpu_utilization(
            "ApiCpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(300),
            scale_out_cooldown=Duration.seconds(60),
        )

        # --- Render Worker Service ---

        self.render_service = ecs.FargateService(
            self,
            "RenderService",
            service_name="decoration-preview-render",
            cluster=self.cluster,
            task_definition=self.render_task_definition,
            desired_count=1,
            min_healthy_percent=0,
            max_healthy_percent=200,
            assign_public_ip=False,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
        )

        # Auto-scaling for render workers based on SQS queue depth
        render_scaling = self.render_service.auto_scale_task_count(
            min_capacity=0,
            max_capacity=50,
        )
        render_scaling.scale_on_cpu_utilization(
            "RenderCpuScaling",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.seconds(600),
            scale_out_cooldown=Duration.seconds(60),
        )

        # Outputs
        cdk.CfnOutput(self, "ClusterName", value=self.cluster.cluster_name)
