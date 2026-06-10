# safety-report

One-shot JSON safety report combining all sub-scans.

## When to use

When the user just wants "is my wallet safe?" with a single command. The
output is a structured JSON that the Agent can summarize in chat or
attach to a ticket.

## How to invoke

```bash
python3 scripts/scan.py \
  --wallet 0xYourWallet \
  --network atlantic-testnet \
  --emit-revoke-plan \
  --out demo/wallet-report.json
```

## Output schema

```typescript
type SafetyReport = {
  wallet: string;
  network: string;
  chain_id: number;
  rpc_url: string;
  scanned_at: number;        // unix seconds

  summary: {
    total_active_approvals: number;
    infinite_approvals: number;
    unknown_spenders: number;
    operator_approvals: number;
    phishing_hits: number;
    revoke_plan_steps: number;
    highest_risk_token: string | null;
  };

  approvals: Approval[];             // ERC-20
  permit2_approvals: Approval[];     // Permit2 (if deployed)
  operator_approvals: Approval[];    // ERC-721/1155 setApprovalForAll
  phishing_hits: PhishingHit[];

  revoke_plan: RevokeStep[];
  contract_scores: Record<string, number>;  // address -> 0..100
};

type Approval = {
  token: string;
  token_name: string;
  spender: string;
  spender_name: string;
  allowance_raw: string;
  allowance_human: string;
  is_infinite: boolean;
  risk: "critical" | "high" | "medium" | "low" | "ok";
  reasons: string[];
};

type PhishingHit = {
  id: string;
  severity: "critical" | "high" | "medium" | "low";
  spender: string;
  tx_hash: string;
  block_number: number;
  evidence: string;
};

type RevokeStep = {
  token: string;
  spender: string;
  to: string;             // token contract
  value: "0x0";
  data: string;           // approve(spender, 0) calldata
  estimated_gas: number;
  priority: number;       // 1 = highest
};
```

## How the Agent should render the summary

```
🛡️  Pharos Approval Shield — Wallet Safety Report
Wallet:    0x1234…abcd
Network:   Atlantic Testnet
Scanned:   2026-06-10 02:30 UTC

Summary
  Total active approvals:  3
  Infinite approvals:      1
  Unknown spenders:        2
  Operator approvals:      0
  Phishing hits:           0
  Revoke plan steps:       2

Top risks
  1. USDC → 0xdead…beef   [HIGH] infinite + unknown
  2. WETH → 0xbeef…cafe   [MEDIUM] partial + unknown

Recommended action
  Generate a revoke plan to clear 2 risky approvals.
  Estimated total gas: ~100,000 (≈ 0.0001 PHRS at 1 gwei).
```

## Privacy

- Reports are written to `--out` (default: stdout). The Agent must NEVER
  paste the wallet address into a public log without the user's
  permission.
- The report does **not** include the private key.
- The `rpc_url` is included for reproducibility — strip it if sharing
  publicly.
