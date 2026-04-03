"""Monitoring stack: CloudWatch dashboards, alarms, and alerts.

Provides observability into service health, performance,
and rendering pipeline metrics.
"""

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
)
from constructs import Construct

from stacks.compute_stack import ComputeStack
from stacks.storage_stack import StorageStack


class MonitoringStack(cdk.Stack):
    """Monitoring and observability infrastructure.

    Provides:
    - CloudWatch dashboard with key metrics
    - Alarms for critical thresholds
    - SNS topic for alert notifications
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        compute: ComputeStack,
        storage: StorageStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # SNS Topic for alerts
        self.alerts_topic = sns.Topic(
            self,
            "AlertsTopic",
            topic_name="decoration-preview-alerts",
            display_name="Decoration Preview Service Alerts",
        )

        # --- CloudWatch Alarms ---

        # API service CPU alarm
        api_cpu_alarm = cloudwatch.Alarm(
            self,
            "ApiHighCpu",
            alarm_name="decoration-preview-api-high-cpu",
            metric=compute.api_service.metric_cpu_utilization(),
            threshold=85,
            evaluation_periods=3,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        api_cpu_alarm.add_alarm_action(cw_actions.SnsAction(self.alerts_topic))

        # SQS queue depth alarm (render backlog)
        queue_depth_alarm = cloudwatch.Alarm(
            self,
            "RenderQueueBacklog",
            alarm_name="decoration-preview-render-backlog",
            metric=storage.render_queue.metric_approximate_number_of_messages_visible(),
            threshold=100,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        queue_depth_alarm.add_alarm_action(cw_actions.SnsAction(self.alerts_topic))

        # DLQ messages alarm (failed renders)
        dlq_alarm = cloudwatch.Alarm(
            self,
            "RenderDlqMessages",
            alarm_name="decoration-preview-render-failures",
            metric=storage.render_dlq.metric_approximate_number_of_messages_visible(),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        dlq_alarm.add_alarm_action(cw_actions.SnsAction(self.alerts_topic))

        # --- CloudWatch Dashboard ---

        self.dashboard = cloudwatch.Dashboard(
            self,
            "ServiceDashboard",
            dashboard_name="decoration-preview-service",
        )

        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Service CPU Utilization",
                left=[compute.api_service.metric_cpu_utilization()],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="API Service Memory Utilization",
                left=[compute.api_service.metric_memory_utilization()],
                width=12,
            ),
        )

        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Render Queue Depth",
                left=[
                    storage.render_queue.metric_approximate_number_of_messages_visible(),
                    storage.render_queue.metric_approximate_number_of_messages_not_visible(),
                ],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="DLQ Messages (Failed Renders)",
                left=[
                    storage.render_dlq.metric_approximate_number_of_messages_visible(),
                ],
                width=12,
            ),
        )

        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Render Worker Tasks",
                left=[compute.render_service.metric_cpu_utilization()],
                width=12,
            ),
            cloudwatch.SingleValueWidget(
                title="Active Render Tasks",
                metrics=[compute.render_service.metric("DesiredCount")],
                width=12,
            ),
        )

        # Outputs
        cdk.CfnOutput(self, "AlertsTopicArn", value=self.alerts_topic.topic_arn)
        cdk.CfnOutput(
            self, "DashboardUrl",
            value=f"https://{cdk.Aws.REGION}.console.aws.amazon.com/cloudwatch/home"
                  f"?region={cdk.Aws.REGION}#dashboards:name=decoration-preview-service",
        )
