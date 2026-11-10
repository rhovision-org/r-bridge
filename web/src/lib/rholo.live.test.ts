// @vitest-environment node
/**
 * Opt-in live test against a running rholo devnet and an installed bridge.
 *
 *   RBRIDGE_LIVE=1 RBRIDGE_NODE=http://localhost:40403 \
 *   RBRIDGE_URI=$(jq -r .uri .devnet/bridge.json) \
 *   RBRIDGE_OWNER=$(jq -r .deployer.rev_address .devnet/demo-keys.json) \
 *   npm --prefix web run test
 */
import { describe, expect, it } from "vitest";
import { readBridgeBalance, readBridgeConfig } from "./rholo";

const live = process.env.RBRIDGE_LIVE === "1";
const node = process.env.RBRIDGE_NODE ?? "http://localhost:40403";
const uri = process.env.RBRIDGE_URI ?? "";
const owner = process.env.RBRIDGE_OWNER ?? "";

describe.skipIf(!live)("live rholo bridge", () => {
  it("reads the bridge config", async () => {
    const config = await readBridgeConfig(node, uri);
    expect(config?.network).toBe("rbridge-devnet");
    expect(config?.bridgeId).toBe("rbridge:devnet:bridge");
  });

  it("reads a holder balance", async () => {
    const balance = await readBridgeBalance(node, uri, "ethereum.eth", owner);
    expect(typeof balance).toBe("number");
  });
});
