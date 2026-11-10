// @vitest-environment node
/**
 * Opt-in live test against a running Anvil and the deployed demo vault.
 *
 *   RBRIDGE_LIVE=1 RBRIDGE_VAULT=$(jq -r .vault .devnet/evm.json) \
 *   RBRIDGE_ANVIL_RPC=http://127.0.0.1:8545 npm --prefix web run test
 */
import { describe, expect, it } from "vitest";
import { readVaultStatus } from "./evm";

const live = process.env.RBRIDGE_LIVE === "1";
const vault = (process.env.RBRIDGE_VAULT ?? "") as `0x${string}`;
const rpc = process.env.RBRIDGE_ANVIL_RPC ?? "http://127.0.0.1:8545";

describe.skipIf(!live)("live Anvil vault", () => {
  it("reads the vault status", async () => {
    const status = await readVaultStatus(vault, rpc);
    expect(status.assetKey).toBe("ethereum.eth");
    expect(status.paused).toBe(false);
    expect(typeof status.locked).toBe("bigint");
  });
});
