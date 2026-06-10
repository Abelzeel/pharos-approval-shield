# scan-approvals

Discover every active ERC-20 token approval for a Pharos wallet.

## When to use

User asks: "scan my approvals", "what tokens can this contract spend?", "audit
my allowances", "is my wallet safe?", or any time the Agent is about to
recommend an `approve()` and needs to know what is already open.

## How it works

We do **not** trust the user to remember their approvals. We scan on-chain
state.

1. **Discover tokens + spenders** by walking back through `Approval(address,
   address, uint256)` logs (topic0
   `0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925`)
   where the owner topic matches the wallet. We use the most recent spender
   per token from the log history.
2. **Read current allowance** for each (token, spender) pair via
   `cast call <token> "allowance(address,address)(uint256)" <owner> <spender>`.
3. **Classify** each approval:
   - `is_infinite = allowance == uint256.max` → risk = `high`
   - spender not on `assets/known-good-dapps.json` → risk bumped to `medium`
     (or `high` if combined with infinite)
4. **Cap** the scan at `--max-tokens` (default 200) for performance.

## Reference command

```bash
python3 scripts/scan.py \
  --wallet 0xYourWallet \
  --network atlantic-testnet \
  --lookback-blocks 50000
```

## Output

JSON with this shape:

```json
{
  "approvals": [
    {
      "token": "0xabc...",
      "token_name": "USDC",
      "spender": "0xdef...",
      "spender_name": "Unknown",
      "allowance_raw": "115792089237316195423570985008687907853269984665640564039457584007913129639935",
      "allowance_human": "infinite",
      "is_infinite": true,
      "risk": "high",
      "reasons": [
        "Infinite approval (uint256 max) — drainer can sweep full balance.",
        "Spender is not on the known-good allowlist."
      ]
    }
  ]
}
```

## What the Agent should say

After running, present a table:

| Token | Spender | Allowance | Risk | Why |
|-------|---------|-----------|------|-----|
| USDC | 0xdef… | infinite | high | Infinite + unknown spender |

Then explicitly **offer to generate a revoke plan** (`--emit-revoke-plan`).
Do not auto-revoke. Auto-revoking is the agent equivalent of an unprompted
`rm -rf`.

## Edge cases

- **No contracts in log history.** Means the wallet has never made an
  ERC-20 `approve()` call within `--lookback-blocks`. Report "0 active
  approvals" and stop.
- **Allowance returns 0.** The user previously approved then revoked (or
  transferred the token). Skip silently.
- **RPC times out.** Retry once with `--rpc-fallback`. If still failing,
  ask the user to provide a custom `--rpc-url` (e.g. their own endpoint).
- **Token has no `symbol()` or `decimals()`.** Likely not ERC-20. Skip.
- **Spender is `0x0`.** This is a *revoke* signature (approve with value
  0). Skip with a debug log.

## Performance

- Log scan is the expensive step. On Atlantic testnet, 50k blocks scans in
  ~2–5 seconds.
- 200 token lookups via `cast call` is ~30 seconds. If this matters, the
  Agent should pre-filter tokens by symbol or non-zero balance first.
