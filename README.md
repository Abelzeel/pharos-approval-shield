# Pharos Approval Shield

A defensive **Skill** for AI Agents operating on Pharos. Audits ERC-20
allowances, Permit2 authorizations, ERC-721/1155 operator rights, and
recent phishing signatures — then returns a prioritized, risk-scored
report and a one-click revoke plan.

Built for the **Skill-to-Agent Dual Cascade Hackathon** on Pharos × Anvita
Flow (Phase 1: Skill Hackathon, June 8 – June 15, 2026).

---

## What problem does this solve?

When an AI Agent operates on a user's behalf, it needs to hold approvals.
But the user has to trust the agent with those permissions. Before any
agent can move value safely, both sides need to know:

- What approvals are already open?
- Which spenders are trusted?
- Are any of them infinite (drainer vector)?
- Did the wallet recently sign a phishing permit?
- What is the smallest, cheapest set of revokes that closes risk?

This Skill answers all of those questions in one read-only pass.

---

## Why it's original

The official pharos-skill-engine ships a generic on-chain toolkit
(balance queries, contract reads, deploy, verify). It does NOT ship
anything for wallet safety, approval auditing, or phishing detection.

Existing work in this space (Revoke.cash, Pocket Universe, Blowfish) is
either browser-extension-based or paid SaaS — none of it is a composable
Skill an Agent can call directly.

This Skill is the only one (as of 2026-06-10) that:

- Targets the Pharos network specifically
- Returns a machine-readable revoke plan that Anvita Flow agents can consume directly in Phase 2
- Is read-only by default — the agent never signs without explicit user confirmation

---

## Quick start

### JavaScript (Recommended — no extra tools needed)

1. Clone the repo and install dependencies:
git clone https://github.com/Abelzeel/pharos-approval-shield.git
cd pharos-approval-shield
npm install

2. Run a safety scan:
node scripts/scan.js 0xYourWalletAddress

### Python + Foundry (Advanced)

1. Install Foundry:
curl -L https://foundry.paradigm.xyz | bash

2. Run a safety report:
python3 scripts/scan.py --wallet 0xYourWallet --network mainnet

3. Generate a revoke plan:
python3 scripts/scan.py --wallet 0xYourWallet --network mainnet --emit-revoke-plan --out demo/wallet-report.json

---

## Capabilities

| Capability | Use when |
|---|---|
| scan-approvals | Listing active ERC-20 approvals |
| decode-approval | Explaining a single Approval event |
| classify-spender | Checking if a spender is on the allowlist |
| phishing-scan | Looking for drainer signatures |
| revoke-plan | Generating the on-chain revoke transactions |
| safety-report | Doing all of the above in one call |
| contract-score | Heuristic 0-100 trust score |

---

## Architecture

SKILL.md — entry point, agent reads this first
references/ — deep-dive docs the agent pulls in per task
assets/
  networks.json — Pharos RPC config
  known-good-dapps.json — spender allowlist
  risk-signatures.json — phishing selector patterns
scripts/
  scan.js — JavaScript scanner (no Foundry needed)
  scan.py — Python scanner (requires Foundry)
  execute-revoke.sh — revoke executor (user-confirmed, never auto)
demo/
  README.md — demo video script
  sample-report.json — example output

---

## Network Details

- Network : Pharos Pacific Ocean Mainnet
- Chain ID : 1672
- RPC URL  : https://rpc.pharos.xyz
- Explorer : https://pharosscan.xyz
- Currency : PROS

---

## Demo Website

https://bs7k2wt8a4re.space.minimax.io

---

## Phase 2 Plan

The natural Phase 2 Agent is a Safe Wallet Agent that:

1. On user request, runs safety-report on demand
2. Schedules a daily check
3. Surfaces a Telegram or Discord alert when a new risky approval appears
4. Waits for explicit user confirmation before any revoke

---

## Hackathon Submission

- Hackathon: Skill-to-Agent Dual Cascade Hackathon
- Phase: 1 — Skill Hackathon
- Deadline: 2026-06-15
- BUIDL on DoraHacks: https://dorahacks.io/hackathon/pharos-phase1

---

## License

MIT-0 — free to use, modify, redistribute. No attribution required.