import os
from aws_cdk import (
    Stack, CfnOutput, RemovalPolicy, Duration,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_kms as kms,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as integrations,
    aws_apigatewayv2_authorizers as authorizers,
    aws_cognito as cognito,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
)
from constructs import Construct

from admin_site import AdminSite  # staff console: own Cognito pool, CloudFront and /admin/* routes


class SemesterOSStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # ── DynamoDB ──────────────────────────────────────────────────────────
        table = dynamodb.Table(
            self, "AppTable",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )
        table.add_global_secondary_index(
            index_name="gsi1",
            partition_key=dynamodb.Attribute(name="gsi1pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="gsi1sk", type=dynamodb.AttributeType.STRING),
        )
        table.add_global_secondary_index(
            index_name="gsi2",
            partition_key=dynamodb.Attribute(name="gsi2pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="gsi2sk", type=dynamodb.AttributeType.STRING),
        )

        # ── S3 Buckets ────────────────────────────────────────────────────────
        upload_bucket = s3.Bucket(
            self, "UploadBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            cors=[s3.CorsRule(
                allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST],
                allowed_origins=["*"],
                allowed_headers=["*"],
                max_age=3000,
            )],
        )

        website_bucket = s3.Bucket(
            self, "WebsiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ── Cognito ───────────────────────────────────────────────────────────
        user_pool = cognito.UserPool(
            self, "UserPool",
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=False,
                require_digits=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
            self_sign_up_enabled=True,
        )
        user_pool_client = user_pool.add_client(
            "WebClient",
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                user_password=True,
            ),
            prevent_user_existence_errors=True,
            disable_o_auth=True,  # the app signs in with SRP only; CDK's default would enable implicit + code flows
        )

        # ── Feed encryption key (Blackboard calendar URLs at rest) ────────────
        feed_key = kms.Key(
            self, "FeedKey",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
            description="Encryption key for Blackboard calendar feed URLs",
        )

        # ── Pre-signup Lambda (domain gate) ──────────────────────────────────
        backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
        pre_signup_fn = lambda_.Function(
            self, "PreSignupFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="pre_signup.handler",
            code=lambda_.Code.from_asset(backend_path, exclude=["tests", "__pycache__", "*.pyc"]),
            timeout=Duration.seconds(5),
            memory_size=256,
            environment={
                "TABLE_NAME": table.table_name,
                "REGION": self.region,
            },
        )
        table.grant_read_data(pre_signup_fn)
        user_pool.add_trigger(cognito.UserPoolOperation.PRE_SIGN_UP, pre_signup_fn)

        # ── Models (chosen in a live bake-off; see the internal planning notes "MODEL DECISION") ──
        # 100-requests-per-minute on-demand models: the Claude profiles in this account allow only 10.
        # None of them accept PDF document blocks, so PDFs are turned into text before extraction.
        model_env = {
            "MODEL_MAIN": "zai.glm-5",
            "MODEL_MAIN_FALLBACKS": "openai.gpt-oss-120b-1:0,mistral.mistral-large-3-675b-instruct,us.anthropic.claude-sonnet-4-6",
            "MODEL_FAST": "amazon.nova-lite-v1:0",
            "MODEL_FAST_FALLBACKS": "zai.glm-5",
        }

        # ── Syllabus worker (async; invoked by the API, not by HTTP) ─────────
        process_syllabus_fn = lambda_.Function(
            self, "ProcessSyllabusFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="process_syllabus.handler",
            code=lambda_.Code.from_asset(backend_path, exclude=["tests", "__pycache__", "*.pyc"]),
            timeout=Duration.seconds(120),
            memory_size=512,
            retry_attempts=0,  # a retry would re-call Bedrock and duplicate the class's assignments
            environment={
                "TABLE_NAME": table.table_name,
                **model_env,
                # This worker has 120s (the API Lambda has 29s), so the model chain can run longer.
                "BEDROCK_CHAIN_BUDGET_SECONDS": "90",
                "BEDROCK_READ_TIMEOUT_SECONDS": "100",
                "REGION": self.region,
            },
        )
        table.grant_read_write_data(process_syllabus_fn)
        upload_bucket.grant_read(process_syllabus_fn)
        # A PDF landing under syllabi/ starts the worker (the key layout is fixed by the API).
        upload_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(process_syllabus_fn),
            s3.NotificationKeyFilter(prefix="syllabi/", suffix=".pdf"),
        )
        process_syllabus_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"],
        ))

        # ── Process-material worker (async; invoked by api_fn on material upload) ──
        process_material_fn = lambda_.Function(
            self, "ProcessMaterialFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="process_material.handler",
            code=lambda_.Code.from_asset(backend_path, exclude=["tests", "__pycache__", "*.pyc"]),
            timeout=Duration.seconds(120),
            memory_size=512,
            retry_attempts=2,
            # no reserved concurrency: the account limit is 10 and Lambda refuses to reserve below 10 unreserved
            environment={
                "TABLE_NAME": table.table_name,
                **model_env,
                "BEDROCK_CHAIN_BUDGET_SECONDS": "60",
                "BEDROCK_READ_TIMEOUT_SECONDS": "100",
                "REGION": self.region,
                "UPLOAD_BUCKET": upload_bucket.bucket_name,
            },
        )
        table.grant_read_write_data(process_material_fn)
        upload_bucket.grant_read(process_material_fn)
        upload_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(process_material_fn),
            s3.NotificationKeyFilter(prefix="materials/"),
        )
        process_material_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"],
        ))

        # ── Color worker (async; invoked by api_fn on new campus creation) ─────
        color_worker_fn = lambda_.Function(
            self, "ColorWorkerFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="color_worker.handler",
            code=lambda_.Code.from_asset(backend_path, exclude=["tests", "__pycache__", "*.pyc"]),
            timeout=Duration.seconds(60),
            memory_size=256,
            retry_attempts=0,
            environment={
                "TABLE_NAME": table.table_name,
                **model_env,
                "REGION": self.region,
                "COLOR_WORKER_ENABLED": "1",
                "COLOR_WORKER_DAILY_CAP": "200",
            },
        )
        table.grant_read_write_data(color_worker_fn)
        color_worker_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=["*"],
        ))

        # ── Sync-Blackboard (scheduled every 15 minutes) ──────────────────────────
        sync_blackboard_fn = lambda_.Function(
            self, "SyncBlackboardFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="sync_blackboard.handler",
            code=lambda_.Code.from_asset(backend_path, exclude=["tests", "__pycache__", "*.pyc"]),
            timeout=Duration.seconds(120),
            memory_size=512,
            retry_attempts=0,
            environment={
                "TABLE_NAME": table.table_name,
                **model_env,
                "REGION": self.region,
                "KMS_KEY_ID": feed_key.key_id,
                "REQUIRE_KMS": "1",
            },
        )
        table.grant_read_write_data(sync_blackboard_fn)
        feed_key.grant_decrypt(sync_blackboard_fn)
        events.Rule(
            self, "SyncBlackboardSchedule",
            schedule=events.Schedule.rate(Duration.minutes(15)),
            targets=[targets.LambdaFunction(sync_blackboard_fn)],
        )

        # ── Lambda ────────────────────────────────────────────────────────────
        api_fn = lambda_.Function(
            self, "ApiFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.handler",
            code=lambda_.Code.from_asset(backend_path, exclude=["tests", "__pycache__", "*.pyc"]),
            timeout=Duration.seconds(29),
            memory_size=512,
            environment={
                "TABLE_NAME": table.table_name,
                "UPLOAD_BUCKET": upload_bucket.bucket_name,
                **model_env,
                "REGION": self.region,
                "PROCESS_SYLLABUS_FN": process_syllabus_fn.function_name,
                "PROCESS_MATERIAL_FN": process_material_fn.function_name,
                "COLOR_WORKER_FN": color_worker_fn.function_name,
                "KMS_KEY_ID": feed_key.key_id,
                "REQUIRE_KMS": "1",
                # Chat timeout guard: keep each model attempt under 8s and total chain under 20s
                # so the 29s Lambda limit is never reached. Worker functions use higher defaults.
                "BEDROCK_READ_TIMEOUT_SECONDS": "8",
                "BEDROCK_CHAIN_BUDGET_SECONDS": "20",
                # Prefer Nova Lite first on API function — fast, cheap, and less likely to be
                # throttled by concurrent material-processing jobs that use the heavier models.
                "MODEL_MAIN_FALLBACKS": "amazon.nova-lite-v1:0,openai.gpt-oss-120b-1:0,mistral.mistral-large-3-675b-instruct,us.anthropic.claude-sonnet-4-6",
            },
        )
        process_syllabus_fn.grant_invoke(api_fn)
        process_material_fn.grant_invoke(api_fn)
        color_worker_fn.grant_invoke(api_fn)
        feed_key.grant_encrypt_decrypt(api_fn)
        table.grant_read_write_data(api_fn)
        upload_bucket.grant_read_write(api_fn)
        api_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"],
        ))

        # ── HTTP API ──────────────────────────────────────────────────────────
        http_api = apigw.HttpApi(
            self, "HttpApi",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigw.CorsHttpMethod.ANY],
                allow_headers=["authorization", "content-type"],
            ),
        )  # replaced with the exact origins below, once the CloudFront domains exist
        jwt_authorizer = authorizers.HttpJwtAuthorizer(
            "CognitoAuth",
            jwt_issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}",
            jwt_audience=[user_pool_client.user_pool_client_id],
        )

        # Public routes (no JWT)
        # (/admin/* is added, authorised by the staff pool, by AdminSite below)
        for route_id, path in [
            ("PublicRoutes", "/public/{proxy+}"),
            ("CalRoute", "/cal/{proxy+}"),
        ]:
            http_api.add_routes(
                path=path,
                methods=[apigw.HttpMethod.ANY],
                integration=integrations.HttpLambdaIntegration(route_id, api_fn),
            )

        # Protected routes (JWT required).
        # Explicitly list methods — do NOT include ANY or OPTIONS.
        # OPTIONS preflights must never hit an authorizer; API Gateway handles them automatically
        # via cors_preflight above. ANY would intercept OPTIONS and return 401, blocking all browsers.
        http_api.add_routes(
            path="/{proxy+}",
            methods=[
                apigw.HttpMethod.GET, apigw.HttpMethod.POST,
                apigw.HttpMethod.PUT, apigw.HttpMethod.PATCH,
                apigw.HttpMethod.DELETE,
            ],
            integration=integrations.HttpLambdaIntegration("ProtectedRoutes", api_fn),
            authorizer=jwt_authorizer,
        )

        # ── Admin console (separate staff site; see ADMIN.md) ─────────────────
        admin_site = AdminSite(self, "AdminSite", http_api=http_api, api_fn=api_fn)

        # ── CloudFront ────────────────────────────────────────────────────────
        distribution = cloudfront.Distribution(
            self, "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(website_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_page_path="/index.html",
                    response_http_status=200,
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_page_path="/index.html",
                    response_http_status=200,
                    ttl=Duration.seconds(0),
                ),
            ],
        )

        # ── CORS: only our two sites (and local dev) may call the API from a browser ──
        # Native apps send no Origin header, so this does not affect the Expo app. Escape hatch on the
        # CFN resource (not cors_preflight) because the CloudFront domains don't exist when http_api is built.
        cfn_api = http_api.node.default_child
        cfn_api.cors_configuration = apigw.CfnApi.CorsProperty(
            allow_origins=[
                f"https://{distribution.distribution_domain_name}", admin_site.url,
                "http://localhost:5173", "http://localhost:5199",  # Vite dev server and the Designer's preview
            ],
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["authorization", "content-type"],
            max_age=3600,
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "TableName", value=table.table_name)
        CfnOutput(self, "UploadBucketName", value=upload_bucket.bucket_name)
        CfnOutput(self, "WebsiteBucketName", value=website_bucket.bucket_name)
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "ApiUrl", value=http_api.api_endpoint)
        CfnOutput(self, "CloudFrontUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "DistributionId", value=distribution.distribution_id)
