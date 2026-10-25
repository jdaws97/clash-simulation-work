#!/usr/bin/env bash
# Offline Rust verification; callable from any working directory.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$HOME/.cargo/env" ]]; then
    . "$HOME/.cargo/env"
fi
# Windows (Git Bash): rustup installs cargo here without an env script.
export PATH="$HOME/.cargo/bin:$PATH"
export CARGO_TARGET_DIR="${1:-${CARGO_TARGET_DIR:-/tmp/clash-target-ws}}"
mkdir -p "$CARGO_TARGET_DIR"
export CARGO_TARGET_DIR="$(cd "$CARGO_TARGET_DIR" && pwd)"
export BASELAB_CATALOG="$ROOT/rust/data/catalog.json"
TEMP="$(mktemp -d "${TMPDIR:-/tmp}/clash-verify.XXXXXXXX")"
trap 'rm -rf "$TEMP"' EXIT
cd "$ROOT"

MANIFEST="$ROOT/Cargo.toml"
BIN="$CARGO_TARGET_DIR/release/clash"
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) BIN="$BIN.exe" ;;
esac

cargo fmt --manifest-path "$MANIFEST" --all -- --check
cargo build --manifest-path "$MANIFEST" --workspace --all-targets --release --locked --offline
cargo test --manifest-path "$MANIFEST" --workspace --release --locked --offline
if ! cargo clippy --version >"$TEMP/clippy-version.txt" 2>&1; then
    printf '%s\n' 'Clippy is unavailable locally; no components will be downloaded.'
    cat "$TEMP/clippy-version.txt"
elif cargo clippy --manifest-path "$MANIFEST" --workspace --all-targets --release --locked --offline -- -D warnings >"$TEMP/clippy-strict.txt" 2>&1; then
    cat "$TEMP/clippy-strict.txt"
else
    printf '%s\n' 'Clippy warnings are advisory during G1/G2; strict report follows.'
    cat "$TEMP/clippy-strict.txt"
    cargo clippy --manifest-path "$MANIFEST" --workspace --all-targets --release --locked --offline
fi

FIXTURES="$ROOT/fixtures"
"$BIN" golden check "$FIXTURES/golden/cases.jsonl" "$FIXTURES/golden/expected.jsonl" --threads 1
"$BIN" golden check "$FIXTURES/golden/cases.jsonl" "$FIXTURES/golden/expected.jsonl" --threads 4
"$BIN" golden plans check "$FIXTURES/golden/plans.jsonl" --root "$ROOT"
"$BIN" guardian-check
"$BIN" armysearch-proof --root "$ROOT" --catalog "$BASELAB_CATALOG" --account "$ROOT/data/your-levels.json" --fuzz 4096 --out "$TEMP/armysearch"
"$BIN" layout proof "$ROOT" "$TEMP/layout.json"
"$BIN" basesearch-proof "$ROOT" "$TEMP/basesearch.json"
cargo test --manifest-path "$MANIFEST" -p clash-vidmine --release --locked --offline
printf '%s\n' 'ALL CHECKS PASSED'
