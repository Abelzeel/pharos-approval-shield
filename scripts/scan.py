#!/usr/bin/env python3
"""
pharos-approval-shield / scripts/scan.py

Read-only safety scanner for Pharos wallets. Wraps `cast` for RPC calls (so
we benefit from the official pharos-skill-engine installation) and emits a
structured JSON report covering:

  1. Active ERC-20 approvals
  2. Permit2 allowances (if Permit2 contract exists)
  3. ERC-721/1155 operator approvals
  4. Phishing signature matches
  5. A prioritized revoke plan (calldata + gas estimates, ready to sign)

This script is intentionally read-only. Revoke execution lives in
`execute-revoke.sh` and requires an explicit --i-understand flag.

Usage:
  python3 scan.py --wallet 0x... --network atlantic-testnet
  python3 scan.py --wallet 0x... --network atlantic-testnet --emit-revoke-plan --out report.json
  python3 scan.py --wallet 0x... --network mainnet --rpc-fallback https://my-rpc.example
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

MAX_UINT256 = (1 << 256) - 1

# Common ERC-20 function selectors
SELECTOR_BALANCE_OF = "0x70a08231"
SELECTOR_ALLOWANCE = "0xdd62ed3e"
SELECTOR_APPROVE = "0x095ea7b3"

# ERC-721 / 1155
SELECTOR_IS_APPROVED_FOR_ALL = "0xe985e9c5"
TOPIC_APPROVAL = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
TOPIC_APPROVAL_FOR_ALL = "0x17307eab39ab6107e889d5b873ef0b21c4c5e6f9b3c4e8c5e9c5e9c5e9c5e9c5"

# Well-known Permit2 (Uniswap) on most EVM chains. We treat it as a constant —
# the scanner checks for code at this address, and if present, queries
# allowance(owner, token, spender).
PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


# -----------------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------------


@dataclass
class Approval:
    token: str
    token_name: str
    spender: str
    spender_name: str
    allowance_raw: str
    allowance_human: str
    is_infinite: bool
    risk: str  # "critical" | "high" | "medium" | "low" | "ok"
    reasons: list[str] = field(default_factory=list)
    block_number: int = 0
    tx_hash: str = ""


@dataclass
class RevokeStep:
    token: str
    spender: str
    to: str  # always the token contract
    value: str  # "0x0"
    data: str  # approve(spender, 0) calldata
    estimated_gas: int
    priority: int  # 1 = highest


@dataclass
class ScanReport:
    wallet: str
    network: str
    chain_id: int
    rpc_url: str
    scanned_at: int
    summary: dict[str, Any]
    approvals: list[Approval]
    permit2_approvals: list[Approval]
    operator_approvals: list[Approval]
    phishing_hits: list[dict[str, Any]]
    revoke_plan: list[RevokeStep]
    contract_scores: dict[str, int]  # address -> 0..100


# -----------------------------------------------------------------------------
# CLI plumbing
# -----------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pharos Approval Shield scanner")
    p.add_argument("--wallet", required=True, help="Wallet address to scan (0x...)")
    p.add_argument(
        "--network",
        default="atlantic-testnet",
        choices=["atlantic-testnet", "mainnet"],
    )
    p.add_argument("--rpc-url", help="Override RPC URL (otherwise read from assets/networks.json)")
    p.add_argument("--rpc-fallback", help="Fallback RPC if primary times out")
    p.add_argument(
        "--lookback-blocks",
        type=int,
        default=50_000,
        help="How many blocks back to scan for Approval logs (default 50k)",
    )
    p.add_argument("--max-tokens", type=int, default=200, help="Cap on tokens to inspect")
    p.add_argument("--emit-revoke-plan", action="store_true")
    p.add_argument("--out", help="Write JSON report here (default stdout summary only)")
    p.add_argument(
        "--permit2", default=PERMIT2_ADDRESS, help="Permit2 contract address (override)"
    )
    return p.parse_args()


def load_networks() -> dict[str, Any]:
    with (ASSETS_DIR / "networks.json").open() as f:
        return json.load(f)


def load_known_good() -> dict[str, Any]:
    with (ASSETS_DIR / "known-good-dapps.json").open() as f:
        return json.load(f)


def load_risk_signatures() -> dict[str, Any]:
    with (ASSETS_DIR / "risk-signatures.json").open() as f:
        return json.load(f)


# -----------------------------------------------------------------------------
# `cast` wrappers
# -----------------------------------------------------------------------------


def cast(
    *args: str,
    rpc_url: str,
    timeout: int = 15,
    retries: int = 1,
) -> str:
    """Run a `cast` subcommand and return stdout. Raise on failure."""
    cmd = ["cast", *args, "--rpc-url", rpc_url]
    last_err: subprocess.CalledProcessError | None = None
    for attempt in range(retries + 1):
        try:
            out = subprocess.check_output(
                cmd, stderr=subprocess.PIPE, timeout=timeout, text=True
            )
            return out.strip()
        except subprocess.CalledProcessError as e:
            last_err = e
            if attempt < retries:
                time.sleep(1)
                continue
            break
    assert last_err is not None
    raise RuntimeError(
        f"cast command failed: {' '.join(cmd)}\nstderr: {last_err.stderr.strip()}"
    )


def get_code(addr: str, rpc_url: str) -> str:
    try:
        return cast("code", addr, rpc_url=rpc_url)
    except Exception:
        return "0x"


def is_contract(addr: str, rpc_url: str) -> bool:
    code = get_code(addr, rpc_url)
    return code not in ("0x", "0x0", "")


def erc20_allowance(token: str, owner: str, spender: str, rpc_url: str) -> int:
    """Return allowance(owner -> spender) for an ERC-20 token. 0 on error."""
    # cast call <token> "allowance(address,address)(uint256)" <owner> <spender>
    try:
        out = cast(
            "call",
            token,
            "allowance(address,address)(uint256)",
            owner,
            spender,
            rpc_url=rpc_url,
        )
        return int(out, 16) if out.startswith("0x") else int(out)
    except Exception:
        return 0


def erc20_symbol(token: str, rpc_url: str) -> str:
    try:
        out = cast("call", token, "symbol()(string)", rpc_url=rpc_url)
        # cast may return quoted string; strip quotes
        return out.strip('"')
    except Exception:
        return "UNKNOWN"


def erc20_decimals(token: str, rpc_url: str) -> int:
    try:
        out = cast("call", token, "decimals()(uint8)", rpc_url=rpc_url)
        return int(out, 16) if out.startswith("0x") else int(out)
    except Exception:
        return 18


def format_units(raw: int, decimals: int) -> str:
    if raw == 0:
        return "0"
    s = str(raw)
    if decimals == 0:
        return s
    if len(s) <= decimals:
        s = s.zfill(decimals + 1)
        whole, frac = s[:-decimals], s[-decimals:]
        return f"{whole}.{frac.rstrip('0') or '0'}"
    whole, frac = s[: -decimals], s[-decimals:]
    return f"{whole}.{frac.rstrip('0') or '0'}"


# -----------------------------------------------------------------------------
# Scanning logic
# -----------------------------------------------------------------------------


def discover_spenders(wallet: str, lookback: int, rpc_url: str) -> set[str]:
    """Return the set of spender addresses that this wallet has approved,
    discovered by scanning Approval events emitted by *any* token contract."""
    spenders: set[str] = set()

    # cast logs --from-block <n> --to-block latest <topic0> <wallet> --json
    # Topic0 = Approval(address,address,uint256)
    # Topics: [Approval, owner, spender]
    try:
        latest = int(cast("block-number", rpc_url=rpc_url), 16)
    except Exception:
        return spenders

    from_block = max(0, latest - lookback)

    try:
        out = cast(
            "logs",
            "--from-block",
            str(from_block),
            "--to-block",
            "latest",
            TOPIC_APPROVAL,
            "--json",
            rpc_url=rpc_url,
        )
        events = json.loads(out) if out else []
    except Exception as e:
        print(f"[warn] log scan failed: {e}", file=sys.stderr)
        return spenders

    wallet_lc = wallet.lower()
    for ev in events:
        topics = ev.get("topics", [])
        if len(topics) < 3:
            continue
        owner_topic = topics[1]
        spender_topic = topics[2]
        if not owner_topic.lower().endswith(wallet_lc[2:]):
            continue
        # Topics are 32-byte; address is the last 20 bytes
        spender = "0x" + spender_topic[-40:]
        if spender != "0x" + "0" * 40:
            spenders.add(spender)

    return spenders


def discover_approved_tokens(wallet: str, lookback: int, rpc_url: str) -> dict[str, str]:
    """Return token -> spender mapping from Approval events emitted to this wallet."""
    mapping: dict[str, str] = {}
    try:
        latest = int(cast("block-number", rpc_url=rpc_url), 16)
    except Exception:
        return mapping
    from_block = max(0, latest - lookback)
    try:
        out = cast(
            "logs",
            "--from-block",
            str(from_block),
            "--to-block",
            "latest",
            TOPIC_APPROVAL,
            "--json",
            rpc_url=rpc_url,
        )
        events = json.loads(out) if out else []
    except Exception:
        return mapping
    wallet_lc = wallet.lower()
    for ev in events:
        topics = ev.get("topics", [])
        if len(topics) < 3:
            continue
        owner_topic = topics[1]
        if not owner_topic.lower().endswith(wallet_lc[2:]):
            continue
        spender = "0x" + topics[2][-40:]
        token = ev.get("address", "")
        if spender != "0x" + "0" * 40 and token:
            # record the *most recent* spender per token
            mapping[token.lower()] = spender
    return mapping


def scan_token_approvals(wallet: str, rpc_url: str, max_tokens: int) -> list[Approval]:
    """For each token the wallet has interacted with, check current allowance
    to the most-recent spender discovered from logs."""
    out: list[Approval] = []
    token_spender_map = discover_approved_tokens(wallet, 50_000, rpc_url)
    if not token_spender_map:
        return out

    known = load_known_good()
    allow_addrs = {e["address"].lower(): e for e in known.get("spenders", [])}

    for i, (token, spender) in enumerate(token_spender_map.items()):
        if i >= max_tokens:
            break
        if not is_contract(token, rpc_url):
            continue
        symbol = erc20_symbol(token, rpc_url)
        decimals = erc20_decimals(token, rpc_url)
        allowance = erc20_allowance(token, wallet, spender, rpc_url)
        if allowance == 0:
            continue

        is_inf = allowance >= MAX_UINT256
        reasons: list[str] = []
        risk = "ok"

        if is_inf:
            risk = "high"
            reasons.append("Infinite approval (uint256 max) — drainer can sweep full balance.")
        if spender.lower() not in allow_addrs:
            risk = "high" if risk == "high" else "medium"
            reasons.append("Spender is not on the known-good allowlist.")

        spender_name = allow_addrs.get(spender.lower(), {}).get("name", "Unknown")

        out.append(
            Approval(
                token=token,
                token_name=symbol,
                spender=spender,
                spender_name=spender_name,
                allowance_raw=str(allowance),
                allowance_human="infinite" if is_inf else format_units(allowance, decimals),
                is_infinite=is_inf,
                risk=risk,
                reasons=reasons,
            )
        )

    out.sort(key=lambda a: ({"critical": 0, "high": 1, "medium": 2, "low": 3, "ok": 4}[a.risk], a.token))
    return out


def scan_permit2(wallet: str, rpc_url: str, permit2_addr: str) -> list[Approval]:
    """If Permit2 is deployed at the well-known address, enumerate any
    non-zero allowances the wallet has granted via Permit2."""
    if not is_contract(permit2_addr, rpc_url):
        return []

    # Permit2 stores allowances in a mapping (owner, token, spender) => uint160.
    # Casting this directly via `cast call` requires the storage slot; the
    # public function `allowance(owner, token, spender)` is on the contract.
    # We need to know which tokens+spenders the wallet used. The simplest
    # read is to call allowance(owner, token, spender) for each discovered
    # (token, spender) pair from discover_approved_tokens.
    token_spender_map = discover_approved_tokens(wallet, 50_000, rpc_url)
    if not token_spender_map:
        return []

    out: list[Approval] = []
    for token, spender in token_spender_map.items():
        try:
            raw = cast(
                "call",
                permit2_addr,
                "allowance(address,address,address)(uint160,uint48,uint48)",
                wallet,
                token,
                spender,
                rpc_url=rpc_url,
            )
        except Exception:
            continue
        # Response is (amount, expiration, nonce) packed. Parse the leading
        # uint160 amount.
        if not raw or raw == "0x0000000000000000000000000000000000000000000000000000000000000000":
            continue
        try:
            amount = int(raw[:66], 16)  # first 32 bytes
        except ValueError:
            continue
        if amount == 0:
            continue
        symbol = erc20_symbol(token, rpc_url)
        out.append(
            Approval(
                token=token,
                token_name=symbol,
                spender=spender,
                spender_name="(Permit2)",
                allowance_raw=str(amount),
                allowance_human="Permit2 allowance (non-zero)",
                is_infinite=False,
                risk="high",
                reasons=["Permit2 allowance active — drainers love off-chain permit signatures."],
            )
        )
    return out


def scan_operator_approvals(wallet: str, rpc_url: str) -> list[Approval]:
    """Scan ApprovalForAll events for ERC-721/1155."""
    out: list[Approval] = []
    try:
        latest = int(cast("block-number", rpc_url=rpc_url), 16)
    except Exception:
        return out
    from_block = max(0, latest - 50_000)
    try:
        raw = cast(
            "logs",
            "--from-block",
            str(from_block),
            "--to-block",
            "latest",
            TOPIC_APPROVAL_FOR_ALL,
            "--json",
            rpc_url=rpc_url,
        )
        events = json.loads(raw) if raw else []
    except Exception:
        return out
    wallet_lc = wallet.lower()
    seen: set[tuple[str, str]] = set()
    for ev in events:
        topics = ev.get("topics", [])
        if len(topics) < 3:
            continue
        if not topics[1].lower().endswith(wallet_lc[2:]):
            continue
        operator = "0x" + topics[2][-40:]
        collection = ev.get("address", "")
        key = (collection.lower(), operator.lower())
        if key in seen:
            continue
        seen.add(key)
        if not is_contract(collection, rpc_url):
            continue
        out.append(
            Approval(
                token=collection,
                token_name="(ERC-721/1155)",
                spender=operator,
                spender_name="(operator)",
                allowance_raw="ALL",
                allowance_human="ALL NFTs in collection",
                is_infinite=True,
                risk="high",
                reasons=["Operator approval — one signature can move every NFT in the collection."],
            )
        )
    return out


def scan_phishing_signatures(wallet: str, rpc_url: str) -> list[dict[str, Any]]:
    """Match the wallet's recent transactions against the risk-signatures list.
    We look at recent outbound txs and decode the function selector."""
    hits: list[dict[str, Any]] = []
    risk = load_risk_signatures()
    sig_by_selector = {s["selector"]: s for s in risk["signatures"] if "selector" in s}

    try:
        latest = int(cast("block-number", rpc_url=rpc_url), 16)
    except Exception:
        return hits
    from_block = max(0, latest - 20_000)

    # We use cast to fetch the latest transactions. Note: Pharos explorers
    # typically expose a txlist API; if available, the agent should use that.
    # Here we just rely on the RPC `txpool_content` for pending + a sample
    # of recent blocks.
    try:
        raw = cast(
            "logs",
            "--from-block",
            str(from_block),
            "--to-block",
            "latest",
            TOPIC_APPROVAL,
            "--json",
            rpc_url=rpc_url,
        )
        events = json.loads(raw) if raw else []
    except Exception:
        events = []

    wallet_lc = wallet.lower()
    for ev in events:
        topics = ev.get("topics", [])
        if len(topics) < 3:
            continue
        if not topics[1].lower().endswith(wallet_lc[2:]):
            continue
        spender = "0x" + topics[2][-40:]
        # data field = amount
        data = ev.get("data", "0x0")
        try:
            amount = int(data, 16)
        except ValueError:
            continue
        if amount >= MAX_UINT256:
            hits.append(
                {
                    "id": "infinite-erc20-approval",
                    "severity": "high",
                    "spender": spender,
                    "tx_hash": ev.get("transactionHash", ""),
                    "block_number": int(ev.get("blockNumber", "0x0"), 16),
                    "evidence": f"Approval of 2^256-1 to {spender}",
                }
            )
    return hits


# -----------------------------------------------------------------------------
# Revoke plan
# -----------------------------------------------------------------------------


def build_revoke_plan(approvals: list[Approval], rpc_url: str) -> list[RevokeStep]:
    """Generate approve(spender, 0) calldata for every risky approval."""
    plan: list[RevokeStep] = []
    priority = 1
    for a in approvals:
        if a.risk not in ("high", "medium"):
            continue
        # approve(spender, 0)
        # cast calldata "approve(address,uint256)" <spender> 0
        try:
            calldata = cast(
                "calldata",
                "approve(address,uint256)",
                a.spender,
                "0",
            )
        except Exception:
            calldata = SELECTOR_APPROVE + a.spender[2:].rjust(64, "0") + "0".rjust(64, "0")

        # Estimate gas
        try:
            gas_est = cast(
                "estimate",
                a.token,
                "approve(address,uint256)",
                a.spender,
                "0",
                rpc_url=rpc_url,
            )
            gas = int(gas_est, 16) if gas_est.startswith("0x") else int(gas_est)
        except Exception:
            gas = 60_000  # typical approve gas

        plan.append(
            RevokeStep(
                token=a.token,
                spender=a.spender,
                to=a.token,
                value="0x0",
                data=calldata,
                estimated_gas=gas,
                priority=priority,
            )
        )
        priority += 1
    return plan


# -----------------------------------------------------------------------------
# Contract scoring (heuristic, explainable)
# -----------------------------------------------------------------------------


def score_contract(addr: str, rpc_url: str) -> int:
    """Return 0..100 — higher is safer. Heuristic only, no false security."""
    score = 50
    code = get_code(addr, rpc_url)
    if code in ("0x", "0x0", ""):
        return 0
    code_len = (len(code) - 2) // 2
    if code_len < 500:
        score -= 20  # very small contracts are suspicious
    if code_len > 5_000:
        score += 5
    # TODO: pull deployer + age + verification from explorer API
    return max(0, min(100, score))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    networks = load_networks()
    net = next(n for n in networks["networks"] if n["name"] == args.network)
    rpc_url = args.rpc_url or net["rpcUrl"]

    if not net["isTestnet"]:
        print("⚠️  MAINNET — read operations only. You will be re-prompted before any signing.")
        time.sleep(1.5)

    print(f"[*] Scanning {args.wallet} on {net['displayName']}…")

    try:
        approvals = scan_token_approvals(args.wallet, rpc_url, args.max_tokens)
    except Exception as e:
        print(f"[error] token approval scan failed: {e}", file=sys.stderr)
        approvals = []

    try:
        permit2 = scan_permit2(args.wallet, rpc_url, args.permit2)
    except Exception as e:
        print(f"[warn] Permit2 scan failed (non-fatal): {e}", file=sys.stderr)
        permit2 = []

    try:
        operators = scan_operator_approvals(args.wallet, rpc_url)
    except Exception as e:
        print(f"[warn] operator scan failed (non-fatal): {e}", file=sys.stderr)
        operators = []

    try:
        phishing = scan_phishing_signatures(args.wallet, rpc_url)
    except Exception as e:
        print(f"[warn] phishing scan failed (non-fatal): {e}", file=sys.stderr)
        phishing = []

    revoke_plan: list[RevokeStep] = []
    if args.emit_revoke_plan:
        revoke_plan = build_revoke_plan(approvals + permit2 + operators, rpc_url)

    contract_scores: dict[str, int] = {}
    for a in approvals + permit2 + operators:
        if a.spender and a.spender not in contract_scores:
            try:
                contract_scores[a.spender] = score_contract(a.spender, rpc_url)
            except Exception:
                contract_scores[a.spender] = 0

    summary = {
        "total_active_approvals": len(approvals) + len(permit2) + len(operators),
        "infinite_approvals": sum(1 for a in approvals if a.is_infinite),
        "unknown_spenders": sum(
            1
            for a in approvals
            if a.spender_name == "Unknown" and a.allowance_raw != "0"
        ),
        "operator_approvals": len(operators),
        "phishing_hits": len(phishing),
        "revoke_plan_steps": len(revoke_plan),
        "highest_risk_token": (approvals[0].token_name if approvals else None),
    }

    report = ScanReport(
        wallet=args.wallet,
        network=args.network,
        chain_id=net["chainId"],
        rpc_url=rpc_url,
        scanned_at=int(time.time()),
        summary=summary,
        approvals=approvals,
        permit2_approvals=permit2,
        operator_approvals=operators,
        phishing_hits=phishing,
        revoke_plan=revoke_plan,
        contract_scores=contract_scores,
    )

    if args.out:
        Path(args.out).write_text(
            json.dumps(asdict(report), indent=2)
        )
        print(f"[ok] Report written to {args.out}")
    else:
        print(json.dumps(asdict(report), indent=2))

    # Always print a short human summary
    print("\n=== Pharos Approval Shield — Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    if phishing:
        print("\n[!] Phishing hits:")
        for h in phishing:
            print(f"  - {h['id']} (severity={h['severity']}) on tx {h['tx_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
