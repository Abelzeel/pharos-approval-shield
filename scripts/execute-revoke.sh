#!/usr/bin/env bash
# pharos-approval-shield / scripts/execute-revoke.sh
#
# Reads a revoke plan JSON (produced by scan.py --emit-revoke-plan) and sends
# the approve(spender, 0) transactions one by one.
#
# USAGE:
#   export PRIVATE_KEY=0x...
#   ./execute-revoke.sh path/to/wallet-report.json
#
# SAFETY:
#   - Will REFUSE to run if PRIVATE_KEY is not set.
#   - Will REFUSE to run if the report's network is "mainnet" unless
#     --i-understand-mainnet is passed.
#   - Prints a confirmation prompt before each transaction.
#
# REQUIRES: cast (Foundry), jq

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <report.json> [--i-understand-mainnet]" >&2
  exit 1
fi

REPORT="$1"
MAINNET_ACK="false"
if [[ "${2:-}" == "--i-understand-mainnet" ]]; then
  MAINNET_ACK="true"
fi

if [[ -z "${PRIVATE_KEY:-}" ]]; then
  echo "[fatal] PRIVATE_KEY env var not set. Aborting." >&2
  exit 2
fi

if ! command -v cast >/dev/null 2>&1; then
  echo "[fatal] 'cast' not found. Install Foundry first: https://book.getfoundry.sh/" >&2
  exit 3
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "[fatal] 'jq' not found. Install it (e.g. 'apt install jq' or 'brew install jq')." >&2
  exit 4
fi

NETWORK=$(jq -r '.network' "$REPORT")
if [[ "$NETWORK" == "mainnet" && "$MAINNET_ACK" != "true" ]]; then
  echo "[fatal] Report targets MAINNET. Re-run with --i-understand-mainnet to proceed." >&2
  exit 5
fi

RPC_URL=$(jq -r '.rpc_url' "$REPORT")
WALLET=$(jq -r '.wallet' "$REPORT")
STEPS=$(jq -r '.revoke_plan | length' "$REPORT")

echo "==> Pharos Approval Shield — Revoke Executor"
echo "    Network: $NETWORK"
echo "    Wallet:  $WALLET"
echo "    RPC:     $RPC_URL"
echo "    Steps:   $STEPS"
echo

for i in $(seq 0 $((STEPS - 1))); do
  TO=$(jq -r ".revoke_plan[$i].to" "$REPORT")
  DATA=$(jq -r ".revoke_plan[$i].data" "$REPORT")
  GAS=$(jq -r ".revoke_plan[$i].estimated_gas" "$REPORT")
  TOKEN=$(jq -r ".revoke_plan[$i].token" "$REPORT")
  SPENDER=$(jq -r ".revoke_plan[$i].spender" "$REPORT")

  echo "------------------------------------------------------------"
  echo "Step $((i + 1))/$STEPS"
  echo "  Token:   $TOKEN"
  echo "  Spender: $SPENDER"
  echo "  To:      $TO"
  echo "  Data:    ${DATA:0:18}…"
  echo "  Gas est: $GAS"
  read -r -p "Send this revoke? [y/N] " ans
  if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
    echo "  [skip] user declined"
    continue
  fi

  cast send --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY" \
    "$TO" "$DATA" --gas-limit "$GAS"
  echo
done

echo "==> Done."
