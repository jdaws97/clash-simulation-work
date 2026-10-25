#!/bin/bash
# One verification gate for every Rust change (Windows Git Bash or WSL).
# Usage: rust/verify.sh [TARGET_DIR]   (default: rust/target-verify)
# Prints one line per check and exits non-zero on the first failure.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/rust" || exit 1
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
export PATH="$HOME/.cargo/bin:$PATH"
export CARGO_TARGET_DIR="${1:-$ROOT/rust/target-verify}"
export BASELAB_CATALOG="$ROOT/rust/data/catalog.json"
EXE=""; case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) EXE=".exe";; esac
BIN="$CARGO_TARGET_DIR/release/baselab-engine$EXE"
fail() { echo "FAIL: $1"; exit 1; }
step() { printf '%-22s ' "$1"; }

step "fmt";        cargo fmt --check >/dev/null 2>&1 && echo ok || fail "cargo fmt --check"
step "build";      cargo build --release 2>&1 | grep -q '^error' && fail "build" || echo ok
step "tests";      out=$(cargo test --release 2>&1); echo "$out" | grep -q 'test result: FAILED\|^error' && fail "cargo test" || echo "ok ($(echo "$out" | grep -o '[0-9]* passed' | awk '{s+=$1} END {print s}') passed)"
cd "$ROOT" || exit 1
step "battle goldens";  r=$("$BIN" golden check rust/golden/cases.jsonl rust/golden/expected.jsonl 2>&1 | tail -1); echo "$r" | grep -q 'failed=0' && echo "$r" || fail "$r"
step "plan goldens";    r=$("$BIN" golden plans check rust/golden/plans.jsonl 2>&1 | grep 'golden plans check' | head -1); echo "$r" | grep -q 'failed=0' && echo "$r" || fail "$r"
step "guardian-check";  r=$("$BIN" guardian-check 2>&1 | tail -1); echo "$r" | grep -q passed && echo "$r" || fail "$r"
step "armysearch-proof"; r=$("$BIN" armysearch-proof --root . --fuzz 4096 --out "${TMPDIR:-/tmp}/verify-proof" 2>&1 | tail -1); echo "$r" | grep -q '"status":"passed"' && echo ok || fail "armysearch-proof: ${r:0:300}"
echo "ALL CHECKS PASSED"
