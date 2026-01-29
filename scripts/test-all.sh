#!/usr/bin/env bash
set -e

VERSIONS=("3.8" "3.9" "3.10" "3.11" "3.12" "3.13" "3.14")
FAILED=()
PASSED=()
SKIPPED=()

for ver in "${VERSIONS[@]}"; do
  PYTHON=$(mise where python "$ver" 2>/dev/null)/bin/python3 || true
  if [ ! -x "$PYTHON" ]; then
    echo "⏭  Python $ver — not installed, skipping"
    SKIPPED+=("$ver")
    continue
  fi

  echo ""
  echo "═══════════════════════════════════════════"
  echo "  Python $ver ($PYTHON)"
  echo "═══════════════════════════════════════════"

  VENV="/tmp/podonos-test-$ver"
  "$PYTHON" -m venv --clear "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -e ".[dev]"

  if "$VENV/bin/python" -m pytest tests/ -q; then
    PASSED+=("$ver")
  else
    FAILED+=("$ver")
  fi

  rm -rf "$VENV"
done

echo ""
echo "═══════════════════════════════════════════"
echo "  Summary"
echo "═══════════════════════════════════════════"
[ ${#PASSED[@]} -gt 0 ]  && echo "  PASSED:  ${PASSED[*]}"
[ ${#FAILED[@]} -gt 0 ]  && echo "  FAILED:  ${FAILED[*]}"
[ ${#SKIPPED[@]} -gt 0 ] && echo "  SKIPPED: ${SKIPPED[*]}"

[ ${#FAILED[@]} -eq 0 ]
