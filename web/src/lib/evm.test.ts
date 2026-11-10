import { describe, expect, it } from "vitest";
import { anvilChain, formatEth, VAULT_ABI } from "./evm";

describe("vault client", () => {
  it("builds the Anvil chain from the configured RPC", () => {
    const chain = anvilChain("http://localhost:8545");
    expect(chain.id).toBe(31337);
    expect(chain.rpcUrls.default.http[0]).toBe("http://localhost:8545");
  });

  it("exposes the lock arm", () => {
    expect(VAULT_ABI.some((item) => "name" in item && item.name === "lock")).toBe(true);
  });

  it("formats wei as ETH", () => {
    expect(formatEth(100_000_000_000_000_000n)).toBe("0.1");
  });
});
