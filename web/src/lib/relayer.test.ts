import { afterEach, describe, expect, it, vi } from "vitest";
import {
  readRelayerChains,
  readRelayerDeposit,
  readRelayerHealth,
  relayerUrlConfigured,
} from "./relayer";

function stub(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("relayer client", () => {
  it("reads health from the configured base URL", async () => {
    const fetchMock = stub({
      version: "dev",
      chains: ["ethereum"],
      threshold: 2,
      signers: 3,
      halted: null,
    });
    const health = await readRelayerHealth("http://127.0.0.1:8099/");
    expect(health.threshold).toBe(2);
    expect(health.signers).toBe(3);
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8099/health");
  });

  it("accepts both chain response shapes", async () => {
    stub([{ chain: "ethereum", head: 12, enabled: true }]);
    const chains = await readRelayerChains("http://127.0.0.1:8099");
    expect(chains[0]).toMatchObject({ chain: "ethereum", head: 12 });

    stub({ chains: ["ethereum", "tron"] });
    const named = await readRelayerChains("http://127.0.0.1:8099");
    expect(named).toEqual([
      { chain: "ethereum", enabled: true },
      { chain: "tron", enabled: true },
    ]);
  });

  it("returns null for a missing deposit", async () => {
    stub({}, 404);
    expect(await readRelayerDeposit("http://127.0.0.1:8099", "0xabc:0")).toBeNull();
  });

  it("reads a deposit", async () => {
    stub({ state: "minted", signatures: ["aa"] });
    const deposit = await readRelayerDeposit("http://127.0.0.1:8099", "0xabc:0");
    expect(deposit?.state).toBe("minted");
  });

  it("reports non-200 responses", async () => {
    stub({ error: "boom" }, 500);
    await expect(readRelayerHealth("http://127.0.0.1:8099")).rejects.toThrow(/HTTP 500/);
  });

  it("rejects a URL without a scheme", async () => {
    await expect(readRelayerHealth("127.0.0.1:8099")).rejects.toThrow(/http/);
  });

  it("detects a configured URL", () => {
    expect(relayerUrlConfigured("http://127.0.0.1:8099")).toBe(true);
    expect(relayerUrlConfigured("https://relayer.example/")).toBe(true);
    expect(relayerUrlConfigured("")).toBe(false);
    expect(relayerUrlConfigured("relayer.example")).toBe(false);
  });
});
