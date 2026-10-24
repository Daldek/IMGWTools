#!/usr/bin/env bash
# Quality gate (DEV-7.6), template from Nogat standards/ci/gate.sh.
# Copy to scripts/gate.sh together with check-commits.sh and set the project
# settings below; nothing else should need editing.
#
# Usage: scripts/gate.sh [extra pytest arguments]
# Runs, in order: ruff format --check, ruff check, mypy, one pytest call over
# tests/ with coverage (contract tests included), and the commit step
# (scripts/check-commits.sh: identity preflight, then message checks). The
# first failure stops it.
set -euo pipefail

# --- project settings --------------------------------------------------------
PACKAGE="imgwtools"                 # import name, measured by coverage
TYPED_PATHS=(src tests)             # mypy targets (DEV-7.3)
# Marker expression of the gate (DEV-10.1); an `app` project without a local
# database uses "not live and not db".
OFFLINE="not live"
# ------------------------------------------------------------------------------

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() { printf '\n== %s\n' "$1"; }
fail() { printf 'gate: %s\n' "$1" >&2; exit 1; }

command -v uv >/dev/null || fail "uv not found (DEV-6.2): https://docs.astral.sh/uv/"

started=$SECONDS

# The environment belongs to this checkout: in a git worktree uv creates the
# worktree's own .venv, so the gate always tests the code it runs from.
step "uv sync --locked"
uv sync --locked --all-extras

run() { uv run --no-sync "$@"; }

step "ruff format --check"
run ruff format --check .

step "ruff check"
run ruff check .

step "mypy"
run mypy "${TYPED_PATHS[@]}"

step "pytest (tests/, coverage)"
# ${@+"$@"} keeps an empty argument list safe under set -u on macOS bash 3.2.
run pytest tests -m "$OFFLINE" \
  --cov="$PACKAGE" --cov-report=term-missing:skip-covered -q ${@+"$@"}

step "commit step"
bash "$ROOT/scripts/check-commits.sh"

printf '\nGATE OK (%d s)\n' "$((SECONDS - started))"
