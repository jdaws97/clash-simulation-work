#!/usr/bin/env bash
# Compatibility entry point; use scripts/verify.sh for workspace verification.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/scripts/verify.sh" "$@"
