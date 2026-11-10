import { describe, expect, it } from "vitest";
import {
  isTronAddress,
  lockTrc20,
  lockTrx,
  parseTronAmount,
  readTrc20Balance,
  readTrxBalance,
  TRON_ZERO_ADDRESS,
  tronBase58ToEth,
  tronHexToEth,
  type TronWebLike,
} from "./tron";

const OWNER = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t";
const VAULT = "TWS1Y2r3j4v5w6x7y8z9A1B2C3D4E5F6G7";
const TOKEN = "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj";
const OWNER_HEX = `41${"11".repeat(20)}`;

interface CallRecord {
  op: string;
  [key: string]: unknown;
}

function fakeTron(
  options: {
    allowance?: bigint;
    balance?: bigint;
    trx?: bigint;
    result?: string;
    sendShape?: "string" | "txid" | "transaction";
  } = {},
) {
  const calls: CallRecord[] = [];
  let allowance = options.allowance ?? 0n;
  const txid = (id: string) => {
    if (options.sendShape === "txid") return { txid: id };
    if (options.sendShape === "transaction") return { transaction: { txID: id } };
    return id;
  };
  const contractAt = async (address: string) => {
    calls.push({ op: "at", address });
    return {
      allowance: (owner: string, spender: string) => ({
        call: async () => {
          calls.push({ op: "allowance", owner, spender });
          return { toString: () => allowance.toString() };
        },
      }),
      approve: (spender: string, amount: string) => ({
        send: async () => {
          calls.push({ op: "approve", spender, amount });
          allowance = BigInt(amount);
          return txid("approve-tx");
        },
      }),
      balanceOf: (owner: string) => ({
        call: async () => {
          calls.push({ op: "balanceOf", owner });
          return options.balance ?? 3_000_000n;
        },
      }),
      lock: (token: string, amount: string, recipient: string, nonce: string) => ({
        send: async (sendOptions?: Record<string, unknown>) => {
          calls.push({ op: "lock", token, amount, recipient, nonce, options: sendOptions });
          return txid("lock-tx");
        },
      }),
    };
  };
  const tronWeb: TronWebLike = {
    defaultAddress: { base58: OWNER, hex: OWNER_HEX },
    address: { toHex: () => OWNER_HEX },
    contract: () => ({ at: contractAt }),
    trx: {
      getBalance: async () => options.trx ?? 9_000_000n,
      getTransactionInfo: async (id: string) => ({
        id,
        receipt: { result: options.result ?? "SUCCESS" },
      }),
    },
  };
  return { tronWeb, calls };
}

describe("Tron addresses and amounts", () => {
  it("converts a 41-prefixed address to its 20-byte payload", () => {
    expect(tronHexToEth(`0x41${"ab".repeat(20)}`)).toBe(`0x${"ab".repeat(20)}`);
    expect(() => tronHexToEth("41abcd")).toThrow(/Tron address/);
  });

  it("maps a base58 account through TronWeb", () => {
    const { tronWeb } = fakeTron();
    expect(tronBase58ToEth(tronWeb, OWNER)).toBe(`0x${"11".repeat(20)}`);
    expect(() => tronBase58ToEth(tronWeb, "not-a-tron-address")).toThrow(/base58/);
  });

  it("validates base58 addresses", () => {
    expect(isTronAddress(OWNER)).toBe(true);
    expect(isTronAddress("0x1234")).toBe(false);
  });

  it("parses 6-decimal amounts", () => {
    expect(parseTronAmount("1")).toBe("1000000");
    expect(parseTronAmount("0.000001")).toBe("1");
    expect(() => parseTronAmount("0")).toThrow(/greater than zero/);
    expect(() => parseTronAmount("1.1234567")).toThrow();
  });
});

describe("Tron locks", () => {
  it("approves a short allowance, then locks the TRC-20", async () => {
    const { tronWeb, calls } = fakeTron({ allowance: 0n });
    const result = await lockTrc20({
      tronWeb,
      vault: VAULT,
      token: TOKEN,
      amount: "1",
      rholoRecipient: "1111demo",
      nonce: 42,
      owner: OWNER,
    });

    expect(result).toEqual({ approve: "approve-tx", lock: "lock-tx" });
    const operations = calls.map((call) => call.op);
    expect(operations).toEqual(["at", "allowance", "approve", "at", "lock"]);
    const lock = calls.find((call) => call.op === "lock");
    expect(lock).toMatchObject({
      token: TOKEN,
      amount: "1000000",
      recipient: "1111demo",
      nonce: "42",
    });
    expect(lock?.options).toBeUndefined();
  });

  it("skips the approval when the allowance is sufficient", async () => {
    const { tronWeb, calls } = fakeTron({ allowance: 5_000_000n });
    const result = await lockTrc20({
      tronWeb,
      vault: VAULT,
      token: TOKEN,
      amount: "1",
      rholoRecipient: "1111demo",
      nonce: 1,
      owner: OWNER,
    });
    expect(result.approve).toBeUndefined();
    expect(calls.some((call) => call.op === "approve")).toBe(false);
  });

  it("locks TRX with the zero address and callValue", async () => {
    const { tronWeb, calls } = fakeTron();
    const hash = await lockTrx({
      tronWeb,
      vault: VAULT,
      amount: "0.5",
      rholoRecipient: "1111demo",
      nonce: 7,
      owner: OWNER,
    });
    expect(hash).toBe("lock-tx");
    const lock = calls.find((call) => call.op === "lock");
    expect(lock).toMatchObject({
      token: TRON_ZERO_ADDRESS,
      amount: "500000",
      options: { callValue: "500000" },
    });
  });

  it("accepts TronWeb's object-shaped send results", async () => {
    const { tronWeb } = fakeTron({ sendShape: "txid" });
    const hash = await lockTrx({
      tronWeb,
      vault: VAULT,
      amount: "1",
      rholoRecipient: "1111demo",
      nonce: 1,
      owner: OWNER,
    });
    expect(hash).toBe("lock-tx");
  });

  it("fails when the Tron receipt is not SUCCESS", async () => {
    const { tronWeb } = fakeTron({ result: "REVERT" });
    await expect(
      lockTrx({
        tronWeb,
        vault: VAULT,
        amount: "1",
        rholoRecipient: "1111demo",
        nonce: 1,
        owner: OWNER,
      }),
    ).rejects.toThrow(/REVERT/);
  });
});

describe("Tron reads", () => {
  it("reads TRX and TRC-20 balances", async () => {
    const { tronWeb } = fakeTron({ trx: 12_345_678n, balance: 4_000_000n });
    expect(await readTrxBalance(tronWeb, OWNER)).toBe(12_345_678n);
    expect(await readTrc20Balance(tronWeb, TOKEN, OWNER)).toBe(4_000_000n);
  });
});
