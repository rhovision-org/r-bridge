import { beforeEach, describe, expect, it } from "vitest";
import {
  findSavedKeystore,
  forgetKeystore,
  loadSavedKeystores,
  saveKeystore,
} from "./keystore-store";

const ADDRESS = "2c7536e3605d9c16a7a3d7b1898e529396a65c23";
const OTHER = "1a642f0e3c3af545e7acbd38b07251b3990914f1";

function stubJson(address = ADDRESS): string {
  return JSON.stringify({
    version: 3,
    address,
    crypto: { cipher: "aes-128-ctr", ciphertext: "00".repeat(32), kdf: "scrypt" },
  });
}

beforeEach(() => {
  localStorage.clear();
});

describe("encrypted keystore store", () => {
  it("saves, finds and forgets by address", () => {
    saveKeystore(stubJson());
    expect(loadSavedKeystores()).toHaveLength(1);
    expect(findSavedKeystore(`0x${ADDRESS.toUpperCase()}`)?.address).toBe(`0x${ADDRESS}`);

    forgetKeystore(`0x${ADDRESS}`);
    expect(loadSavedKeystores()).toHaveLength(0);
  });

  it("replaces an existing entry instead of duplicating it", () => {
    saveKeystore(stubJson());
    saveKeystore(stubJson());
    expect(loadSavedKeystores()).toHaveLength(1);

    saveKeystore(stubJson(OTHER));
    expect(loadSavedKeystores()).toHaveLength(2);
  });

  it("ignores corrupted storage", () => {
    localStorage.setItem("rbridge.keystores", "{not json");
    expect(loadSavedKeystores()).toEqual([]);
    localStorage.setItem("rbridge.keystores", JSON.stringify([{ address: "nope" }]));
    expect(loadSavedKeystores()).toEqual([]);
  });
});
