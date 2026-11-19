#!/usr/bin/env bash
# Run the cggt unit tests with the active Python.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage_help() {
  echo "Usage: $(basename "$0") [-h]"
  echo "Run pytest for cggt."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage_help
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage_help >&2
      exit 1
      ;;
  esac
done

cd "${ROOT}"
python -m pytest -q
