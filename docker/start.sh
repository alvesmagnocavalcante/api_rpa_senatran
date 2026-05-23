#!/usr/bin/env bash
set -e

export DISPLAY=${DISPLAY:-:1}

# Garante que o Chromium use profile gravável
mkdir -p /tmp/chromium-profile

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
