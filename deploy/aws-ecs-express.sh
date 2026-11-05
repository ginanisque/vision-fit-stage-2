#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${SCRIPT_DIR}/../service"
REGION="${AWS_REGION:-}"
SERVICE_NAME="${ECS_SERVICE_NAME:-ginani-visionfit-api}"
REPOSITORY="${ECR_REPOSITORY:-ginani-visionfit-api}"
EXECUTION_ROLE="${ECS_EXECUTION_ROLE_ARN:-}"
INFRASTRUCTURE_ROLE="${ECS_INFRASTRUCTURE_ROLE_ARN:-}"
SERVICE_ARN="${ECS_SERVICE_ARN:-}"
CORS_ORIGINS="${VISIONFIT_CORS_ORIGINS:-http://localhost:5173}"
RUNTIME_SECRET_ARN="${VISIONFIT_RUNTIME_SECRET_ARN:-}"
BOOTSTRAP_ADMINS="${VISIONFIT_BOOTSTRAP_ADMIN_EMAILS:-}"
RETENTION_DAYS="${VISIONFIT_RETENTION_DAYS:-30}"

for tool in aws docker python3; do
  command -v "$tool" >/dev/null || { echo "Required command not found: $tool" >&2; exit 1; }
done
[[ -n "$REGION" ]] || { echo "Set AWS_REGION to the AWS region for your grant." >&2; exit 1; }
[[ -n "$EXECUTION_ROLE" ]] || { echo "Set ECS_EXECUTION_ROLE_ARN to the ecsTaskExecutionRole ARN." >&2; exit 1; }
[[ -n "$RUNTIME_SECRET_ARN" ]] || { echo "Set VISIONFIT_RUNTIME_SECRET_ARN to the Secrets Manager ARN containing the VisionFit runtime JSON." >&2; exit 1; }
if [[ -z "$SERVICE_ARN" && -z "$INFRASTRUCTURE_ROLE" ]]; then
  echo "Set ECS_INFRASTRUCTURE_ROLE_ARN when creating a new service." >&2
  exit 1
fi
[[ "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]] || { echo "VISIONFIT_RETENTION_DAYS must be a positive integer." >&2; exit 1; }

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE_TAG="${VISIONFIT_IMAGE_TAG:-$(date -u +%Y%m%d-%H%M%S)}"
IMAGE="${REGISTRY}/${REPOSITORY}:${IMAGE_TAG}"

if ! aws ecr describe-repositories --repository-names "$REPOSITORY" --region "$REGION" >/dev/null 2>&1; then
  aws ecr create-repository --repository-name "$REPOSITORY" \
    --image-scanning-configuration scanOnPush=true --region "$REGION" >/dev/null
fi

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 -t "$IMAGE" "$SERVICE_DIR"
docker push "$IMAGE"

export IMAGE CORS_ORIGINS RUNTIME_SECRET_ARN BOOTSTRAP_ADMINS RETENTION_DAYS
CONTAINER_JSON="$(python3 -c '
import json, os
secret = os.environ["RUNTIME_SECRET_ARN"]
names = [
    "DATABASE_URL_POOLED", "NEON_AUTH_BASE_URL", "NEON_AUTH_JWKS_URL",
    "AWS_ENDPOINT_URL_S3", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "S3_REGION", "S3_BUCKET", "ROBOFLOW_ENABLED", "ROBOFLOW_API_KEY",
    "ROBOFLOW_WORKSPACE", "ROBOFLOW_KEYPOINT_WORKFLOW_ID",
]
print(json.dumps({
    "image": os.environ["IMAGE"],
    "containerPort": 8080,
    "environment": [
        {"name": "VISIONFIT_CORS_ORIGINS", "value": os.environ["CORS_ORIGINS"]},
        {"name": "VISIONFIT_BOOTSTRAP_ADMIN_EMAILS", "value": os.environ["BOOTSTRAP_ADMINS"]},
        {"name": "VISIONFIT_RETENTION_DAYS", "value": os.environ["RETENTION_DAYS"]},
        {"name": "VISIONFIT_RETENTION_ENABLED", "value": "true"},
    ],
    "secrets": [{"name": name, "valueFrom": f"{secret}:{name}::"} for name in names],
}))')"

COMMON_ARGS=(
  --execution-role-arn "$EXECUTION_ROLE"
  --primary-container "$CONTAINER_JSON"
  --health-check-path /api/health
  --cpu 1024
  --memory 2048
  --scaling-target '{"minTaskCount":1,"maxTaskCount":1}'
  --monitor-resources DEPLOYMENT
  --region "$REGION"
)

if [[ -n "$SERVICE_ARN" ]]; then
  aws ecs update-express-gateway-service --service-arn "$SERVICE_ARN" "${COMMON_ARGS[@]}"
else
  aws ecs create-express-gateway-service \
    --service-name "$SERVICE_NAME" \
    --infrastructure-role-arn "$INFRASTRUCTURE_ROLE" \
    "${COMMON_ARGS[@]}"
fi

echo "Deployment request submitted. Check the Amazon ECS console for the service URL and status."
