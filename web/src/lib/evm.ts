/**
 * Anvil/Ethereum vault client.
 *
 * MetaMask owns the account and signs `approve` + `lock`. Reads use the configured RPC
 * so the portfolio works before a wallet is connected. Native ETH uses the same `lock`
 * arm with `token == address(0)`; ERC-20s are approved to the vault first.
 */
import {
  createPublicClient,
  createWalletClient,
  custom,
  formatEther,
  formatUnits,
  http,
  parseEther,
  parseUnits,
  zeroAddress,
  type Address,
  type EIP1193Provider,
  type Hash,
} from "viem";

export function anvilChain(rpc: string) {
  return {
    id: 31337,
    name: "Anvil",
    nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
    rpcUrls: { default: { http: [rpc] } },
  } as const;
}

export const VAULT_ABI = [
  {
    type: "function",
    name: "locked",
    stateMutability: "view",
    inputs: [{ name: "", type: "address" }],
    outputs: [{ type: "uint256" }],
  },
  {
    type: "function",
    name: "fees",
    stateMutability: "view",
    inputs: [{ name: "", type: "address" }],
    outputs: [{ type: "uint256" }],
  },
  {
    type: "function",
    name: "paused",
    stateMutability: "view",
    inputs: [],
    outputs: [{ type: "bool" }],
  },
  {
    type: "function",
    name: "assets",
    stateMutability: "view",
    inputs: [{ name: "", type: "address" }],
    outputs: [
      { name: "enabled", type: "bool" },
      { name: "maxDeposit", type: "uint256" },
      { name: "maxLocked", type: "uint256" },
      { name: "scale", type: "uint256" },
      { name: "withdrawFeeBps", type: "uint256" },
      { name: "assetKey", type: "string" },
    ],
  },
  {
    type: "function",
    name: "lock",
    stateMutability: "payable",
    inputs: [
      { name: "token", type: "address" },
      { name: "amount", type: "uint256" },
      { name: "rholoRecipient", type: "string" },
      { name: "nonce", type: "uint256" },
    ],
    outputs: [],
  },
] as const;

export const ERC20_ABI = [
  {
    type: "function",
    name: "symbol",
    stateMutability: "view",
    inputs: [],
    outputs: [{ type: "string" }],
  },
  {
    type: "function",
    name: "decimals",
    stateMutability: "view",
    inputs: [],
    outputs: [{ type: "uint8" }],
  },
  {
    type: "function",
    name: "balanceOf",
    stateMutability: "view",
    inputs: [{ name: "owner", type: "address" }],
    outputs: [{ type: "uint256" }],
  },
  {
    type: "function",
    name: "allowance",
    stateMutability: "view",
    inputs: [
      { name: "owner", type: "address" },
      { name: "spender", type: "address" },
    ],
    outputs: [{ type: "uint256" }],
  },
  {
    type: "function",
    name: "approve",
    stateMutability: "nonpayable",
    inputs: [
      { name: "spender", type: "address" },
      { name: "value", type: "uint256" },
    ],
    outputs: [{ type: "bool" }],
  },
] as const;

export interface VaultAsset {
  enabled: boolean;
  maxDeposit: bigint;
  maxLocked: bigint;
  scale: bigint;
  withdrawFeeBps: bigint;
  assetKey: string;
}

export interface VaultStatus extends Omit<VaultAsset, "maxLocked"> {
  locked: bigint;
  fees: bigint;
  paused: boolean;
  decimals: number;
}

export async function readAsset(
  vault: Address,
  token: Address,
  rpc: string,
): Promise<VaultAsset> {
  const client = createPublicClient({ chain: anvilChain(rpc), transport: http(rpc) });
  const asset = await client.readContract({
    address: vault,
    abi: VAULT_ABI,
    functionName: "assets",
    args: [token],
  });
  return {
    enabled: asset[0],
    maxDeposit: asset[1],
    maxLocked: asset[2],
    scale: asset[3],
    withdrawFeeBps: asset[4],
    assetKey: asset[5],
  };
}

export async function readTokenDecimals(token: Address, rpc: string): Promise<number> {
  if (token === zeroAddress) return 18;
  const client = createPublicClient({ chain: anvilChain(rpc), transport: http(rpc) });
  return client.readContract({ address: token, abi: ERC20_ABI, functionName: "decimals" });
}

export async function readTokenBalance(
  token: Address,
  rpc: string,
  account: Address,
): Promise<bigint> {
  const client = createPublicClient({ chain: anvilChain(rpc), transport: http(rpc) });
  return client.readContract({
    address: token,
    abi: ERC20_ABI,
    functionName: "balanceOf",
    args: [account],
  });
}

export async function readTokenAllowance(
  token: Address,
  rpc: string,
  owner: Address,
  spender: Address,
): Promise<bigint> {
  const client = createPublicClient({ chain: anvilChain(rpc), transport: http(rpc) });
  return client.readContract({
    address: token,
    abi: ERC20_ABI,
    functionName: "allowance",
    args: [owner, spender],
  });
}

export async function readVaultStatus(
  vault: Address,
  rpc: string,
  token: Address = zeroAddress,
): Promise<VaultStatus> {
  const client = createPublicClient({ chain: anvilChain(rpc), transport: http(rpc) });
  const [locked, fees, paused, asset, decimals] = await Promise.all([
    client.readContract({ address: vault, abi: VAULT_ABI, functionName: "locked", args: [token] }),
    client.readContract({ address: vault, abi: VAULT_ABI, functionName: "fees", args: [token] }),
    client.readContract({ address: vault, abi: VAULT_ABI, functionName: "paused" }),
    client.readContract({ address: vault, abi: VAULT_ABI, functionName: "assets", args: [token] }),
    readTokenDecimals(token, rpc),
  ]);
  return {
    locked,
    fees,
    paused,
    assetKey: asset[5],
    maxDeposit: asset[1],
    scale: asset[3],
    enabled: asset[0],
    withdrawFeeBps: asset[4],
    decimals,
  };
}

export async function readEthBalance(rpc: string, account: Address): Promise<bigint> {
  const client = createPublicClient({ chain: anvilChain(rpc), transport: http(rpc) });
  return client.getBalance({ address: account });
}

/** An ERC-20 needs an allowance refresh before `lock` can pull the tokens. */
export function needsApproval(allowance: bigint, amount: bigint): boolean {
  return allowance < amount;
}

/**
 * Client-side mirror of the vault's `lock` checks, so the user sees a reason before
 * MetaMask asks them to pay for a revert.
 */
export function lockAmountError(
  amount: bigint,
  asset: Pick<VaultAsset, "enabled" | "maxDeposit" | "scale">,
): string | null {
  if (!asset.enabled) return "This asset is not enabled in the vault.";
  if (asset.maxDeposit > 0n && amount > asset.maxDeposit) {
    return `Amount exceeds the per-deposit cap of ${asset.maxDeposit} base units.`;
  }
  if (asset.scale > 1n && amount % asset.scale !== 0n) {
    return `Amount must be a multiple of ${asset.scale} base units (native → rholo scaling).`;
  }
  return null;
}

export async function ensureAnvilNetwork(rpc: string): Promise<void> {
  if (!window.ethereum) {
    throw new Error("MetaMask is not installed in this browser.");
  }
  const chainId = "0x7a69";
  try {
    await window.ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId }],
    });
  } catch {
    await window.ethereum.request({
      method: "wallet_addEthereumChain",
      params: [
        {
          chainId,
          chainName: "Anvil",
          nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
          rpcUrls: [rpc],
        },
      ],
    });
  }
}

export async function lockEth(options: {
  vault: Address;
  amountEth: string;
  rholoRecipient: string;
  nonce: number;
  account: Address;
  rpc: string;
}): Promise<Hash> {
  if (!window.ethereum) {
    throw new Error("MetaMask is not installed in this browser.");
  }
  await ensureAnvilNetwork(options.rpc);
  const value = parseEther(options.amountEth);
  const asset = await readAsset(options.vault, zeroAddress, options.rpc);
  const problem = lockAmountError(value, asset);
  if (problem) throw new Error(problem);
  const wallet = createWalletClient({
    chain: anvilChain(options.rpc),
    transport: custom(window.ethereum as EIP1193Provider),
  });
  return wallet.writeContract({
    address: options.vault,
    abi: VAULT_ABI,
    functionName: "lock",
    args: [zeroAddress, value, options.rholoRecipient, BigInt(options.nonce)],
    value,
    account: options.account,
  });
}

export interface Erc20LockResult {
  approve?: Hash;
  lock: Hash;
}

/**
 * Approve the vault for `amount` (when the current allowance is short), wait for the
 * approval to be mined, then call `lock`. Returns both transactions so the UI can show
 * the two MetaMask confirmations separately.
 */
export async function lockErc20(options: {
  vault: Address;
  token: Address;
  amount: string;
  rholoRecipient: string;
  nonce: number;
  account: Address;
  rpc: string;
}): Promise<Erc20LockResult> {
  if (!window.ethereum) {
    throw new Error("MetaMask is not installed in this browser.");
  }
  if (options.token === zeroAddress) {
    throw new Error("Use lockEth for native ETH.");
  }
  await ensureAnvilNetwork(options.rpc);
  const publicClient = createPublicClient({
    chain: anvilChain(options.rpc),
    transport: http(options.rpc),
  });
  const wallet = createWalletClient({
    chain: anvilChain(options.rpc),
    transport: custom(window.ethereum as EIP1193Provider),
  });

  const [decimals, asset] = await Promise.all([
    publicClient.readContract({
      address: options.token,
      abi: ERC20_ABI,
      functionName: "decimals",
    }),
    readAsset(options.vault, options.token, options.rpc),
  ]);
  const value = parseUnits(options.amount, decimals);
  const problem = lockAmountError(value, asset);
  if (problem) throw new Error(problem);

  const allowance = await publicClient.readContract({
    address: options.token,
    abi: ERC20_ABI,
    functionName: "allowance",
    args: [options.account, options.vault],
  });
  let approve: Hash | undefined;
  if (needsApproval(allowance, value)) {
    approve = await wallet.writeContract({
      address: options.token,
      abi: ERC20_ABI,
      functionName: "approve",
      args: [options.vault, value],
      account: options.account,
    });
    await publicClient.waitForTransactionReceipt({ hash: approve });
  }

  const lock = await wallet.writeContract({
    address: options.vault,
    abi: VAULT_ABI,
    functionName: "lock",
    args: [options.token, value, options.rholoRecipient, BigInt(options.nonce)],
    account: options.account,
  });
  return { approve, lock };
}

export function formatEth(value: bigint): string {
  return formatEther(value);
}

export function formatNative(value: bigint, decimals: number): string {
  return formatUnits(value, decimals);
}
