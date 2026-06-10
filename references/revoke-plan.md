# revoke-plan

Generate a list of `approve(spender, 0)` transactions that, when signed,
clear every risky approval the scanner found.

## When to use

After `scan-approvals` returns at least one `high` or `medium` approval
and the user says "revoke them" or "clean up my wallet."

## How to invoke

```bash
python3 scripts/scan.py \
  --wallet 0xYourWallet \
  --network atlantic-testnet \
  --emit-revoke-plan \
  --out demo/wallet-report.json
```

This produces `demo/wallet-report.json` with a `revoke_plan` array. Each
entry has:

```json
{
  "token": "0xabc...",
  "spender": "0xdef...",
  "to": "0xabc...",
  "value": "0x0",
  "data": "0x095ea7b3...",     // approve(spender, 0) calldata
  "estimated_gas": 51234,
  "priority": 1
}
```

## To execute (USER must do this, not the agent)

```bash
export PRIVATE_KEY=0x...
./scripts/execute-revoke.sh demo/wallet-report.json
```

The script:
- Refuses to run without `PRIVATE_KEY` set
- Refuses to run on mainnet unless `--i-understand-mainnet` is passed
- Prompts `y/N` before each transaction

## Why the agent does NOT auto-execute

- **Irreversibility.** Once you sign an `approve(spender, 0)` the previous
  approval is cleared. If you didn't mean to, you have to re-approve.
- **Front-running risk on mainnet.** A drainer watching the wallet can
  try to race a revoke to extract value. Best practice is to revoke from
  a private RPC or via Flashbots (when supported on Pharos).
- **User consent.** The whole point of an "agent with a wallet" is that
  a human stays in the loop for write operations.

## Gas notes

- Each `approve(spender, 0)` is ~50,000 gas.
- 10 revokes ≈ 500,000 gas ≈ 0.0005 PHRS at 1 gwei.
- The script uses `cast estimate` to set per-tx gas limits, but you can
  override with `--gas-price` if you want.

## What if a spender re-approves itself?

Some contracts (rare, mostly malicious) have a `setApproval` fallback that
re-grants the allowance on `transferFrom`. The revoke will look
"successful" but the spender can drain again. To detect:

1. Wait one block after the revoke.
2. Re-read `allowance()`.
3. If it is non-zero, **do not** interact with that contract again —
   treat it as a malicious upgradeable proxy.

This is a known footgun in DeFi and the Agent should warn the user about
it when revoking to unknown spenders.
