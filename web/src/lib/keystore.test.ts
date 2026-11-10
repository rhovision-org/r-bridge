// @vitest-environment node
import { readFile } from "node:fs/promises";
import { beforeAll, describe, expect, it } from "vitest";
import { initWasm } from "../wasm";
import { createKeystore, keystoreAddress, randomSecretHex, unlockKeystore } from "./keystore";

beforeAll(async () => {
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
});
