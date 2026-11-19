#!/usr/bin/env bash
# Install cggt and test dependencies into the active Python (pyenv when .python-version is set).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage_help() {
  echo "Usage: $(basename "$0") [-h]"
  echo "Install the cggt package editable with dev dependencies."
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
python -m pip install -e ".[dev]"
