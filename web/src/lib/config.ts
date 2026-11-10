/**
 * Local devnet wiring for the web demo. Everything here is a user setting; the app
 * never bakes in keys or a deployed address.
 */
export interface AppConfig {
  node: string;
  bridgeUri: string;
  vault: string;
  /** Devnet mock-USDT address from `.devnet/evm.json`; enables the ERC-20 lock. */
  usdtToken: string;
  /** TVM vault address (base58) and its TRC-20 USDT; enables the TronLink lock. */
  tronVault: string;
  tronUsdt: string;
  /** Relayer read API (mock on :8099 or the dev watcher's metrics port). */
  relayerUrl: string;
  rholoAddress: string;
  anvilRpc: string;
}

const KEY = "rbridge.config";

export const DEFAULT_CONFIG: AppConfig = {
  node: import.meta.env.VITE_RBRIDGE_NODE ?? "http://localhost:40403",
  bridgeUri: import.meta.env.VITE_RBRIDGE_URI ?? "",
  vault: import.meta.env.VITE_RBRIDGE_VAULT ?? "",
  usdtToken: import.meta.env.VITE_RBRIDGE_USDT ?? "",
  tronVault: import.meta.env.VITE_RBRIDGE_TRON_VAULT ?? "",
  tronUsdt: import.meta.env.VITE_RBRIDGE_TRON_USDT ?? "",
  relayerUrl: import.meta.env.VITE_RBRIDGE_RELAYER ?? "",
  rholoAddress: import.meta.env.VITE_RHOLO_ADDRESS ?? "",
  anvilRpc: import.meta.env.VITE_ANVIL_RPC ?? "http://127.0.0.1:8545",
};

export function loadConfig(): AppConfig {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULT_CONFIG, ...(JSON.parse(raw) as Partial<AppConfig>) } : DEFAULT_CONFIG;
  } catch {
    return DEFAULT_CONFIG;
  }
}

export function saveConfig(config: AppConfig): void {
  localStorage.setItem(KEY, JSON.stringify(config));
}
