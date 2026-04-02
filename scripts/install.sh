#!/bin/bash
set -e

PYTHON_BIN="/usr/bin/python3"
HF_HOME_DIR="/opt/fastapi/.cache/huggingface"
if [ -x /usr/bin/python3.11 ]; then
    PYTHON_BIN="/usr/bin/python3.11"
fi
# AWS CLI v2 설치 (깨진 버전 덮어쓰기)
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install --update
rm -rf /tmp/awscliv2.zip /tmp/aws
echo "AWS CLI v2 installed"

cd /opt/fastapi
mkdir -p "$HF_HOME_DIR"
chown -R ec2-user:ec2-user /opt/fastapi/.cache

# .env 복원 (Secrets Manager)
SECRET=$(aws secretsmanager get-secret-value \
    --secret-id sollite/ai/env \
    --region ap-northeast-2 \
    --query SecretString \
    --output text)
echo "$SECRET" | jq -r 'to_entries[] | .key + "=" + .value' > /opt/fastapi/.env
echo ".env restored from Secrets Manager"

# 런타임과 동일한 Python으로 의존성 설치
echo "$PYTHON_BIN" > /opt/fastapi/.python-bin
"$PYTHON_BIN" -m pip install -r requirements.txt --quiet
echo "dependencies installed"

# local_files_only=True 를 위해 배포 시점에 모델/토크나이저를 공유 캐시에 미리 저장
HF_HOME="$HF_HOME_DIR" TRANSFORMERS_CACHE="$HF_HOME_DIR" "$PYTHON_BIN" -c "
from transformers import AutoTokenizer, BartForConditionalGeneration
AutoTokenizer.from_pretrained('EbanLee/kobart-summary-v3', use_fast=False)
BartForConditionalGeneration.from_pretrained('EbanLee/kobart-summary-v3')
"
echo "kobart-summary-v3 cached"
