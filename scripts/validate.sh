#!/bin/bash
set -e

for i in $(seq 1 10); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "000")
    if [ "$STATUS" = "200" ]; then
        echo "Health check passed (attempt $i)"
        exit 0
    fi
    echo "Attempt $i: status=$STATUS, waiting..."
    sleep 10
done

echo "Health check failed after 10 attempts"
exit 1
