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

/**
 * Create a new rholo account and return its encrypted v3 file. The caller is
 * responsible for saving `json`; the plaintext secret exists only in the returned
 * object and the browser's memory.
 */
export async function createKeystore(password: string): Promise<CreatedKeystore> {
  if (password.length < 8) {
    throw new Error("Use a password of at least 8 characters.");
  }
  const { initWasm, keystore_create, RholoKey } = await import("../wasm");
  await initWasm();
  const secretHex = randomSecretHex();
  const json = keystore_create(secretHex, password);
  const ethAddress = keystoreAddress(json);
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return {
    json,
    secretHex,
    revAddress: new RholoKey(secretHex).rev_address(),
    ethAddress,
    filename: `UTC--${stamp}--${ethAddress.slice(2)}`,
  };
}
