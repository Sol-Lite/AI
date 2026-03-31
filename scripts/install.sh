#!/bin/bash
set -e

# AWS CLI v2 설치 (깨진 버전 덮어쓰기)
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install --update
rm -rf /tmp/awscliv2.zip /tmp/aws
echo "AWS CLI v2 installed"

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
