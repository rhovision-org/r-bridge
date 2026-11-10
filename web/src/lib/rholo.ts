/**
 * Read-only rholo bridge client for the browser.
 *
 * The node's exploratory deploy returns the value on the first private name; every term
 * here binds `ret` first, looks up the bridge bundle, and calls one read arm. No key,
 * phlo or wasm is needed for reads. Writes still require the rholo signer (next phase).
 */

const URI = /^rho:id:[A-Za-z0-9:._/-]+$/;
const SAFE = /^[A-Za-z0-9:._/-]+$/;

export interface BridgeConfig {
  network: string;
  bridgeId: string;
  paused: boolean;
  relayerThreshold: number;
  adminThreshold: number;
}

/** Decode the node's externally tagged RhoExpr JSON into plain JS values. */
export function decodeRho(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(decodeRho);
  }
  if (value && typeof value === "object") {
    const tagged = value as Record<string, { data?: unknown }>;
    const tag = Object.keys(tagged)[0];
    const payload = tagged[tag]?.data;
    switch (tag) {
      case "ExprInt":
      case "ExprString":
      case "ExprBool":
      case "ExprUri":
        return payload;
      case "ExprNil":
        return null;
      case "ExprBytes":
        return payload as string;
      case "ExprList":
      case "ExprTuple":
        return (payload as unknown[]).map(decodeRho);
      case "ExprMap": {
        if (Array.isArray(payload)) {
          return Object.fromEntries(
            (payload as [unknown, unknown][]).map(([key, item]) => [
              String(decodeRho(key)),
              decodeRho(item),
            ]),
          );
        }
        return Object.fromEntries(
          Object.entries(payload as Record<string, unknown>).map(([key, item]) => [
            key,
            decodeRho(item),
          ]),
        );
      }
      default:
        return value;
    }
  }
  return value;
}

export function bridgeCall(uri: string, call: string): string {
  if (!URI.test(uri)) {
    throw new Error("bridge URI must be a rho:id:… registry URI");
  }
  return [
    "new ret, rl(`rho:registry:lookup`), ch in {",
    `  rl!(\`${uri}\`, *ch) |`,
    "  for (Bridge <- ch) {",
    `    Bridge!(${call}, *ret)`,
    "  }",
    "}",
  ].join("\n");
}

export function bridgeDeployTerm(uri: string, call: string): string {
  if (!URI.test(uri)) {
    throw new Error("bridge URI must be a rho:id:… registry URI");
  }
  return [
    "new ret(`rho:rchain:deployId`), rl(`rho:registry:lookup`), ch in {",
    `  rl!(\`${uri}\`, *ch) |`,
    "  for (Bridge <- ch) {",
    `    Bridge!(${call}, *ret)`,
    "  }",
    "}",
  ].join("\n");
}

/** Build the burn arm arguments for a chain-qualified asset. */
export function burnCall(
  assetKey: string,
  amount: string,
  destChain: string,
  destAddress: string,
  withdrawalId: string,
): string {
  const [chain, assetId] = assetKey.split(".");
  if (!chain || !assetId || !SAFE.test(chain) || !SAFE.test(assetId)) {
    throw new Error("invalid asset key");
  }
  if (!/^\d+$/.test(amount) || amount === "0") {
    throw new Error("amount must be a positive integer string");
  }
  if (!SAFE.test(destChain)) {
    throw new Error("invalid destination chain");
  }
  if (!/^0x[0-9a-fA-F]{40}$/.test(destAddress)) {
    throw new Error("destination must be a 20-byte 0x address");
  }
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(withdrawalId)) {
    throw new Error("withdrawal id has unsupported characters");
  }
  return [
    `"burn", "${chain}", "${assetId}", ${amount},`,
    `"${destChain}", "${destAddress.toLowerCase()}", "${withdrawalId}"`,
  ].join(" ");
}

export async function explore(node: string, term: string): Promise<unknown> {
  const res = await fetch(`${node.replace(/\/$/, "")}/api/explore-deploy`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(term),
  });
  if (!res.ok) {
    throw new Error(`explore failed: ${res.status} ${await res.text()}`);
  }
  const data = (await res.json()) as { expr?: unknown[] };
  return data.expr?.[0] === undefined ? null : decodeRho(data.expr[0]);
}

export async function readBridgeConfig(node: string, uri: string): Promise<BridgeConfig | null> {
  const result = await explore(node, bridgeCall(uri, '"config"'));
  if (Array.isArray(result) && result[0] === true) {
    return result[1] as BridgeConfig;
  }
  return null;
}

export async function readBridgeBalance(
  node: string,
  uri: string,
  assetKey: string,
  owner: string,
): Promise<number | null> {
  if (!SAFE.test(assetKey) || !SAFE.test(owner)) {
    throw new Error("asset key and owner must be simple string literals");
  }
  const call = `"balanceOf", "${assetKey}", "${owner}"`;
  const result = await explore(node, bridgeCall(uri, call));
  if (Array.isArray(result) && result[0] === true) {
    return Number(result[1]);
  }
  return null;
}
