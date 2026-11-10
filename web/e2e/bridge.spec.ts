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

async function configure(page: Page): Promise<void> {
  await page.addInitScript(
    (config: State) => {
      localStorage.setItem(
        "rbridge.config",
        JSON.stringify({
          node: "http://127.0.0.1:40403",
          bridgeUri: "",
          vault: config.vault,
          usdtToken: config.token,
          tronVault: "TWS1Y2r3j4v5w6x7y8z9A1B2C3D4E5F6G7",
          tronUsdt: "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
          rholoAddress: "",
          anvilRpc: config.rpc,
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
    state,
  );
}

test.beforeEach(async ({ page }) => {
  await configure(page);
});

test("locks ETH through the configured vault", async ({ page }) => {
  await page.goto("/#/bridge");
  await page.getByRole("button", { name: "Connect MetaMask" }).click();
  await expect(page.getByText(/MetaMask: 0xf39F/)).toBeVisible();
  await expect(page.getByText(/rholo address: 1111/)).toBeVisible();
  await page.getByRole("button", { name: "Use as recipient" }).click();
  await expect(page.getByLabel("rholo recipient")).toHaveValue(/^1111/);

  await page.getByLabel("Amount").fill("0.1");
  await page.getByRole("button", { name: "Lock and mint" }).click();

  await expect(page.getByText(/Lock submitted: 0x/)).toBeVisible();
  await page.goto("/#/");
  await expect(page.getByText(/locked 0\.1 ETH/)).toBeVisible();
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
