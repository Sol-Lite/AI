#!/bin/bash
set -e

# systemd 서비스 파일 생성 (최초 or 갱신)
cat > /etc/systemd/system/sol-lite-ai.service << 'EOF'
[Unit]
Description=Sol-Lite AI FastAPI Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/fastapi
EnvironmentFile=/opt/fastapi/.env
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable sol-lite-ai
systemctl start sol-lite-ai
echo "sol-lite-ai started"
