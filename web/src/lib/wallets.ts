/**
 * Connectors for the wallets that already own the native accounts.
 *
 * r-bridge does not create or store native-chain keys. MetaMask handles Ethereum,
 * TronLink handles Tron and Keplr handles Cosmos/Agoric. The only account this app
 * stores is the rholo account, which lives in the WASM keystore (next phase).
 */

interface Eip1193Provider {
  request(args: { method: string; params?: unknown[] }): Promise<unknown>;
  isMetaMask?: boolean;
}

interface TronLinkProvider {
  request(args: { method: string }): Promise<{ code?: number; message?: string }>;
}

interface TronWebLike {
  defaultAddress?: { base58?: string };
}

interface KeplrLike {
  enable(chainId: string): Promise<void>;
  getKey(chainId: string): Promise<{ bech32Address: string }>;
}

declare global {
  interface Window {
    ethereum?: Eip1193Provider;
    tronLink?: TronLinkProvider;
    tronWeb?: TronWebLike;
    keplr?: KeplrLike;
  }
}

export const AGORIC_CHAIN_ID =
  import.meta.env.VITE_AGORIC_CHAIN_ID ?? "agoriclocal";

export function hasMetaMask(): boolean {
  return Boolean(window.ethereum?.isMetaMask ?? window.ethereum);
}

export function hasTronLink(): boolean {
  return Boolean(window.tronLink);
}

export function hasKeplr(): boolean {
  return Boolean(window.keplr);
}

export async function connectMetaMask(): Promise<string> {
  if (!window.ethereum) {
    throw new Error("MetaMask is not installed in this browser.");
  }
  const accounts = (await window.ethereum.request({
    method: "eth_requestAccounts",
  })) as string[];
  const address = accounts[0];
  if (!address) {
    throw new Error("MetaMask returned no account.");
  }
  return address;
}

export async function connectTronLink(): Promise<string> {
  if (!window.tronLink) {
    throw new Error("TronLink is not installed in this browser.");
  }
  const result = await window.tronLink.request({ method: "tron_requestAccounts" });
  if (result?.code === 4001) {
    throw new Error(result.message ?? "TronLink refused the request.");
  }
  const address = window.tronWeb?.defaultAddress?.base58;
  if (!address) {
    throw new Error("TronLink is connected but reported no address.");
  }
  return address;
}

export async function connectKeplr(): Promise<string> {
  if (!window.keplr) {
    throw new Error("Keplr is not installed in this browser.");
  }
  await window.keplr.enable(AGORIC_CHAIN_ID);
  const key = await window.keplr.getKey(AGORIC_CHAIN_ID);
  if (!key.bech32Address) {
    throw new Error("Keplr returned no Agoric address.");
  }
  return key.bech32Address;
}

export const WALLET_FOR_CHAIN = {
  ethereum: { name: "MetaMask", connect: connectMetaMask, installed: hasMetaMask },
  tron: { name: "TronLink", connect: connectTronLink, installed: hasTronLink },
  agoric: { name: "Keplr", connect: connectKeplr, installed: hasKeplr },
} as const;
