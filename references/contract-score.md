# contract-score

Heuristic, explainable 0–100 trust score for a contract address.

## When to use

When the user asks "is this contract safe?" or when the Agent is about to
recommend an interaction. Always pair the score with a short explanation
— never just a number.

## Heuristics (v0.1.0)

| Signal | Effect |
|--------|--------|
| No code at address | score = 0 |
| Code size < 500 bytes | score -= 20 (suspiciously small) |
| Code size > 5,000 bytes | score += 5 |
| Contract not verified on explorer | score -= 15 (TODO: requires explorer API) |
| Contract age < 7 days | score -= 15 (TODO: requires explorer API) |
| On allowlist | score += 30 |
| Matches a `risk-signatures.json` pattern | score -= 40 |
| Deployer has prior malicious deployments | score -= 30 (TODO: requires on-chain deployer trace) |

Base score: 50. Final score clamped to [0, 100].

## Render in chat

> Contract 0xdead…beef
> Score: 42 / 100  (lower is riskier)
> - Not on the known-good allowlist
> - Code size 312 bytes (suspiciously small)
> - No explorer verification
>
> Recommendation: do not interact until verified.

## Limitations

This is a **v0 heuristic**. It catches the obvious cases (unverified
contracts, infinite approvals, Permit2 drains) but cannot replace a real
audit. Never tell the user "this is safe" — always say "this is
relatively low-risk based on what we can see on-chain; the user should
still verify."

## Future work

- Pull verified-source / age / deployer info from the Pharos explorer
  API. (Currently no public endpoint discovered; the docs page is the
  best link to start with.)
- Cross-reference the deployer's other contracts.
- Optional: integrate SlowMist or GoPlus audit DBs.
