// @vitest-environment node
import { readFile } from "node:fs/promises";
import { beforeAll, describe, expect, it } from "vitest";
import { initWasm } from "../wasm";
import {
  createKeystore,
  keystoreAddress,
  keystoreFromSecret,
  randomSecretHex,
  revAddressFromEth,
  unlockKeystore,
} from "./keystore";
import { loadSavedKeystores, saveKeystore } from "./keystore-store";

const METAMASK_KEY = "0x4C0883A69102937D6231471B5DBB6204FE5129617082792AE468D01A3F362318";

beforeAll(async () => {
  const items = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => items.get(key) ?? null,
      setItem: (key: string, value: string) => items.set(key, value),
      removeItem: (key: string) => items.delete(key),
      clear: () => items.clear(),
    },
  });
  const bytes = await readFile(new URL("../wasm/pkg/rbridge_wasm_bg.wasm", import.meta.url));
  await initWasm(new Uint8Array(bytes));
});

describe("keystore helpers", () => {
  it("parses the Ethereum address from a v3 file", () => {
    const json = JSON.stringify({ version: 3, address: "2C7536E3605D9C16A7A3D7B1898E529396A65C23" });
    expect(keystoreAddress(json)).toBe("0x2c7536e3605d9c16a7a3d7b1898e529396a65c23");
  });

  it("refuses a file without an address", () => {
    expect(() => keystoreAddress("{}")).toThrow(/address/);
    expect(() => keystoreAddress("not json")).toThrow(/JSON/);
  });

  it("generates a 32-byte secret", () => {
    expect(randomSecretHex()).toMatch(/^[0-9a-f]{64}$/);
  });

  it("round-trips create and unlock through the WASM keystore", async () => {
    const created = await createKeystore("interop-password");
    expect(keystoreAddress(created.json)).toBe(created.ethAddress);
    expect(created.revAddress.startsWith("1111")).toBe(true);

    const unlocked = await unlockKeystore(created.json, "interop-password");
    expect(unlocked.secretHex).toBe(created.secretHex);
    expect(unlocked.revAddress).toBe(created.revAddress);
  });

  it("refuses the wrong password", async () => {
    const created = await createKeystore("interop-password");
    await expect(unlockKeystore(created.json, "wrong-password")).rejects.toThrow(/password/i);
  });

  it("requires a password of at least 8 characters", async () => {
    await expect(createKeystore("short")).rejects.toThrow(/8 characters/);
  });

  it("encrypts a MetaMask key and never stores the plaintext", async () => {
    const created = await keystoreFromSecret(METAMASK_KEY, "interop-password");
    expect(created.ethAddress).toBe("0x2c7536e3605d9c16a7a3d7b1898e529396a65c23");
    expect(created.secretHex).toBe(METAMASK_KEY.toLowerCase().slice(2));
    expect(created.revAddress.startsWith("1111")).toBe(true);

    saveKeystore(created.json);
    const stored = JSON.stringify(loadSavedKeystores()).toLowerCase();
    expect(stored).toContain("ciphertext");
    expect(stored).not.toContain(created.secretHex);
    expect(stored).not.toContain("interop-password");
  });

  it("maps an Ethereum address to the key's REV address", async () => {
    const created = await keystoreFromSecret(METAMASK_KEY, "interop-password");
    expect(await revAddressFromEth(created.ethAddress)).toBe(created.revAddress);
    expect(await revAddressFromEth(created.ethAddress.slice(2))).toBe(created.revAddress);
  });

  it("refuses a malformed private key", async () => {
    await expect(keystoreFromSecret("0x1234", "interop-password")).rejects.toThrow(/64 hex/);
    await expect(keystoreFromSecret("zz".repeat(32), "interop-password")).rejects.toThrow(
      /64 hex/,
    );
  });

  it("refuses a zero private key", async () => {
    await expect(keystoreFromSecret("00".repeat(32), "interop-password")).rejects.toThrow(
      /cannot be used/,
    );
  });
});
