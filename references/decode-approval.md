# decode-approval

Turn a single ERC-20 Approval event into a human-readable description.

## When to use

User provides a tx hash or log entry and asks "what did this do?", or when
the scanner surfaces an approval and you want to render a clean explanation
in chat.

## Reference command

```bash
cast tx <tx_hash> --rpc-url "$RPC_URL"
cast logs --from-block <n> --to-block <n> \
  0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925 \
  --json
```

The event signature is:

```solidity
event Approval(address indexed owner, address indexed spender, uint256 value);
```

Decoded fields:

- `owner` (topic1) — the wallet that granted the allowance
- `spender` (topic2) — the contract that can now move tokens
- `value` (data) — the allowance in raw token units

## How to render

> Approval detected
> Owner:    0x1234…abcd
> Spender:  0xdead…beef  ← *Unknown — not on allowlist*
> Token:    USDC (0xabcd…)
> Value:    115792089237316195423570985008687907853269984665640564039457584007913129639935
>          = **infinite** (uint256 max)
> Risk:     HIGH
> Tx:       0xcafe…

## Decision rules

| Value | Render |
|-------|--------|
| `value == 0` | "Revoke (allowance cleared)" |
| `value == uint256.max` | "**Infinite** approval — full balance at risk" |
| `value > 0` and `< uint256.max` | "Partial approval: <human amount>" |
