#!/usr/bin/env bash
# نصب اولیه = همان deploy.sh (هر دو بی‌خطر قابل تکرارند).
set -euo pipefail
exec bash "$(dirname "$0")/deploy.sh" "$@"
