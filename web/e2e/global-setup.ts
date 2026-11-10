/**
 * Start an isolated Anvil and deploy the demo vault + mock USDT for the browser tests.
 *
 * Nothing here touches the developer's 8545 devnet. The deployed addresses are written
 * to `e2e/.state.json` (gitignored) for the specs.
 */
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const PORT = 8546;
const RPC = `http://127.0.0.1:${PORT}`;
/** Prefer an explicit env path, then the local Foundry install, then PATH. */
function tool(name: string, envName: string): string {
  const explicit = process.env[envName];
  if (explicit) return explicit;
  const local = resolve(homedir(), ".foundry/bin", name);
  return existsSync(local) ? local : name;
}

const FORGE = tool("forge", "FORGE");
const ANVIL = tool("anvil", "ANVIL");
const CAST = tool("cast", "CAST");

const PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";
const ACCOUNT = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"; // Anvil account 0

const ENV = {
  ADMIN1: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
  ADMIN2: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
  ADMIN3: "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
  RELAYER1: "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
  RELAYER2: "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
  RELAYER3: "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
  TREASURY: "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955",
};

let anvil: ChildProcess | undefined;

async function rpc(method: string): Promise<unknown> {
  const response = await fetch(RPC, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params: [] }),
  });
  const body = (await response.json()) as { result?: unknown; error?: { message: string } };
  if (body.error) throw new Error(body.error.message);
  return body.result;
}

async function waitForRpc(): Promise<void> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      await rpc("eth_chainId");
      return;
    } catch {
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
    }
  }
  throw new Error(`Anvil did not answer on ${RPC}`);
}

export default async function globalSetup(): Promise<() => void> {
  for (const [name, path] of [
    ["anvil", ANVIL],
    ["forge", FORGE],
    ["cast", CAST],
  ] as const) {
    if (path.includes("/") && !existsSync(path)) {
      throw new Error(`${name} not found at ${path}; install Foundry to run the e2e tests`);
    }
  }

  anvil = spawn(ANVIL, ["--port", String(PORT), "--silent"], { stdio: "ignore" });
  await waitForRpc();

  execFileSync(
    FORGE,
    ["script", "script/DeployAnvil.s.sol:DeployAnvil", "--rpc-url", RPC, "--broadcast"],
    {
      cwd: resolve(ROOT, "contracts/evm"),
      env: { ...process.env, PRIVATE_KEY, ...ENV },
      stdio: "inherit",
    },
  );

  const broadcast = JSON.parse(
    readFileSync(
      resolve(ROOT, "contracts/evm/broadcast/DeployAnvil.s.sol/31337/run-latest.json"),
      "utf8",
    ),
  ) as { transactions: Array<{ contractName?: string; contractAddress?: string }> };
  let vault = "";
  let token = "";
  for (const tx of broadcast.transactions) {
    if (tx.contractName === "BridgeVault" && tx.contractAddress) vault = tx.contractAddress;
    if (tx.contractName === "MockERC20" && tx.contractAddress) token = tx.contractAddress;
  }
  if (!vault || !token) {
    throw new Error("the deployment produced no BridgeVault/MockERC20 address");
  }

  // Give the test account 2 USDT to lock.
  execFileSync(
    CAST,
    [
      "send",
      token,
      "mint(address,uint256)",
      ACCOUNT,
      "2000000",
      "--private-key",
      PRIVATE_KEY,
      "--rpc-url",
      RPC,
    ],
    { stdio: "ignore" },
  );

  writeFileSync(
    resolve(HERE, ".state.json"),
    JSON.stringify({ rpc: RPC, vault, token, account: ACCOUNT }, null, 2),
  );

  return () => {
    anvil?.kill("SIGTERM");
  };
}
