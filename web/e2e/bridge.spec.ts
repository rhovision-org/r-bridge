/**
 * Browser tests for the flows that do not need the rholo devnet: MetaMask-shaped
 * deposits (ETH and USDT) and keystore creation. Anvil runs on 8546 and the injected
 * provider signs with Anvil account 0, so no wallet extension is required.
 */
import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

interface State {
  rpc: string;
  vault: string;
  token: string;
  account: string;
}

const HERE = dirname(fileURLToPath(import.meta.url));
let state: State;

test.beforeAll(() => {
  state = JSON.parse(readFileSync(resolve(HERE, ".state.json"), "utf8")) as State;
});

async function configure(
  page: Page,
  overrides: Record<string, unknown> = {},
): Promise<void> {
  await page.addInitScript(
    ({ config, overrides }: { config: State; overrides: Record<string, unknown> }) => {
      localStorage.setItem(
        "rbridge.config",
        JSON.stringify({
          node: "http://127.0.0.1:40403",
          bridgeUri: "",
          vault: config.vault,
          usdtToken: config.token,
          tronVault: "TWS1Y2r3j4v5w6x7y8z9A1B2C3D4E5F6G7",
          tronUsdt: "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
          relayerUrl: "http://127.0.0.1:9199",
          rholoAddress: "",
          anvilRpc: config.rpc,
          ...overrides,
        }),
      );

      const tronCalls: Array<Record<string, unknown>> = [];
      (window as unknown as { __tronCalls: unknown }).__tronCalls = tronCalls;
      const owner = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t";
      const ownerHex = `41${"11".repeat(20)}`;
      (window as unknown as { tronLink: unknown }).tronLink = {
        request: async () => ({ code: 200 }),
      };
      (window as unknown as { tronWeb: unknown }).tronWeb = {
        defaultAddress: { base58: owner, hex: ownerHex },
        address: { toHex: () => ownerHex },
        contract: () => ({
          at: async (address: string) => ({
            allowance: () => ({
              call: async () => {
                tronCalls.push({ op: "allowance", address });
                return { toString: () => "0" };
              },
            }),
            approve: (spender: string, amount: string) => ({
              send: async () => {
                tronCalls.push({ op: "approve", spender, amount });
                return "approve-tx";
              },
            }),
            balanceOf: () => ({ call: async () => "0" }),
            lock: (token: string, amount: string, recipient: string, nonce: string) => ({
              send: async (options?: Record<string, unknown>) => {
                tronCalls.push({ op: "lock", token, amount, recipient, nonce, options });
                return "lock-tx";
              },
            }),
          }),
        }),
        trx: {
          getBalance: async () => "9000000",
          getTransactionInfo: async (txid: string) => ({
            id: txid,
            receipt: { result: "SUCCESS" },
          }),
        },
      };

      let nextId = 1;
      Object.defineProperty(window, "ethereum", {
        configurable: true,
        value: {
          isMetaMask: true,
          request: async ({
            method,
            params,
          }: {
            method: string;
            params?: unknown[];
          }) => {
            if (method === "eth_requestAccounts" || method === "eth_accounts") {
              return [config.account];
            }
            if (
              method === "wallet_switchEthereumChain" ||
              method === "wallet_addEthereumChain"
            ) {
              return null;
            }
            const response = await fetch(config.rpc, {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                jsonrpc: "2.0",
                id: nextId++,
                method,
                params: params ?? [],
              }),
            });
            const body = (await response.json()) as {
              result?: unknown;
              error?: { message?: string };
            };
            if (body.error) throw new Error(body.error.message ?? "rpc error");
            return body.result;
          },
        },
      });
    },
    { config: state, overrides },
  );
}

async function routeRelayer(page: Page, depositState = "minted"): Promise<void> {
  await page.route("http://127.0.0.1:9199/**", async (route) => {
    const url = route.request().url();
    const headers = { "access-control-allow-origin": "*" };
    if (url.endsWith("/health")) {
      return route.fulfill({
        status: 200,
        headers,
        json: {
          version: "dev",
          chains: ["ethereum"],
          threshold: 2,
          signers: 3,
          paused: false,
          halted: null,
          last_block: 12,
        },
      });
    }
    if (url.endsWith("/v1/chains")) {
      return route.fulfill({
        status: 200,
        headers,
        json: [{ chain: "ethereum", head: 12, enabled: true }],
      });
    }
    if (url.includes("/v1/deposits/")) {
      return route.fulfill({
        status: 200,
        headers,
        json: { state: depositState, signatures: [] },
      });
    }
    if (url.includes("/v1/withdrawals/")) {
      return route.fulfill({
        status: 200,
        headers,
        json: { state: "unlocked", native_tx: "0xfeed" },
      });
    }
    return route.fulfill({ status: 404, headers, json: {} });
  });
}

/**
 * A stubbed rholo node: enough of /api/v1/{nodes,status,deploy,deploy-status} for the
 * WASM signer to submit a deploy and see it processed. The deploy is recorded so the
 * test can check the signed term; nothing on rholo actually runs.
 */
async function routeNode(
  page: Page,
): Promise<Array<{ data?: { term?: string } }>> {
  const deploys: Array<{ data?: { term?: string } }> = [];
  const headers = {
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "*",
    "access-control-allow-methods": "*",
  };
  await page.route("http://127.0.0.1:40403/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers });
    }
    const url = request.url();
    if (url.endsWith("/api/v1/nodes")) {
      return route.fulfill({ status: 404, headers, json: {} });
    }
    if (url.endsWith("/api/v1/status")) {
      return route.fulfill({
        status: 200,
        headers,
        json: {
          address: "",
          networkId: "testnet",
          shardId: "/root",
          minPhloPrice: 1,
          latestBlockNumber: 1,
          proposer: true,
          acceptsDeploys: true,
        },
      });
    }
    if (url.endsWith("/api/v1/deploy") && request.method() === "POST") {
      deploys.push(request.postDataJSON() as { data?: { term?: string } });
      return route.fulfill({ status: 200, headers, json: { message: "dispatch" } });
    }
    if (url.includes("/api/v1/deploy-status/")) {
      return route.fulfill({
        status: 200,
        headers,
        json: {
          ProcessedWithSuccess: {
            deployResult: [],
            block: { blockHash: "00", blockNumber: 1 },
          },
        },
      });
    }
    return route.fulfill({ status: 404, headers, json: {} });
  });
  return deploys;
}

test.beforeEach(async ({ page }) => {
  await configure(page);
});

test("locks ETH through the configured vault and follows the relayer", async ({ page }) => {
  await routeRelayer(page);
  await page.goto("/#/bridge");
  await page.getByRole("button", { name: "Connect MetaMask" }).click();
  await expect(page.getByText(/MetaMask: 0xf39F/)).toBeVisible();
  await expect(page.getByText(/rholo address: 1111/)).toBeVisible();
  await page.getByRole("button", { name: "Use as recipient" }).click();
  await expect(page.getByLabel("rholo recipient")).toHaveValue(/^1111/);

  await page.getByLabel("Amount").fill("0.1");
  await page.getByRole("button", { name: "Lock and mint" }).click();

  await expect(page.getByText(/Lock submitted: 0x/)).toBeVisible();
  await expect(page.getByText(/relayer minted on rholo/)).toBeVisible();
  await page.goto("/#/");
  await expect(page.getByText(/locked 0\.1 ETH/)).toBeVisible();
});

test("burns in the browser and follows the withdrawal through the relayer", async ({
  page,
}) => {
  // The node is stubbed: the WASM signer, the burn term and the relayer polling are
  // real, but no rholo cluster runs in this suite.
  await configure(page, { bridgeUri: "rho:id:testbridge" });
  const deploys = await routeNode(page);
  await routeRelayer(page);

  await page.goto("/#/bridge");
  await page.getByLabel("Direction").selectOption("withdraw");
  await page.getByLabel("Amount").fill("0.05");
  await page
    .getByLabel("Native recipient")
    .fill("0x2222222222222222222222222222222222222222");
  await page
    .getByLabel("or dev secret")
    .fill("a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76");
  await page.getByRole("button", { name: "Burn and unlock" }).click();

  await expect(page.getByText(/processedWithSuccess/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Relayer unlocked on Anvil \(tx 0xfeed\)/)).toBeVisible();

  expect(deploys).toHaveLength(1);
  expect(deploys[0].data?.term).toContain('"burn"');
  expect(deploys[0].data?.term).toContain(
    '"0x2222222222222222222222222222222222222222"',
  );
  expect(deploys[0].data?.term).toContain('"web-withdraw-');
});

test("shows relayer health and chains on Overview", async ({ page }) => {
  await routeRelayer(page);
  await page.goto("/#/");
  await expect(page.getByText(/3 signers/)).toBeVisible();
  await expect(page.getByText(/ethereum: head 12/)).toBeVisible();
});

test("approves and locks USDT", async ({ page }) => {
  await page.goto("/#/bridge");
  await page.getByRole("button", { name: "Connect MetaMask" }).click();
  await page.getByLabel("Asset").selectOption("usdt");
  await page.getByLabel("Amount").fill("1");
  await page.getByLabel("rholo recipient").fill("1111demo");

  await expect(page.getByRole("button", { name: "Approve and lock" })).toBeVisible();
  await page.getByRole("button", { name: "Approve and lock" }).click();

  await expect(page.getByText(/Approval mined: 0x/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Lock submitted: 0x/)).toBeVisible();
  await page.goto("/#/");
  await expect(page.getByText(/locked 1 USDT/)).toBeVisible();
});

test("builds a TronLink approve and lock for TRC-20 USDT", async ({ page }) => {
  await page.goto("/#/bridge");
  await page.getByLabel("Chain").selectOption("tron");
  await page.getByRole("button", { name: "Connect TronLink" }).click();
  await expect(page.getByText(/TronLink: TR7N/)).toBeVisible();
  await expect(page.getByText(/rholo address: 1111/)).toBeVisible();
  await page.getByRole("button", { name: "Use as recipient" }).click();
  await expect(page.getByLabel("rholo recipient")).toHaveValue(/^1111/);

  await page.getByLabel("Asset").selectOption("usdt");
  await page.getByLabel("Amount").fill("1");
  await page.getByRole("button", { name: "Approve and lock" }).click();

  await expect(page.getByText(/Approval mined: approve-tx/)).toBeVisible();
  await expect(page.getByText(/Lock submitted: lock-tx/)).toBeVisible();
  await expect(page.getByText(/a Tron deposit is not minted here/)).toBeVisible();

  const calls = await page.evaluate(
    () =>
      (window as unknown as { __tronCalls: Array<Record<string, unknown>> }).__tronCalls,
  );
  expect(calls.filter((call) => call.op === "approve")).toHaveLength(1);
  const lock = calls.find((call) => call.op === "lock");
  expect(lock).toMatchObject({
    token: "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
    amount: "1000000",
    recipient: expect.stringMatching(/^1111/),
  });
});

test("shows Tron balances after TronLink connects", async ({ page }) => {
  await page.goto("/#/");
  await page.getByRole("button", { name: "Connect TronLink" }).click();
  await expect(page.getByText(/TR7NHqje/)).toBeVisible();
  await expect(page.getByText(/9 TRX/)).toBeVisible();
});

test("refuses an amount above the vault cap before sending", async ({ page }) => {
  await page.goto("/#/bridge");
  await page.getByRole("button", { name: "Connect MetaMask" }).click();
  await page.getByLabel("Asset").selectOption("usdt");
  await page.getByLabel("Amount").fill("2000000");
  await page.getByLabel("rholo recipient").fill("1111demo");
  await page.getByRole("button", { name: "Approve and lock" }).click();

  await expect(page.getByText(/per-deposit cap/)).toBeVisible();
  await expect(page.getByText(/Lock submitted/)).toHaveCount(0);
});

test("creates and downloads a Web3 v3 keystore", async ({ page }) => {
  await page.goto("/#/settings");
  await page.getByLabel("Password", { exact: true }).fill("interop-password");
  await page.getByLabel("Confirm", { exact: true }).fill("interop-password");

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Create and download" }).click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toMatch(/^UTC--.*--[0-9a-f]{40}(\.json)?$/);
  const path = await download.path();
  expect(path).not.toBeNull();
  const json = JSON.parse(readFileSync(path as string, "utf8")) as {
    version: number;
    crypto: { kdf: string; cipher: string };
  };
  expect(json.version).toBe(3);
  expect(json.crypto.kdf).toBe("scrypt");
  expect(json.crypto.cipher).toBe("aes-128-ctr");
  await expect(page.getByText(/REV 1111/)).toBeVisible();
});

test("imports a MetaMask key and saves only the encrypted copy", async ({ page }) => {
  const secret = "4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318";
  await page.goto("/#/settings");
  await page.locator("#import-key").fill(`0x${secret}`);
  await page.locator("#import-password").fill("interop-password");
  await page.locator("#import-confirm").fill("interop-password");
  await page.locator("#import-save").check();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Encrypt and download" }).click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toMatch(/^UTC--.*--2c7536e3605d9c16a7a3d7b1898e529396a65c23(\.json)?$/);
  await expect(page.getByText(/ETH 0x2c7536e3605d9c16a7a3d7b1898e529396a65c23/)).toBeVisible();
  await expect(page.getByText(/REV 1111/)).toBeVisible();

  const stored = (await page.evaluate(() => localStorage.getItem("rbridge.keystores"))) ?? "";
  expect(stored).toContain("ciphertext");
  expect(stored).not.toContain(secret);
  expect(stored).not.toContain("interop-password");

  await page.reload();
  await expect(page.getByText("0x2c7536e3605d9c16a7a3d7b1898e529396a65c23")).toBeVisible();
});
