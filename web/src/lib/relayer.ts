/**
 * Browser client for the rail-agnostic relayer read API.
 *
 * Mirrors the Rust `RelayerClient`: health, chains and a deposit's state. A 404 is a
 * normal "not found yet" result; any other failure is an error the UI can show. The
 * relayer URL is user configuration, so this never assumes a deployment.
 */

export interface RelayerHealth {
  version: string;
  chains: string[];
  threshold: number;
  signers?: number;
  paused?: boolean;
  halted?: unknown;
  last_block?: number | null;
}

export interface RelayerChain {
  chain: string;
  head?: number | null;
  confirmations?: number | null;
  finalized?: boolean | null;
  enabled?: boolean;
}

export interface RelayerDeposit {
  deposit_id?: string;
  state: string;
  message?: string | null;
  signatures?: string[];
  error?: string | null;
}

export function relayerUrlConfigured(url: string): boolean {
  return /^https?:\/\/\S+$/.test(url.trim());
}

function baseUrl(url: string): string {
  const trimmed = url.trim().replace(/\/+$/, "");
  if (!relayerUrlConfigured(trimmed)) {
    throw new Error("The relayer URL must start with http:// or https://.");
  }
  return trimmed;
}

async function getJson<T>(url: string, path: string, timeoutMs = 4_000): Promise<T | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl(url)}${path}`, {
      signal: controller.signal,
      headers: { accept: "application/json" },
    });
    if (response.status === 404) return null;
    if (!response.ok) {
      throw new Error(`relayer ${path}: HTTP ${response.status}`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`relayer ${path}: timed out`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export async function readRelayerHealth(url: string): Promise<RelayerHealth> {
  const health = await getJson<RelayerHealth>(url, "/health");
  if (!health) throw new Error("relayer /health returned 404");
  return health;
}

type RawChains =
  | Array<RelayerChain | string>
  | { chains?: Array<RelayerChain | string> };

/** Accept both the mock's bare names and the dev watcher's per-chain objects. */
export async function readRelayerChains(url: string): Promise<RelayerChain[]> {
  const value = await getJson<RawChains>(url, "/v1/chains");
  if (!value) throw new Error("relayer /v1/chains returned 404");
  const items = Array.isArray(value) ? value : value.chains ?? [];
  return items.map((item) =>
    typeof item === "string" ? { chain: item, enabled: true } : item,
  );
}

export async function readRelayerDeposit(
  url: string,
  depositId: string,
): Promise<RelayerDeposit | null> {
  return getJson<RelayerDeposit>(
    url,
    `/v1/deposits/${encodeURIComponent(depositId)}`,
  );
}
