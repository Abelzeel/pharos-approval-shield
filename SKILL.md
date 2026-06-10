---
name: pharos-approval-shield
description: >
  REQUIRED whenever a Pharos wallet, agent, or user asks about token approvals,
  ERC-20 allowances, Permit2 authorizations, NFT operator rights, suspicious
  contract activity, phishing signatures, or wallet safety. Invoked for tasks
  like "scan my approvals", "what contracts can spend my tokens?", "is this
  approval safe?", "revoke allowance", "decode this phishing tx", or "give me a
  wallet safety report". Builds a risk-scored report from on-chain Allowance /
  Approval events, classifies spenders against an allowlist, flags infinite
  approvals and known-bad signatures, and returns a one-click revoke plan.
  Without this skill the agent will guess at allowance state and miss phishing
  patterns that are present on-chain.
version: 0.1.0
requires:
  anyBins:
    - cast
    - jq
    - python3
---
# Pharos Approval Shield

A defensive Skill for AI Agents operating on Pharos. Audits ERC-20 allowances,
Permit2 authorizations, ERC-721/ERC-1155 operator rights, and recent phishing
signatures — then returns a prioritized, risk-scored report and a one-click
revoke plan.

Designed to be composed with `pharos-skill-engine` (uses the same RPC
configuration from `assets/networks.json`) and consumed by Agents built in
Anvita Flow (Phase 2 of the hackathon).

## What This Skill Is For

Pharos's agent economy means **agents will sign transactions on behalf of
users**. Before any agent can move value, it has to either:
1. Hold an `ERC-20.approve(agent, amount)` allowance, or
2. Use a Permit2 / off-chain signature that grants spend rights

This Skill gives an Agent the ability to **see, score, and revoke** those
permissions — turning a wallet into something an Agent can safely touch.

## Capabilities (Index)

| User Need | Capability | Detailed Instructions |
|-----------|-----------|----------------------|
| List every active token approval for a wallet | `scan-approvals` | → `references/scan-approvals.md` |
| Decode a single Approval event into human language | `decode-approval` | → `references/decode-approval.md` |
| Check whether a spender is on the known-good allowlist | `classify-spender` | → `references/classify-spender.md` |
| Scan recent wallet activity for phishing signatures (Permit, Permit2, setApprovalForAll, eth_sign) | `phishing-scan` | → `references/phishing-scan.md` |
| Generate a revoke transaction plan (gas + calldata) | `revoke-plan` | → `references/revoke-plan.md` |
| Generate a one-shot JSON safety report for the wallet | `safety-report` | → `references/safety-report.md` |
| Risk-score a contract (0–100, with explainable breakdown) | `contract-score` | → `references/contract-score.md` |

## Prerequisites

1. **Foundry is installed** (mandatory — this Skill wraps `cast`, not raw
   `curl`). If `cast` is not found, run:
   ```bash
   curl -L https://foundry.paradigm.xyz | bash
   source ~/.zshenv && foundryup
   cast --version
   ```
2. **Python 3.10+** for the scanner (`scripts/scan.py`).
3. **Read-only operations require no private key**. Only `revoke-plan` → on-chain
   execution requires `$PRIVATE_KEY` (covered in `references/revoke-plan.md`).
4. **Optional: a Pharos testnet wallet** with at least 0.001 PHRS for revoke gas.

## Network Configuration

Reuses the canonical `pharos-skill-engine` schema. Read from
`assets/networks.json` (relative to this Skill). Default is
`atlantic-testnet`.

```bash
RPC_URL=$(jq -r '.networks[] | select(.name=="atlantic-testnet") | .rpcUrl' assets/networks.json)
```

If you call this Skill **alongside** `pharos-skill-engine`, point the
`assets/networks.json` symlink at the engine's copy to avoid drift.

## Quick Start

```bash
# 1. Configure target wallet
export TARGET_WALLET=0xYourWallet...

# 2. Run a full safety report (read-only, no key needed)
python3 scripts/scan.py --wallet "$TARGET_WALLET" --network atlantic-testnet

# 3. Output a prioritized revoke plan
python3 scripts/scan.py --wallet "$TARGET_WALLET" --network atlantic-testnet \
  --emit-revoke-plan --out demo/wallet-report.json

# 4. (Optional) Execute the revoke plan
export PRIVATE_KEY=0x...
bash scripts/execute-revoke.sh demo/wallet-report.json
```

## How an Agent Should Use This Skill

**Step A — Detect intent.** When a user says *"is my wallet safe?"*, *"check
my approvals"*, *"what can this contract do?"*, or any time an Agent is
about to request an `approve()` call from a user, **invoke this Skill first**.

**Step B — Run `safety-report`.** Use `scripts/scan.py --wallet <addr>`. Do
not trust the user's verbal description of approvals — always read on-chain
state. Never invent allowance state.

**Step C — Summarize risk.** Report:
- Total active approvals
- Count of *infinite* approvals (`uint256.max`)
- Count of approvals to *unknown* spenders (not in `assets/known-good-dapps.json`)
- Any matches against `assets/risk-signatures.json` (Permit2, drainer patterns)
- Top 3 highest-risk items to revoke

**Step D — Offer action.** Produce a revoke plan (`--emit-revoke-plan`).
**Always** ask the user to confirm before signing. Never auto-revoke.

## Security Reminders

- **Read-only by default.** This Skill reads on-chain state. It does not
  sign or send transactions unless the user explicitly runs `execute-revoke.sh`.
- **Never expose private keys** in chat history, logs, or the generated
  report file. The revoke plan file contains calldata + spender addresses
  only — no keys.
- **Mainnet confirmation.** If `--network mainnet` is selected, the
  scanner prints a `⚠️ MAINNET` banner before every read. Agents must
  re-confirm with the user before any mainnet revoke execution.
- **Allowlist is a hint, not a guarantee.** A spender being on
  `known-good-dapps.json` means it has been *seen* in audited contexts. A
  spender **not** on the list is not automatically malicious — it is
  *unknown*. Always show the user the spenders and let them decide.

## General Error Handling

| Error Scenario | CLI Error Signature | Handling |
|----------------|---------------------|----------|
| RPC unreachable | `connection refused` / timeout | Retry once with `--rpc-fallback`; if still failing, ask user to provide an alternate RPC |
| `cast` not installed | `command not found: cast` | Re-run the Foundry install block in Prerequisites |
| Invalid address | `invalid address` | Prompt the user to re-check `TARGET_WALLET` |
| Allowance lookup returns 0x | empty data | Means no contract code at that address — likely not ERC-20 |
| Block explorer API down | HTTP 5xx | Fall back to RPC-only mode; degrade gracefully and tell the user |
| Permission denied writing report | `Permission denied` | Tell user to pick a writable `--out` path |

## Files In This Skill

```
pharos-approval-shield/
├── SKILL.md                          # this file
├── references/
│   ├── scan-approvals.md
│   ├── decode-approval.md
│   ├── classify-spender.md
│   ├── phishing-scan.md
│   ├── revoke-plan.md
│   ├── safety-report.md
│   └── contract-score.md
├── assets/
│   ├── networks.json                 # Pharos networks (testnet + mainnet)
│   ├── known-good-dapps.json         # allowlist of audited spenders
│   └── risk-signatures.json          # Permit2 + drainer selector patterns
├── scripts/
│   ├── scan.py                       # the main scanner (Python)
│   └── execute-revoke.sh             # executes a generated revoke plan
├── demo/
│   ├── README.md                     # what to put in the demo video
│   └── sample-report.json            # example output for the README
├── LICENSE                           # MIT-0 (matches pharos-skill-engine)
└── README.md
```

## License

MIT-0 — free to use, modify, redistribute. No attribution required.
