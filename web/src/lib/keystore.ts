/**
 * rholo keystore helpers. The Web3 v3 encryption is the Rust `rbridge-keystore` crate
 * compiled to WASM; the same files open in r-wallet, and the decrypted secret never
 * leaves this module except as a return value the caller holds in memory.
 */

export interface KeystoreAccount {
  secretHex: string;
  revAddress: string;
}

export interface CreatedKeystore extends KeystoreAccount {
  json: string;
  ethAddress: string;
  filename: string;
}

/** The Ethereum address recorded in a v3 file, as a `0x` string. */
export function keystoreAddress(json: string): string {
  let value: unknown;
  try {
    value = JSON.parse(json);
  } catch {
    throw new Error("Not a keystore: the file is not JSON.");
  }
  const address = (value as { address?: unknown } | null)?.address;
  if (typeof address !== "string" || !/^[0-9a-fA-F]{40}$/.test(address)) {
    throw new Error("Not a Web3 v3 keystore: missing address.");
  }
  return `0x${address.toLowerCase()}`;
}

/**
 * Derive the rholo (REV) address from an Ethereum address. The mapping is public, so a
 * MetaMask account can be shown as a rholo recipient without exporting its key.
 */
export async function revAddressFromEth(ethAddress: string): Promise<string> {
  const { initWasm, rev_address_from_eth } = await import("../wasm");
  await initWasm();
  return rev_address_from_eth(ethAddress);
}

/** Decrypt a v3 keystore and derive the rholo account. Throws on a wrong password. */
export async function unlockKeystore(
  json: string,
  password: string,
): Promise<KeystoreAccount> {
  keystoreAddress(json);
  if (!password) {
    throw new Error("Enter the keystore password.");
  }
  const { initWasm, keystore_unlock, RholoKey } = await import("../wasm");
  await initWasm();
  const secretHex = keystore_unlock(json, password);
  return { secretHex, revAddress: new RholoKey(secretHex).rev_address() };
}

export function randomSecretHex(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Normalize a pasted private key: optional `0x`, any case, exactly 32 bytes. */
export function normalizeSecret(secretHex: string): string {
  const trimmed = secretHex.trim().toLowerCase();
  const hex = trimmed.startsWith("0x") ? trimmed.slice(2) : trimmed;
  if (!/^[0-9a-f]{64}$/.test(hex)) {
    throw new Error("Enter a 32-byte hex private key (64 hex characters).");
  }
  return hex;
}

export function keystoreFilename(address: string, at = new Date()): string {
  const stamp = at.toISOString().replace(/[:.]/g, "-");
  return `UTC--${stamp}--${address.replace(/^0x/, "")}`;
}

/**
 * Encrypt an existing 32-byte secp256k1 secret (for example a MetaMask account key
 * exported from Account details) into a rholo keystore. The same key addresses an
 * Ethereum account and a rholo account; only the rholo use is stored here.
 */
export async function keystoreFromSecret(
  secretHex: string,
  password: string,
): Promise<CreatedKeystore> {
  if (password.length < 8) {
    throw new Error("Use a password of at least 8 characters.");
  }
  const secret = normalizeSecret(secretHex);
  const { initWasm, keystore_create, RholoKey } = await import("../wasm");
  await initWasm();
  let json: string;
  try {
    json = keystore_create(secret, password);
  } catch (caught) {
    throw new Error(
      `That private key cannot be used: ${caught instanceof Error ? caught.message : String(caught)}`,
    );
  }
  const ethAddress = keystoreAddress(json);
  return {
    json,
    secretHex: secret,
    revAddress: new RholoKey(secret).rev_address(),
    ethAddress,
    filename: keystoreFilename(ethAddress),
  };
}

/**
 * Create a new rholo account and return its encrypted v3 file. The caller is
 * responsible for saving `json`; the plaintext secret exists only in the returned
 * object and the browser's memory.
 */
export async function createKeystore(password: string): Promise<CreatedKeystore> {
  return keystoreFromSecret(randomSecretHex(), password);
}
