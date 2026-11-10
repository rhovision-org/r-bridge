/**
 * TronLink/TronWeb client for the TVM vault.
 *
 * TronLink owns the Tron account and signs; this module only builds the approve + lock
 * calls and reads balances. Tron addresses are base58 for display and `41`-prefixed hex
 * for the 20-byte payload the vault uses; the same 20 bytes are the account's Ethereum
 * address, which is how a TronLink key maps to a rholo address.
 */
import { parseUnits } from "viem";

/** The all-zero account in Tron base58; the vault uses it for native TRX. */
export const TRON_ZERO_ADDRESS = "T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb";
const TRON_BASE58 = /^T[1-9A-HJ-NP-Za-km-z]{33}$/;

export interface TronContractCall {
  call(): Promise<unknown>;
}

export interface TronContractSend {
  send(options?: Record<string, unknown>): Promise<unknown>;
}

export interface TronContract {
  allowance(owner: string, spender: string): TronContractCall;
  approve(spender: string, amount: string): TronContractSend;
  balanceOf(owner: string): TronContractCall;
  lock(
    token: string,
    amount: string,
    rholoRecipient: string,
    nonce: string,
  ): TronContractSend;
}

export interface TronTransactionInfo {
  id?: string;
  receipt?: { result?: string };
}

export interface TronWebLike {
  defaultAddress?: { base58?: string; hex?: string };
  address: {
    toHex(address: string): string;
    fromHex?(address: string): string;
  };
  contract(): { at(address: string): Promise<TronContract> };
  trx: {
    getBalance(address: string): Promise<number | string | bigint>;
    getTransactionInfo(txid: string): Promise<TronTransactionInfo | null>;
  };
}

export function getTronWeb(): TronWebLike | null {
  return typeof window === "undefined" ? null : window.tronWeb ?? null;
}

export function isTronAddress(value: string): boolean {
  return TRON_BASE58.test(value);
}

export function parseTronAmount(amount: string, decimals = 6): string {
  const fraction = amount.trim().split(".")[1] ?? "";
  if (fraction.length > decimals) {
    throw new Error(`Amount has more than ${decimals} decimal places.`);
  }
  const value = parseUnits(amount, decimals);
  if (value <= 0n) throw new Error("Amount must be greater than zero.");
  return value.toString();
}

/** `41a614…` (or `0x41a614…`) -> `0xa614…`, the 20-byte payload. */
export function tronHexToEth(hex: string): string {
  const normalized = hex.toLowerCase().replace(/^0x/, "");
  if (!/^41[0-9a-f]{40}$/.test(normalized)) {
    throw new Error(`Not a Tron address in hex: ${hex}`);
  }
  return `0x${normalized.slice(2)}`;
}

export function tronBase58ToEth(tronWeb: TronWebLike, base58: string): string {
  if (!isTronAddress(base58)) {
    throw new Error(`Not a Tron base58 address: ${base58}`);
  }
  return tronHexToEth(tronWeb.address.toHex(base58));
}

/** TronWeb resolves `.send()` to a txid string in 5.x and an object in some builds. */
function txidOf(result: unknown): string {
  if (typeof result === "string" && result) return result;
  const value = result as
    | { txid?: unknown; transaction?: { txID?: unknown } }
    | null
    | undefined;
  if (value && typeof value.txid === "string") return value.txid;
  if (value?.transaction && typeof value.transaction.txID === "string") {
    return value.transaction.txID;
  }
  throw new Error("TronLink returned no transaction id");
}

function bigintOf(value: unknown): bigint {
  const text = String(value);
  try {
    return BigInt(text);
  } catch {
    throw new Error(`Unexpected Tron number: ${text}`);
  }
}

async function waitForTron(
  tronWeb: TronWebLike,
  txid: string,
  timeoutMs = 90_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const info = await tronWeb.trx.getTransactionInfo(txid);
    if (info && (info.id === undefined || info.id === txid)) {
      const result = info.receipt?.result;
      if (result && result !== "SUCCESS") {
        throw new Error(`Tron transaction ${txid} failed: ${result}`);
      }
      if (result === "SUCCESS") return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_500));
  }
  throw new Error(`Tron transaction ${txid} was not confirmed in time.`);
}

export interface TronLockResult {
  approve?: string;
  lock: string;
}

/** Approve the vault for the amount (when short), then lock a TRC-20. */
export async function lockTrc20(options: {
  tronWeb: TronWebLike;
  vault: string;
  token: string;
  amount: string;
  rholoRecipient: string;
  nonce: number;
  owner: string;
  decimals?: number;
}): Promise<TronLockResult> {
  const value = parseTronAmount(options.amount, options.decimals ?? 6);
  const token = await options.tronWeb.contract().at(options.token);
  const allowance = bigintOf(
    await token.allowance(options.owner, options.vault).call(),
  );
  let approve: string | undefined;
  if (allowance < BigInt(value)) {
    approve = txidOf(
      await token.approve(options.vault, value).send(),
    );
    await waitForTron(options.tronWeb, approve);
  }
  const vault = await options.tronWeb.contract().at(options.vault);
  const lock = txidOf(
    await vault
      .lock(options.token, value, options.rholoRecipient, String(options.nonce))
      .send(),
  );
  await waitForTron(options.tronWeb, lock);
  return { approve, lock };
}

/** Lock native TRX: the vault's `lock` is payable and takes the zero address token. */
export async function lockTrx(options: {
  tronWeb: TronWebLike;
  vault: string;
  amount: string;
  rholoRecipient: string;
  nonce: number;
  owner: string;
}): Promise<string> {
  const value = parseTronAmount(options.amount, 6);
  const vault = await options.tronWeb.contract().at(options.vault);
  const lock = txidOf(
    await vault
      .lock(TRON_ZERO_ADDRESS, value, options.rholoRecipient, String(options.nonce))
      .send({ callValue: value }),
  );
  await waitForTron(options.tronWeb, lock);
  return lock;
}

export async function readTrxBalance(
  tronWeb: TronWebLike,
  account: string,
): Promise<bigint> {
  return bigintOf(await tronWeb.trx.getBalance(account));
}

export async function readTrc20Balance(
  tronWeb: TronWebLike,
  token: string,
  account: string,
): Promise<bigint> {
  const contract = await tronWeb.contract().at(token);
  return bigintOf(await contract.balanceOf(account).call());
}
