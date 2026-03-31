#!/bin/bash
set -e

# AWS CLI 설치 (없을 경우)
if ! command -v aws &> /dev/null; then
    curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    unzip -q /tmp/awscliv2.zip -d /tmp
    /tmp/aws/install
    rm -rf /tmp/awscliv2.zip /tmp/aws
    echo "AWS CLI installed"
fi

cd /opt/fastapi

# .env 복원 (Secrets Manager)
SECRET=$(aws secretsmanager get-secret-value \
    --secret-id sollite/ai/env \
    --region ap-northeast-2 \
    --query SecretString \
    --output text)
echo "$SECRET" | jq -r 'to_entries[] | .key + "=" + .value' > /opt/fastapi/.env
echo ".env restored from Secrets Manager"

# pip 의존성 설치
pip3.11 install -r requirements.txt --quiet
echo "dependencies installed"
