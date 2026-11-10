// @vitest-environment node
/**
 * Opt-in live test against a running Anvil and the deployed demo vault.
 *
 *   RBRIDGE_LIVE=1 RBRIDGE_VAULT=$(jq -r .vault .devnet/evm.json) \
 *   RBRIDGE_USDT=$(jq -r .token .devnet/evm.json) \
 *   RBRIDGE_ANVIL_RPC=http://127.0.0.1:8545 npm --prefix web run test
 *
 * The ERC-20 case injects a MetaMask-shaped EIP-1193 provider backed by an Anvil
 * account, so the browser approve/lock path runs unchanged in Node.
 */
import { describe, expect, it } from "vitest";
import { createPublicClient, createWalletClient, http, parseAbi } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import {
  anvilChain,
  lockErc20,
  readTokenAllowance,
  readTokenBalance,
  readVaultStatus,
} from "./evm";

const live = process.env.RBRIDGE_LIVE === "1";
const vault = (process.env.RBRIDGE_VAULT ?? "") as `0x${string}`;
const usdt = (process.env.RBRIDGE_USDT ?? "") as `0x${string}`;
const rpc = process.env.RBRIDGE_ANVIL_RPC ?? "http://127.0.0.1:8545";
const anvilKey = (process.env.RBRIDGE_ANVIL_KEY ??
  "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80") as `0x${string}`;

const MINT_ABI = parseAbi(["function mint(address to, uint256 amount)"]);

describe.skipIf(!live)("live Anvil vault", () => {
  it("reads the vault status", async () => {
    const status = await readVaultStatus(vault, rpc);
    expect(status.assetKey).toBe("ethereum.eth");
    expect(status.paused).toBe(false);
    expect(typeof status.locked).toBe("bigint");
  });

  it.skipIf(!usdt)("reads the ERC-20 asset status", async () => {
    const status = await readVaultStatus(vault, rpc, usdt);
    expect(status.assetKey).toBe("ethereum.usdt");
    expect(status.decimals).toBe(6);
    expect(status.scale).toBe(1n);
    expect(typeof status.locked).toBe("bigint");
  });

  it.skipIf(!usdt)("approves and locks an ERC-20 through the MetaMask-shaped provider", async () => {
    const account = privateKeyToAccount(anvilKey);
    const publicClient = createPublicClient({ chain: anvilChain(rpc), transport: http(rpc) });
    const wallet = createWalletClient({ chain: anvilChain(rpc), transport: http(rpc), account });

    // Give the account 2 USDT to lock.
    const mintHash = await wallet.writeContract({
      address: usdt,
      abi: MINT_ABI,
      functionName: "mint",
      args: [account.address, 2_000_000n],
    });
    await publicClient.waitForTransactionReceipt({ hash: mintHash });

    // MetaMask-shaped provider: chain switching is a no-op, everything else goes to
    // Anvil, which signs for its unlocked accounts like an injected wallet would.
    (globalThis as { window?: unknown }).window = {
      ethereum: {
        request: async ({ method, params }: { method: string; params?: unknown[] }) => {
          if (method === "wallet_switchEthereumChain" || method === "wallet_addEthereumChain") {
            return null;
          }
          return wallet.request({ method, params } as Parameters<typeof wallet.request>[0]);
        },
      },
    };

    const before = await readTokenBalance(usdt, rpc, account.address);
    const vaultBefore = await readVaultStatus(vault, rpc, usdt);
    const result = await lockErc20({
      vault,
      token: usdt,
      amount: "1",
      rholoRecipient: "1111devnetrecipient",
      nonce: Date.now(),
      account: account.address,
      rpc,
    });
    await publicClient.waitForTransactionReceipt({ hash: result.lock });

    expect(result.approve).toBeDefined();
    expect(await readTokenAllowance(usdt, rpc, account.address, vault)).toBeLessThan(2_000_000n);
    expect(await readTokenBalance(usdt, rpc, account.address)).toBe(before - 1_000_000n);
    const vaultAfter = await readVaultStatus(vault, rpc, usdt);
    expect(vaultAfter.locked).toBe(vaultBefore.locked + 1_000_000n);

    delete (globalThis as { window?: unknown }).window;
    expect(account.address).toBeDefined();
  });
});
