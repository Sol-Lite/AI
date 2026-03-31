#!/bin/bash
set -e

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
pip3 install -r requirements.txt --quiet
echo "dependencies installed"
