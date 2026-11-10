import { describe, expect, it } from "vitest";
import { bridgeCall, decodeRho } from "./rholo";

describe("rho decoder", () => {
  it("decodes the bridge config tuple", () => {
    const wire = {
      ExprTuple: {
        data: [
          { ExprBool: { data: true } },
          {
            ExprMap: {
              data: {
                network: { ExprString: { data: "rbridge-devnet" } },
                paused: { ExprBool: { data: false } },
                relayerThreshold: { ExprInt: { data: 2 } },
              },
            },
          },
        ],
      },
    };
    expect(decodeRho(wire)).toEqual([
      true,
      { network: "rbridge-devnet", paused: false, relayerThreshold: 2 },
    ]);
  });

  it("decodes lists and bytes", () => {
    const wire = {
      ExprList: {
        data: [
          { ExprBytes: { data: "04aa" } },
          { ExprList: { data: [{ ExprInt: { data: 7 } }] } },
        ],
      },
    };
    expect(decodeRho(wire)).toEqual(["04aa", [7]]);
  });
});

describe("bridgeCall", () => {
  it("builds a registry read term", () => {
    const term = bridgeCall("rho:id:abc", '"config"');
    expect(term).toContain("rl!(`rho:id:abc`");
    expect(term).toContain('Bridge!("config", *ret)');
    expect(term.indexOf("new ret")).toBeLessThan(term.indexOf("rl!"));
  });

  it("refuses a non-registry URI", () => {
    expect(() => bridgeCall("http://example.com", '"config"')).toThrow();
    expect(() => bridgeCall("rho:id:", '"config"')).toThrow();
  });
});
