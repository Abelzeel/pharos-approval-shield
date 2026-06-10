# classify-spender

Look up a spender address in `assets/known-good-dapps.json` and return a
risk classification.

## When to use

Every time the scanner surfaces an approval. The output drives the
`risk` field in the report.

## Classification rules

| Condition | Risk |
|-----------|------|
| Spender is `0x0` (zero address) | `ok` — sentinel, not a real contract |
| Spender is in `known-good-dapps.json` and category ∈ {dex, lending, bridge, nft-marketplace, staking} | `ok` |
| Spender is in `known-good-dapps.json` but category = `unverified` | `medium` |
| Spender not in allowlist and approval is **not** infinite | `medium` |
| Spender not in allowlist and approval **is** infinite | `high` |
| Spender matches a `risk-signatures.json` entry (e.g. Permit2 hit) | `high` or `critical` |
| Contract has no deployed code at the address | `high` (phantom approval) |

## How the Agent should phrase the result

- On `ok`: "Spender is on the allowlist (<category>). Allowance is normal
  for this kind of dApp."
- On `medium`: "Spender is not on the allowlist. This does not mean it is
  unsafe — it means we have not audited it. The approval is <partial/infinite>."
- On `high`: "Spender is unknown AND the approval is infinite. Recommend
  revoking."
- On `critical`: "Match against known phishing signature. Move funds and
  revoke all approvals."

## Adding to the allowlist

Maintainers may add new entries via PR. Required:

- Contract address (checksummed)
- Name + category
- Audit report URL (or a verifiable deploy tx from a known team)
- Date added

The allowlist is a *hint*, not a guarantee. Agents must not treat "on
allowlist" as "safe to leave allowance open forever."

## Future work

- Pull deployment tx + age from the Pharos explorer API to factor into
  the score.
- Cross-reference against GoPlus / GoPlus Security's contract audit DB
  when available.
