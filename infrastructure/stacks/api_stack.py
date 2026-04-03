"""API stack: API Gateway and CloudFront distribution.

Configures the public-facing API infrastructure with
authentication, rate limiting, and CDN caching.
"""

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_certificatemanager as acm,
    aws_wafv2 as waf,
)
from constructs import Construct

from stacks.storage_stack import StorageStack
from stacks.compute_stack import ComputeStack


class ApiStack(cdk.Stack):
    """Public API infrastructure.

    Architecture:
    - Application Load Balancer (ALB) fronting ECS API service
    - CloudFront CDN for caching rendered previews
    - WAF for DDoS protection and request filtering
    - API usage plans and rate limiting
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        storage: StorageStack,
        compute: ComputeStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Application Load Balancer ---

        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            "ApiAlb",
            load_balancer_name="decoration-preview-alb",
            vpc=vpc,
            internet_facing=True,
        )

        # HTTP listener (redirects to HTTPS)
        self.alb.add_listener(
            "HttpListener",
            port=80,
            default_action=elbv2.ListenerAction.redirect(
                protocol="HTTPS",
                port="443",
                permanent=True,
            ),
        )

        # HTTPS listener
        # NOTE: In production, attach an ACM certificate
        https_listener = self.alb.add_listener(
            "HttpsListener",
            port=443,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            # certificate: Use acm.Certificate in production
            default_action=elbv2.ListenerAction.fixed_response(
                status_code=404,
                content_type="application/json",
                message_body='{"detail": "Not found"}',
            ),
        )

        # Target group for API service
        api_target_group = https_listener.add_targets(
            "ApiTargets",
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[compute.api_service],
            health_check=elbv2.HealthCheck(
                path="/health",
                port="8000",
                healthy_http_codes="200",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
            deregistration_delay=Duration.seconds(30),
        )

        # --- CloudFront Distribution ---

        # Origin Access Identity for S3
        self.distribution = cloudfront.Distribution(
            self,
            "CdnDistribution",
            comment="Decoration Preview Service CDN",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(
                    self.alb,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
            ),
            additional_behaviors={
                "/api/v1/render/*/download*": cloudfront.BehaviorOptions(
                    origin=origins.LoadBalancerV2Origin(
                        self.alb,
                        protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy(
                        self,
                        "PreviewCachePolicy",
                        cache_policy_name="decoration-preview-cache",
                        default_ttl=Duration.hours(1),
                        max_ttl=Duration.hours(24),
                        min_ttl=Duration.minutes(5),
                        header_behavior=cloudfront.CacheHeaderBehavior.allow_list(
                            "X-API-Key"
                        ),
                        query_string_behavior=cloudfront.CacheQueryStringBehavior.all(),
                    ),
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                ),
            },
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            enabled=True,
        )

        # --- WAF WebACL ---

        self.web_acl = waf.CfnWebACL(
            self,
            "ApiWebAcl",
            name="decoration-preview-waf",
            scope="CLOUDFRONT",
            default_action=waf.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="decoration-preview-waf",
                sampled_requests_enabled=True,
            ),
            rules=[
                # Rate limiting rule
                waf.CfnWebACL.RuleProperty(
                    name="RateLimit",
                    priority=1,
                    action=waf.CfnWebACL.RuleActionProperty(block={}),
                    statement=waf.CfnWebACL.StatementProperty(
                        rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                            limit=1000,
                            aggregate_key_type="IP",
                        ),
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="rate-limit",
                        sampled_requests_enabled=True,
                    ),
                ),
                # AWS Managed Rules - Common Rule Set
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommon",
                    priority=2,
                    override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet",
                        ),
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="aws-common-rules",
                        sampled_requests_enabled=True,
                    ),
                ),
            ],
        )

        # --- Outputs ---

        cdk.CfnOutput(self, "AlbDnsName", value=self.alb.load_balancer_dns_name)
        cdk.CfnOutput(
            self, "CloudFrontDomain", value=self.distribution.distribution_domain_name
        )
