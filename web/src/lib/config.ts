/**
 * Local devnet wiring for the web demo. Everything here is a user setting; the app
 * never bakes in keys or a deployed address.
 */
export interface AppConfig {
  node: string;
  bridgeUri: string;
  vault: string;
  rholoAddress: string;
  anvilRpc: string;
}

const KEY = "rbridge.config";

export const DEFAULT_CONFIG: AppConfig = {
  node: import.meta.env.VITE_RBRIDGE_NODE ?? "http://localhost:40403",
  bridgeUri: import.meta.env.VITE_RBRIDGE_URI ?? "",
  vault: import.meta.env.VITE_RBRIDGE_VAULT ?? "",
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
