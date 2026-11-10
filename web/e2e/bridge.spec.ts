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
          rholoAddress: "",
          anvilRpc: config.rpc,
        }),
      );

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

  await page.getByLabel("Amount").fill("0.1");
  await page.getByLabel("rholo recipient").fill("1111demo");
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
  await page.getByLabel("Confirm").fill("interop-password");

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
