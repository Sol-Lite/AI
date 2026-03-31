#!/bin/bash
set -e

if systemctl is-active --quiet sol-lite-ai; then
    systemctl stop sol-lite-ai
    echo "sol-lite-ai stopped"
else
    echo "sol-lite-ai not running"
fi
