#!/bin/bash
set -e

PYTHON_BIN="/usr/bin/python3"
if [ -f /opt/fastapi/.python-bin ]; then
    PYTHON_BIN="$(cat /opt/fastapi/.python-bin)"
elif [ -x /usr/bin/python3.11 ]; then
    PYTHON_BIN="/usr/bin/python3.11"
fi
# systemd 서비스 파일 생성 (최초 or 갱신)
cat > /etc/systemd/system/sol-lite-ai.service << 'EOF'
[Unit]
Description=Sol-Lite AI FastAPI Server
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/fastapi
EnvironmentFile=/opt/fastapi/.env
Environment=HF_HOME=/opt/fastapi/.cache/huggingface
Environment=TRANSFORMERS_CACHE=/opt/fastapi/.cache/huggingface
Environment=PYTHONUNBUFFERED=1
ExecStart=__PYTHON_BIN__ -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sed -i "s|__PYTHON_BIN__|$PYTHON_BIN|g" /etc/systemd/system/sol-lite-ai.service

systemctl daemon-reload
systemctl enable sol-lite-ai
systemctl start sol-lite-ai
echo "sol-lite-ai started"
