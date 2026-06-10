# phishing-scan

Scan a wallet's recent on-chain activity and off-chain signatures for
phishing indicators.

## When to use

- User asks "is my wallet compromised?", "did I sign something bad?",
  "check for drainer hits."
- Right after the user reports clicking a suspicious link.
- Before recommending a high-value transaction.

## What we look for

Loaded from `assets/risk-signatures.json`:

| ID | Pattern | Severity |
|----|---------|----------|
| `infinite-erc20-approval` | Approval event with value = uint256.max | high |
| `permit2-default-approve` | Permit2 `approve` with non-zero amount | high |
| `permit2-permit` | Off-chain Permit2 permit signature | **critical** |
| `erc20-permit` | Off-chain ERC-2612 permit signature | high |
| `set-approval-for-all` | ERC-721/1155 ApprovalForAll | high |
| `eth-sign-blank` | Blank `eth_sign` / `personal_sign` | **critical** |
| `increase-allowance` | `increaseAllowance` on unknown spender | medium |

## Limitations

**On-chain only.** Off-chain signatures (Permit, Permit2, eth_sign) are
*not* visible on-chain. We can only see the **result** of those signatures
(a subsequent drain tx). To see the signature itself requires either:

- A signed-message DB (not generally available on Pharos yet)
- The user's wallet history (MetaMask activity, Rabby history, etc.)

**Mitigation.** Tell the user to import their wallet into a tool that
shows signed messages (e.g. Pocket Universe, Rabby, Blowfish) and look
for unexpected permits.

## Reference command

```python
# scripts/scan.py runs this automatically when you call --emit-revoke-plan
python3 scripts/scan.py --wallet 0x... --network atlantic-testnet
```

Look at `report.phishing_hits` in the output JSON.

## If a critical hit is found

1. Tell the user: their wallet is **likely compromised**.
2. Recommend: move all funds to a **fresh wallet** (new private key).
3. Recommend: revoke **all** approvals (use the full revoke plan).
4. Do not ask the user to sign anything from the compromised wallet
   except revokes — the drainer could be watching and front-run.

## Future work

- Integrate with Pharos explorer's txlist API to fetch txs in bulk
  (faster than per-block log scanning).
- Integrate with an allowlist of known drainer kit addresses (Phalcon,
  Blocksec, SlowMist maintain such lists).
- Optional: pull ERC-20 transfer events from the wallet to detect
  outbound transfers to known mixer addresses.
