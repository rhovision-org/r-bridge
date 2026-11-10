import { describe, expect, it } from "vitest";
import {
  anvilChain,
  ERC20_ABI,
  formatEth,
  formatNative,
  lockAmountError,
  needsApproval,
  VAULT_ABI,
} from "./evm";

describe("vault client", () => {
  it("builds the Anvil chain from the configured RPC", () => {
    const chain = anvilChain("http://localhost:8545");
    expect(chain.id).toBe(31337);
    expect(chain.rpcUrls.default.http[0]).toBe("http://localhost:8545");
  });

  it("exposes the lock arm", () => {
    expect(VAULT_ABI.some((item) => "name" in item && item.name === "lock")).toBe(true);
  });

  it("exposes the ERC-20 approve and allowance arms", () => {
    const names = ERC20_ABI.map((item) => ("name" in item ? item.name : ""));
    expect(names).toEqual(expect.arrayContaining(["approve", "allowance", "balanceOf", "decimals"]));
  });

  it("asks for approval only when the allowance is short", () => {
    expect(needsApproval(0n, 1_000_000n)).toBe(true);
    expect(needsApproval(999_999n, 1_000_000n)).toBe(true);
    expect(needsApproval(1_000_000n, 1_000_000n)).toBe(false);
    expect(needsApproval(2_000_000n, 1_000_000n)).toBe(false);
  });

  it("mirrors the vault's lock checks", () => {
    const asset = { enabled: true, maxDeposit: 20_000_000_000n, scale: 10_000_000_000n };
    expect(lockAmountError(10_000_000_000n, asset)).toBeNull();
    expect(lockAmountError(20_000_000_001n, asset)).toMatch(/cap/);
    expect(lockAmountError(1_500n, asset)).toMatch(/multiple/);
    expect(lockAmountError(1n, { ...asset, enabled: false })).toMatch(/not enabled/);
  });

  it("formats wei as ETH", () => {
    expect(formatEth(100_000_000_000_000_000n)).toBe("0.1");
  });

  it("formats token units with the token's decimals", () => {
    expect(formatNative(1_000_000n, 6)).toBe("1");
    expect(formatNative(400_000n, 6)).toBe("0.4");
  });
});
