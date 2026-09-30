#!/bin/sh
set -eu

# Generate a stable per-installation encryption key on first start. The key is
# kept in the app_data volume, so users do not need to prepare an .env file.
if [ -z "${APP_SECRET_KEY:-}" ]; then
    SECRET_FILE=/data/app-secret
    mkdir -p /data
    if [ ! -s "$SECRET_FILE" ]; then
        umask 077
        python -c "import secrets; print(secrets.token_hex(32))" > "$SECRET_FILE"
    fi
    APP_SECRET_KEY=$(cat "$SECRET_FILE")
    export APP_SECRET_KEY
fi

exec "$@"

