/**
 * Encrypted keystore storage in this browser.
 *
 * Only the Web3 v3 JSON is stored — never the password and never the plaintext
 * secret. A saved keystore still needs its password to sign. The file can also be
 * downloaded and kept on the user's device; this store is a convenience, not the
 * source of truth.
 */
import { keystoreAddress } from "./keystore";

const KEY = "rbridge.keystores";

export interface SavedKeystore {
  address: string;
  json: string;
  savedAt: number;
}

function isSaved(value: unknown): value is SavedKeystore {
  const item = value as Partial<SavedKeystore> | null;
  return (
    typeof item?.address === "string" &&
    /^0x[0-9a-f]{40}$/.test(item.address) &&
    typeof item.json === "string" &&
    typeof item.savedAt === "number"
  );
}

export function loadSavedKeystores(): SavedKeystore[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isSaved) : [];
  } catch {
    return [];
  }
}

/** Save (or replace) the encrypted JSON, keyed by its Ethereum address. */
export function saveKeystore(json: string): SavedKeystore {
  const address = keystoreAddress(json);
  const saved: SavedKeystore = { address, json, savedAt: Date.now() };
  const next = loadSavedKeystores().filter((item) => item.address !== address);
  next.push(saved);
  localStorage.setItem(KEY, JSON.stringify(next));
  return saved;
}

export function findSavedKeystore(address: string): SavedKeystore | undefined {
  return loadSavedKeystores().find(
    (item) => item.address.toLowerCase() === address.toLowerCase(),
  );
}

export function forgetKeystore(address: string): void {
  const next = loadSavedKeystores().filter(
    (item) => item.address.toLowerCase() !== address.toLowerCase(),
  );
  localStorage.setItem(KEY, JSON.stringify(next));
}

/** Trigger a download of the encrypted JSON; the plaintext is not involved. */
export function downloadKeystore(json: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
