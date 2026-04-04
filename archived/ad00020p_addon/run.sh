#!/usr/bin/with-contenv bashio

WEBHOOK_URL=$(bashio::config 'webhook_url')
RECEIVER_NAME=$(bashio::config 'receiver_name')

bashio::log.info "Starting IR Daemon..."
bashio::log.info "Webhook URL: ${WEBHOOK_URL}"
bashio::log.info "Receiver Name: ${RECEIVER_NAME}"

python3 -u /app/ir_daemon.py --url "${WEBHOOK_URL}" --receiver "${RECEIVER_NAME}"
