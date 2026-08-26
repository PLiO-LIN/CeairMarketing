#!/bin/sh
set -eu

if [ -z "${BASIC_AUTH_USER:-}" ] || [ -z "${BASIC_AUTH_PASSWORD:-}" ]; then
  echo "BASIC_AUTH_USER and BASIC_AUTH_PASSWORD are required" >&2
  exit 1
fi

htpasswd -bcB /etc/nginx/.htpasswd "$BASIC_AUTH_USER" "$BASIC_AUTH_PASSWORD"
chown nginx:nginx /etc/nginx/.htpasswd
chmod 640 /etc/nginx/.htpasswd
