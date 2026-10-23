# AWS Deployment Guide: Strands Sentinel

This guide details how to take **Strands Sentinel: Zero-Trust Governance Agent** from local development into production on Amazon Web Services (AWS).

---

## 1. Amazon Bedrock Prerequisites

### 1.1 Enable Model Access
Before executing the agent on AWS, ensure model access is enabled for Claude 3.5 Sonnet:
1. Open the **Amazon Bedrock Console** in your target region (e.g., `us-east-1` or `us-west-2`).
2. Navigate to **Model access** in the bottom left menu.
3. Click **Modify model access** and check **Anthropic: Claude 3.5 Sonnet**.
4. Submit the request and verify the status displays **Access granted**.

### 1.2 IAM Task Role Permissions
The Sentinel agent requires permission to invoke Amazon Bedrock foundation models. Attach the policy defined in [`iam-policy.json`](./iam-policy.json) to your ECS Task Role:

```bash
aws iam create-policy \
    --policy-name StrandsSentinelBedrockPolicy \
    --policy-document file://deploy/aws/iam-policy.json
```

---

## 2. Containerizing & Pushing to Amazon ECR

Create Amazon Elastic Container Registry (ECR) repositories for the components:

```bash
# 1. Create repositories
aws ecr create-repository --repository-name sentinel-ledger --region us-east-1
aws ecr create-repository --repository-name sentinel-crm --region us-east-1
aws ecr create-repository --repository-name sentinel-agent --region us-east-1

# 2. Authenticate Docker with your ECR registry
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com

# 3. Build, tag, and push Go Ledger
docker build -t sentinel-ledger ./services/ledger
docker tag sentinel-ledger:latest ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/sentinel-ledger:latest
docker push ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/sentinel-ledger:latest

# 4. Build, tag, and push FastAPI CRM
docker build -t sentinel-crm ./services/crm
docker tag sentinel-crm:latest ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/sentinel-crm:latest
docker push ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/sentinel-crm:latest

# 5. Build, tag, and push Sentinel Agent
docker build -t sentinel-agent ./agent
docker tag sentinel-agent:latest ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/sentinel-agent:latest
docker push ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/sentinel-agent:latest
```

---

## 3. Running on Amazon ECS Fargate

### 3.1 Network Architecture & Private VPC
For zero-trust enterprise compliance:
- Run all containers in **Private Subnets** with no inbound public internet ingress.
- Utilize an **AWS PrivateLink VPC Endpoint for Amazon Bedrock** (`com.amazonaws.us-east-1.bedrock-runtime`) so the generative model traffic never traverses the public internet.
- Enable **AWS Cloud Map** or **ECS Service Connect** for private service discovery between the agent, the CRM, and the Go Ledger.

### 3.2 Registering the Task Definition
Update the placeholder account IDs in [`ecs-task-definition.example.json`](./ecs-task-definition.example.json) and register the task definition:

```bash
aws ecs register-task-definition \
    --cli-input-json file://deploy/aws/ecs-task-definition.example.json
```

### 3.3 Running as an ECS One-Off Task or Scheduled Job
In enterprise operational workflows, finance operations tasks are typically run on a schedule (e.g. hourly or upon an S3 drop):

```bash
aws ecs run-task \
    --cluster sentinel-cluster \
    --task-definition strands-sentinel \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-12345],securityGroups=[sg-67890],assignPublicIp=DISABLED}"
```

---

## 4. Alternative: AWS App Runner for Dashboard Services

If your operations team requires interactive browser access to the Go Ledger audit trail and FastAPI CRM dashboard:
1. Create an **AWS App Runner** service pointing to the `sentinel-ledger` container image on port `8081`.
2. Restrict access behind **AWS IAM Identity Center (SSO)** or an AWS WAF IP whitelist.
3. Keep the systemic kill switch endpoint (`POST /kill`) accessible internally to the agent and authenticated security leads.
