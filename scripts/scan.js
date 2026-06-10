const { ethers } = require("ethers");
const fs = require("fs");
const path = require("path");

const PHAROS_RPC = "https://rpc.pharos.xyz";
const PHAROS_CHAIN_ID = 1672;
const PHAROS_EXPLORER = "https://pharosscan.xyz";
const PHAROS_CURRENCY = "PROS";

const MAX_UINT256 = BigInt("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");

// ERC-20 ABI for allowance and symbol checks
const ERC20_ABI = [
  "function symbol() view returns (string)",
  "function decimals() view returns (uint8)",
  "function allowance(address owner, address spender) view returns (uint256)",
];

// Known safe spenders
const KNOWN_SAFE_SPENDERS = [
  "uniswap",
  "aave",
  "compound",
  "curve",
  "pharos",
];

// Approval event topic
const APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925";

async function scanWallet(walletAddress) {
  if (!ethers.isAddress(walletAddress)) {
    console.log(JSON.stringify({
      success: false,
      error: "Invalid wallet address"
    }));
    return;
  }

  console.error(`[*] Scanning ${walletAddress} on Pharos Mainnet...`);

  const provider = new ethers.JsonRpcProvider(PHAROS_RPC, {
    chainId: PHAROS_CHAIN_ID,
    name: "pharos-mainnet",
  });

  const latestBlock = await provider.getBlockNumber();
  const fromBlock = Math.max(0, latestBlock - 50000);

  console.error(`[*] Scanning blocks ${fromBlock} to ${latestBlock} for approvals...`);

  // Fetch Approval events
  const approvalFilter = {
    topics: [APPROVAL_TOPIC],
    fromBlock: fromBlock,
    toBlock: latestBlock,
  };

  let logs = [];
  try {
    logs = await provider.getLogs(approvalFilter);
  } catch (e) {
    console.error(`[warn] Could not fetch logs: ${e.message}`);
  }

  // Filter logs where owner is our wallet
  const walletLower = walletAddress.toLowerCase();
  const relevantLogs = logs.filter(log => {
    if (log.topics.length < 3) return false;
    const owner = "0x" + log.topics[1].slice(26);
    return owner.toLowerCase() === walletLower;
  });

  console.error(`[*] Found ${relevantLogs.length} approval events`);

  // Get unique token+spender pairs
  const pairs = new Map();
  for (const log of relevantLogs) {
    const token = log.address.toLowerCase();
    const spender = "0x" + log.topics[2].slice(26);
    pairs.set(`${token}:${spender}`, { token, spender });
  }

  // Check current allowances
  const approvals = [];
  for (const { token, spender } of pairs.values()) {
    try {
      const contract = new ethers.Contract(token, ERC20_ABI, provider);
      const [symbol, decimals, allowance] = await Promise.all([
        contract.symbol().catch(() => "UNKNOWN"),
        contract.decimals().catch(() => 18),
        contract.allowance(walletAddress, spender),
      ]);

      if (allowance === 0n) continue;

      const isInfinite = allowance >= MAX_UINT256 / 2n;
      const allowanceHuman = isInfinite
        ? "infinite"
        : parseFloat(ethers.formatUnits(allowance, decimals)).toFixed(6);

      // Risk assessment
      let risk = "low";
      const reasons = [];

      if (isInfinite) {
        risk = "critical";
        reasons.push("Infinite approval — spender can drain entire token balance");
      }

      const spenderLower = spender.toLowerCase();
      const isKnownSafe = KNOWN_SAFE_SPENDERS.some(name =>
        spenderLower.includes(name)
      );

      if (!isKnownSafe && risk !== "critical") {
        risk = "high";
        reasons.push("Spender is not on the known-safe list");
      }

      if (reasons.length === 0) {
        reasons.push("Limited approval to known protocol");
      }

      approvals.push({
        token: token,
        tokenSymbol: symbol,
        spender: spender,
        allowanceRaw: allowance.toString(),
        allowanceHuman: allowanceHuman,
        isInfinite: isInfinite,
        risk: risk,
        reasons: reasons,
        explorerUrl: PHAROS_EXPLORER + "/token/" + token,
      });

    } catch (e) {
      console.error(`[warn] Could not check token ${token}: ${e.message}`);
    }
  }

  // Sort by risk
  const riskOrder = { critical: 0, high: 1, medium: 2, low: 3, ok: 4 };
  approvals.sort((a, b) => (riskOrder[a.risk] || 4) - (riskOrder[b.risk] || 4));

  // Build revoke plan
  const revokePlan = approvals
    .filter(a => a.risk === "critical" || a.risk === "high")
    .map((a, i) => ({
      priority: i + 1,
      token: a.token,
      tokenSymbol: a.tokenSymbol,
      spender: a.spender,
      action: "Call approve(spender, 0) on the token contract",
      estimatedGas: 60000,
      revokeCommand: `cast send ${a.token} "approve(address,uint256)" ${a.spender} 0 --rpc-url ${PHAROS_RPC}`,
    }));

  // Summary
  const summary = {
    totalActiveApprovals: approvals.length,
    infiniteApprovals: approvals.filter(a => a.isInfinite).length,
    criticalRisk: approvals.filter(a => a.risk === "critical").length,
    highRisk: approvals.filter(a => a.risk === "high").length,
    revokePlanSteps: revokePlan.length,
    highestRiskToken: approvals.length > 0 ? approvals[0].tokenSymbol : null,
  };

  const result = {
    success: true,
    skill: "pharos-approval-shield",
    action: "scan-wallet",
    data: {
      wallet: walletAddress,
      network: "Pharos Pacific Ocean Mainnet",
      chainId: PHAROS_CHAIN_ID,
      scannedAt: new Date().toISOString(),
      blocksScanned: { from: fromBlock, to: latestBlock },
      summary: summary,
      approvals: approvals,
      revokePlan: revokePlan,
      explorerUrl: PHAROS_EXPLORER + "/address/" + walletAddress,
    },
    timestamp: new Date().toISOString(),
  };

  console.log(JSON.stringify(result, null, 2));
}

const wallet = process.argv[2];
if (!wallet) {
  console.log(JSON.stringify({
    success: false,
    error: "Missing argument. Usage: node scripts/scan.js <wallet_address>"
  }));
} else {
  scanWallet(wallet).catch(console.error);
}