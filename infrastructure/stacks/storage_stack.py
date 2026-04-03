"""Storage stack: S3, DynamoDB, and SQS.

Defines all data persistence and messaging resources with
encryption, lifecycle policies, and access controls.
"""

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
    aws_s3 as s3,
    aws_sqs as sqs,
)
from constructs import Construct


class StorageStack(cdk.Stack):
    """Storage infrastructure for artwork, elements, and rendered previews.

    Security features:
    - All S3 buckets encrypted with KMS (CMK)
    - S3 versioning enabled for audit trail
    - S3 lifecycle policies for cost optimization
    - DynamoDB encryption at rest
    - SQS encryption with KMS
    - Block all public access on S3 buckets
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # KMS key for encrypting all storage resources
        self.encryption_key = kms.Key(
            self,
            "StorageEncryptionKey",
            alias="decoration-preview/storage",
            description="Encryption key for Decoration Preview Service storage",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # --- S3 Buckets ---

        # Artwork uploads bucket (confidential pre-release designs)
        self.artwork_bucket = s3.Bucket(
            self,
            "ArtworkBucket",
            bucket_name=f"decoration-preview-artwork-{cdk.Aws.ACCOUNT_ID}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.encryption_key,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="CleanupTempUploads",
                    prefix="temp/",
                    expiration=Duration.days(1),
                ),
                s3.LifecycleRule(
                    id="ArchiveOldArtwork",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                            transition_after=Duration.days(30),
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90),
                        ),
                    ],
                ),
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST],
                    allowed_origins=["*"],  # Restricted in production
                    allowed_headers=["*"],
                    max_age=3600,
                ),
            ],
        )

        # 3D element models bucket
        self.elements_bucket = s3.Bucket(
            self,
            "ElementsBucket",
            bucket_name=f"decoration-preview-elements-{cdk.Aws.ACCOUNT_ID}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.encryption_key,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Rendered previews bucket
        self.renders_bucket = s3.Bucket(
            self,
            "RendersBucket",
            bucket_name=f"decoration-preview-renders-{cdk.Aws.ACCOUNT_ID}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.encryption_key,
            versioned=False,  # Renders are reproducible
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireOldRenders",
                    expiration=Duration.days(30),
                ),
                s3.LifecycleRule(
                    id="CleanupFailedMultipart",
                    abort_incomplete_multipart_upload_after=Duration.days(1),
                ),
            ],
        )

        # --- DynamoDB Table ---

        self.jobs_table = dynamodb.Table(
            self,
            "JobsTable",
            table_name="decoration-preview-jobs",
            partition_key=dynamodb.Attribute(
                name="job_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN,
            time_to_live_attribute="ttl",
        )

        # GSI for querying jobs by status
        self.jobs_table.add_global_secondary_index(
            index_name="status-created-index",
            partition_key=dynamodb.Attribute(
                name="status", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # GSI for querying jobs by element
        self.jobs_table.add_global_secondary_index(
            index_name="element-created-index",
            partition_key=dynamodb.Attribute(
                name="element_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # --- SQS Queue ---

        # Dead letter queue for failed rendering jobs
        self.render_dlq = sqs.Queue(
            self,
            "RenderDeadLetterQueue",
            queue_name="decoration-preview-render-dlq",
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=self.encryption_key,
            retention_period=Duration.days(14),
        )

        # Main render job queue
        self.render_queue = sqs.Queue(
            self,
            "RenderQueue",
            queue_name="decoration-preview-render-queue",
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=self.encryption_key,
            visibility_timeout=Duration.minutes(10),
            receive_message_wait_time=Duration.seconds(20),  # Long polling
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.render_dlq,
            ),
        )

        # --- Outputs ---

        cdk.CfnOutput(self, "ArtworkBucketName", value=self.artwork_bucket.bucket_name)
        cdk.CfnOutput(self, "ElementsBucketName", value=self.elements_bucket.bucket_name)
        cdk.CfnOutput(self, "RendersBucketName", value=self.renders_bucket.bucket_name)
        cdk.CfnOutput(self, "JobsTableName", value=self.jobs_table.table_name)
        cdk.CfnOutput(self, "RenderQueueUrl", value=self.render_queue.queue_url)
