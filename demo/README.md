# Demo Video Script — Pharos Approval Shield

A 90-second walkthrough you can record and submit to DoraHacks.

## Setup (do this before recording)

```bash
# 1. Clone & install
git clone https://github.com/your-username/pharos-approval-shield.git
cd pharos-approval-shield
curl -L https://foundry.paradigm.xyz | bash
source ~/.zshenv && foundryup

# 2. Get testnet PHRS + a wallet with some test ERC-20 approvals
#    (use the Atlantic testnet faucet — see Pharos docs)

# 3. Configure
export TARGET_WALLET=0xYourTestWallet...
```

## Scene-by-scene (90 seconds total)

### Scene 1 — Hook (0:00–0:10)
> "AI agents are about to sign transactions on behalf of users on Pharos.
> But how does an agent know what's already open in a wallet — and what's
> safe to sign next? Pharos Approval Shield is a Skill that audits every
> active approval and produces a one-click revoke plan."

### Scene 2 — The scan (0:10–0:35)
Run the safety report in the terminal:
```bash
python3 scripts/scan.py --wallet "$TARGET_WALLET" --network atlantic-testnet
```
Show the output table:
- 3 active approvals
- 1 infinite USDC approval to an unknown spender
- 0 phishing hits

### Scene 3 — The risk explanation (0:35–0:55)
Open the JSON report (`demo/sample-report.json` or your live output) and
point at the `reasons` array. Explain: an unknown spender with an
infinite approval is a drainer vector.

### Scene 4 — The revoke (0:55–1:25)
Generate the revoke plan and walk through the executor:
```bash
python3 scripts/scan.py --wallet "$TARGET_WALLET" --network atlantic-testnet \
  --emit-revoke-plan --out demo/wallet-report.json

export PRIVATE_KEY=0x...
./scripts/execute-revoke.sh demo/wallet-report.json
```

### Scene 5 — Wrap (1:25–1:30)
> "Read-only by default. The user always confirms each revoke. MIT-0
> license. Drop-in compatible with `pharos-skill-engine`. Phase 2 ready."

## Files referenced in the demo

- `demo/sample-report.json` — example output for screenshots/slides
- `scripts/scan.py` — the scanner
- `scripts/execute-revoke.sh` — the executor
- `SKILL.md` — the Skill definition

## What to include in the DoraHacks submission

1. **GitHub repo link** (this repo)
2. **Demo video** (≤ 3 minutes, upload to YouTube or Loom)
3. **Short description** (~150 words) explaining the problem and solution
4. **Tags**: AgentSkill, Onchain, Security, Pharos, Anvita
