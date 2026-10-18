"""
AdminSite: the staff-only admin dashboard, fully separate from the student site.

  * its own Cognito user pool (no self sign-up, strong passwords, TOTP MFA required)
  * its own app client (no secret, SRP only) and an `admins` group
  * its own private S3 bucket + CloudFront distribution (a different origin from the student site)
  * a dedicated JWT authorizer attached to /admin/{proxy+} on the existing HTTP API

Wiring (see ADMIN.md): create it in stack.py AFTER http_api and api_fn exist:
    admin_site = AdminSite(self, "AdminSite", http_api=http_api, api_fn=api_fn)
"""
import re

from aws_cdk import (
    Stack, CfnOutput, Annotations, RemovalPolicy, Duration,
    aws_cognito as cognito,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as integrations,
    aws_apigatewayv2_authorizers as authorizers,
)
from constructs import Construct


class AdminSite(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, http_api: apigw.HttpApi, api_fn,
                 api_origin: str | None = None):
        """api_origin pins the CSP connect-src to exactly one API. If not passed it is read from CDK
        context `adminApiOrigin` (cdk.json "context", or `-c adminApiOrigin=...`): the ApiUrl output of
        the first deploy, a plain string, so there is no CloudFormation cycle with the API's CORS list.
        First deploy only (value unknown yet): falls back to the regional execute-api wildcard and adds a
        CDK warning. Set the context value and redeploy to pin it."""
        super().__init__(scope, construct_id)
        stack = Stack.of(self)
        region = stack.region

        # ── Staff user pool ───────────────────────────────────────────────────
        self.user_pool = cognito.UserPool(
            self, "StaffPool",
            user_pool_name="semesteros-staff",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            sign_in_case_sensitive=False,
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=False),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=Duration.days(3),
            ),
            mfa=cognito.Mfa.REQUIRED,
            mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True),
            account_recovery=cognito.AccountRecovery.NONE,  # another admin (or the script) resets access
            user_invitation=cognito.UserInvitationConfig(
                email_subject="You have been invited to the Semester OS admin console",
                email_body=(
                    "You have been added as a Semester OS administrator.<br/><br/>"
                    "Username: <b>{username}</b><br/>Temporary password: <b>{####}</b><br/><br/>"
                    "Sign in on the admin site, choose a new password (12+ characters) and set up "
                    "an authenticator app. The temporary password expires in 3 days."
                ),
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        cognito.CfnUserPoolGroup(
            self, "AdminsGroup",
            user_pool_id=self.user_pool.user_pool_id,
            group_name="admins",
            description="Semester OS staff who may use the admin console",
        )

        self.client = self.user_pool.add_client(
            "AdminClient",
            user_pool_client_name="semesteros-admin-site",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True),
            disable_o_auth=True,
            prevent_user_existence_errors=True,
            enable_token_revocation=True,
            id_token_validity=Duration.minutes(30),
            access_token_validity=Duration.minutes(30),
            refresh_token_validity=Duration.hours(8),
        )

        # ── Authorizer + routes (separate issuer and audience from the student pool) ──
        authorizer = authorizers.HttpJwtAuthorizer(
            "AdminCognitoAuth",
            jwt_issuer=f"https://cognito-idp.{region}.amazonaws.com/{self.user_pool.user_pool_id}",
            jwt_audience=[self.client.user_pool_client_id],
        )
        http_api.add_routes(
            path="/admin/{proxy+}",
            methods=[apigw.HttpMethod.GET, apigw.HttpMethod.POST, apigw.HttpMethod.PUT,
                     apigw.HttpMethod.PATCH, apigw.HttpMethod.DELETE],
            integration=integrations.HttpLambdaIntegration("AdminRoutes", api_fn),
            authorizer=authorizer,
        )
        # admin_api.py double-checks the issuer is this pool and the `admins` group is present
        api_fn.add_environment("ADMIN_USER_POOL_ID", self.user_pool.user_pool_id)

        # ── Hosting: private bucket + own CloudFront distribution ─────────────
        self.bucket = s3.Bucket(
            self, "AdminBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        api_origin = api_origin or stack.node.try_get_context("adminApiOrigin")
        if api_origin:
            if not re.fullmatch(r"https://[a-z0-9]+\.execute-api\.[a-z0-9-]+\.amazonaws\.com", str(api_origin)):
                raise ValueError("adminApiOrigin must look like https://<id>.execute-api.<region>.amazonaws.com (no path, no slash)")
            api_src = api_origin
        else:
            api_src = f"https://*.execute-api.{region}.amazonaws.com"
            Annotations.of(self).add_warning(
                "Admin CSP connect-src is the regional execute-api wildcard. Set context adminApiOrigin to the "
                "ApiUrl output and redeploy to pin it (see ADMIN.md).")
        csp = "; ".join([
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            "img-src 'self' data:",
            "font-src 'self'",
            f"connect-src 'self' {api_src} https://cognito-idp.{region}.amazonaws.com",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ])
        headers_policy = cloudfront.ResponseHeadersPolicy(
            self, "AdminHeaders",
            comment="Semester OS admin site security headers",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                content_security_policy=cloudfront.ResponseHeadersContentSecurityPolicy(
                    content_security_policy=csp, override=True),
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.days(730), include_subdomains=True, preload=True, override=True),
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(override=True),
                frame_options=cloudfront.ResponseHeadersFrameOptions(
                    frame_option=cloudfront.HeadersFrameOption.DENY, override=True),
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.NO_REFERRER, override=True),
            ),
            custom_headers_behavior=cloudfront.ResponseCustomHeadersBehavior(custom_headers=[
                cloudfront.ResponseCustomHeader(header="X-Robots-Tag", value="noindex, nofollow, noarchive", override=True),
                cloudfront.ResponseCustomHeader(header="Cache-Control", value="no-store", override=True),
                cloudfront.ResponseCustomHeader(header="Cross-Origin-Opener-Policy", value="same-origin", override=True),
                cloudfront.ResponseCustomHeader(header="Cross-Origin-Resource-Policy", value="same-origin", override=True),
                cloudfront.ResponseCustomHeader(header="Permissions-Policy", value="camera=(), microphone=(), geolocation=()", override=True),
            ]),
        )

        self.distribution = cloudfront.Distribution(
            self, "AdminDistribution",
            comment="Semester OS admin console",
            default_root_object="index.html",
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(self.bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                response_headers_policy=headers_policy,
            ),
            error_responses=[
                cloudfront.ErrorResponse(http_status=403, response_page_path="/index.html",
                                         response_http_status=200, ttl=Duration.seconds(0)),
                cloudfront.ErrorResponse(http_status=404, response_page_path="/index.html",
                                         response_http_status=200, ttl=Duration.seconds(0)),
            ],
        )

        self.url = f"https://{self.distribution.distribution_domain_name}"

        # ── Outputs (stack-level ids so cdk-outputs.json keys are stable) ─────
        CfnOutput(stack, "AdminUserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(stack, "AdminClientId", value=self.client.user_pool_client_id)
        CfnOutput(stack, "AdminBucketName", value=self.bucket.bucket_name)
        CfnOutput(stack, "AdminDistributionId", value=self.distribution.distribution_id)
        CfnOutput(stack, "AdminSiteUrl", value=self.url)
