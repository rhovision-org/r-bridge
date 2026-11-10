/**
 * Anvil/Ethereum vault client.
 *
 * MetaMask owns the account and signs `lock`. Reads use the configured RPC so the
 * portfolio works before a wallet is connected.
 */
import {
  createPublicClient,
  createWalletClient,
  custom,
  formatEther,
  http,
  parseEther,
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

export interface VaultStatus {
  locked: bigint;
  fees: bigint;
  paused: boolean;
  assetKey: string;
  maxDeposit: bigint;
  scale: bigint;
}

export async function readVaultStatus(vault: Address, rpc: string): Promise<VaultStatus> {
  const client = createPublicClient({ chain: anvilChain(rpc), transport: http(rpc) });
  const [locked, fees, paused, asset] = await Promise.all([
    client.readContract({ address: vault, abi: VAULT_ABI, functionName: "locked", args: [zeroAddress] }),
    client.readContract({ address: vault, abi: VAULT_ABI, functionName: "fees", args: [zeroAddress] }),
    client.readContract({ address: vault, abi: VAULT_ABI, functionName: "paused" }),
    client.readContract({ address: vault, abi: VAULT_ABI, functionName: "assets", args: [zeroAddress] }),
  ]);
  return {
    locked,
    fees,
    paused,
    assetKey: asset[5],
    maxDeposit: asset[1],
    scale: asset[3],
  };
}

export async function readEthBalance(rpc: string, account: Address): Promise<bigint> {
  const client = createPublicClient({ chain: anvilChain(rpc), transport: http(rpc) });
  return client.getBalance({ address: account });
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
  const wallet = createWalletClient({
    chain: anvilChain(options.rpc),
    transport: custom(window.ethereum as EIP1193Provider),
  });
  const value = parseEther(options.amountEth);
  return wallet.writeContract({
    address: options.vault,
    abi: VAULT_ABI,
    functionName: "lock",
    args: [zeroAddress, value, options.rholoRecipient, BigInt(options.nonce)],
    value,
    account: options.account,
  });
}

export function formatEth(value: bigint): string {
  return formatEther(value);
}
