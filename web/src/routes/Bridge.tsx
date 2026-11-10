import { useMemo, useState } from "react";
import { parseUnits, zeroAddress, type Address, type Hash } from "viem";
import { RELAYER_ISSUE } from "../App";
import { ASSETS, CHAIN_LABEL, type Chain } from "../lib/assets";
import { loadConfig } from "../lib/config";
import { lockErc20, lockEth } from "../lib/evm";
import { keystoreAddress, unlockKeystore } from "../lib/keystore";
import { bridgeDeployTerm, burnCall } from "../lib/rholo";
import { connectMetaMask } from "../lib/wallets";

type Direction = "deposit" | "withdraw";

interface WithdrawalState {
  id: string;
  state: string;
  result?: unknown;
}

export default function Bridge() {
  const [config] = useState(() => loadConfig());
  const [chain, setChain] = useState<Chain>("ethereum");
  const [assetId, setAssetId] = useState("eth");
  const [direction, setDirection] = useState<Direction>("deposit");
  const [amount, setAmount] = useState("");
  const [recipient, setRecipient] = useState(config.rholoAddress);
  const [rholoSecret, setRholoSecret] = useState("");
  const [keystoreJson, setKeystoreJson] = useState("");
  const [keystorePassword, setKeystorePassword] = useState("");
  const [keystoreAccount, setKeystoreAccount] = useState<string | null>(null);
  const [account, setAccount] = useState<Address | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tx, setTx] = useState<Hash | null>(null);
  const [approveTx, setApproveTx] = useState<Hash | null>(null);
  const [withdrawal, setWithdrawal] = useState<WithdrawalState | null>(null);

  // The demo vault has ETH and USDT; the other registry assets are read-only until
  // they are added to a deployment.
  const chainAssets = useMemo(
    () =>
      ASSETS.filter(
        (asset) =>
          asset.chain === chain &&
          asset.enabled &&
          (chain !== "ethereum" || asset.id === "eth" || asset.id === "usdt"),
      ),
    [chain],
  );
  const asset = chainAssets.find((candidate) => candidate.id === assetId) ?? chainAssets[0];
  const erc20Configured = /^0x[0-9a-fA-F]{40}$/.test(config.usdtToken);
  const token: Address | null =
    chain !== "ethereum"
      ? null
      : asset?.id === "eth"
        ? zeroAddress
        : asset?.id === "usdt" && erc20Configured
          ? (config.usdtToken as Address)
          : null;
  const supported = chain === "ethereum" && token !== null;
  const canLock =
    direction === "deposit" &&
    supported &&
    Boolean(config.vault) &&
    Boolean(account) &&
    Number(amount) > 0;
  const canBurn =
    direction === "withdraw" &&
    supported &&
    Boolean(config.bridgeUri) &&
    (Boolean(keystoreJson) ? Boolean(keystorePassword) : Boolean(rholoSecret)) &&
    Number(amount) > 0 &&
    /^0x[0-9a-fA-F]{40}$/.test(recipient);

  async function connect() {
    setError(null);
    try {
      setAccount((await connectMetaMask()) as Address);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function lock() {
    setError(null);
    setTx(null);
    setApproveTx(null);
    if (!config.vault) {
      setError("Set the vault address in Settings first.");
      return;
    }
    if (!account) {
      setError("Connect MetaMask first.");
      return;
    }
    if (!token) {
      setError(
        chain === "ethereum"
          ? "Set the USDT token address in Settings first."
          : "Native → rholo writes are wired for Ethereum in this demo. Tron and Agoric use the same vault/vat; see the harness.",
      );
      return;
    }
    if (!recipient) {
      setError("Enter a rholo recipient.");
      return;
    }
    setBusy(true);
    try {
      if (token === zeroAddress) {
        const hash = await lockEth({
          vault: config.vault as Address,
          amountEth: amount,
          rholoRecipient: recipient,
          nonce: Date.now(),
          account,
          rpc: config.anvilRpc,
        });
        setTx(hash);
      } else {
        const result = await lockErc20({
          vault: config.vault as Address,
          token,
          amount,
          rholoRecipient: recipient,
          nonce: Date.now(),
          account,
          rpc: config.anvilRpc,
        });
        setApproveTx(result.approve ?? null);
        setTx(result.lock);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function loadKeystore(file: File | undefined) {
    setError(null);
    setKeystoreAccount(null);
    if (!file) {
      setKeystoreJson("");
      return;
    }
    if (file.size > 32 * 1024) {
      setError("That file is too large to be a keystore.");
      return;
    }
    try {
      const text = await file.text();
      setKeystoreAccount(keystoreAddress(text));
      setKeystoreJson(text);
    } catch (caught) {
      setKeystoreJson("");
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function burn() {
    setError(null);
    setWithdrawal(null);
    if (!config.bridgeUri) {
      setError("Set the bridge URI in Settings first.");
      return;
    }
    if (!keystoreJson && !rholoSecret) {
      setError("Choose a keystore file or paste the devnet signer secret.");
      return;
    }
    if (!/^0x[0-9a-fA-F]{40}$/.test(recipient)) {
      setError("Enter a 20-byte 0x destination address.");
      return;
    }
    setBusy(true);
    try {
      let secret = rholoSecret;
      if (keystoreJson) {
        try {
          secret = (await unlockKeystore(keystoreJson, keystorePassword)).secretHex;
        } catch (caught) {
          setError(
            `Could not unlock the keystore: ${caught instanceof Error ? caught.message : String(caught)}`,
          );
          return;
        }
      }
      if (!secret) {
        setError("Choose a keystore file or paste the devnet signer secret.");
        return;
      }
      const { initWasm, RholoClient, RholoKey } = await import("../wasm");
      await initWasm();
      const key = new RholoKey(secret);
      const signerAddress = key.rev_address();
      if (config.rholoAddress && signerAddress !== config.rholoAddress) {
        setError(
          `signer address ${signerAddress} does not match the configured rholo address ${config.rholoAddress}`,
        );
        return;
      }
      const amountRholo = parseUnits(amount, asset?.rholoDecimals ?? 8).toString();
      const withdrawalId = `web-withdraw-${Date.now()}`;
      const call = burnCall(`${chain}.${asset?.id}`, amountRholo, "ethereum", recipient, withdrawalId);
      const term = bridgeDeployTerm(config.bridgeUri, call);
      const client = new RholoClient(config.node);
      const deployId = await client.deploy(term, secret, 8_000_000n);
      setWithdrawal({ id: withdrawalId, state: "submitted", result: deployId });
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const status = JSON.parse(await client.deploy_status(deployId)) as {
          state: string;
          deploy_result?: unknown;
          deploy_error?: string;
        };
        if (status.state !== "notProcessed") {
          setWithdrawal({
            id: withdrawalId,
            state: status.state,
            result: status.deploy_result ?? status.deploy_error,
          });
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section>
        <h1>Bridge</h1>
        <p className="notice">
          ETH and ERC-20 (USDT) deposit and withdraw are live against the configured
          rails. The relayer (or <span className="mono">make relayer-watch</span> in the
          demo) mints after a native lock and unlocks after a rholo burn. The rholo
          signer below is a devnet key; never use one holding real value.
        </p>
      </section>

      <section className="card form">
        <div className="row">
          <label htmlFor="direction">Direction</label>
          <select
            id="direction"
            value={direction}
            onChange={(event) => setDirection(event.target.value as Direction)}
          >
            <option value="deposit">Native → rholo (lock & mint)</option>
            <option value="withdraw">rholo → native (burn & unlock)</option>
          </select>
        </div>

        <div className="row">
          <label htmlFor="chain">Chain</label>
          <select
            id="chain"
            value={chain}
            onChange={(event) => {
              const next = event.target.value as Chain;
              setChain(next);
              const first = ASSETS.find((item) => item.chain === next && item.enabled);
              if (first) setAssetId(first.id);
            }}
          >
            {(["ethereum", "tron", "agoric"] as Chain[]).map((value) => (
              <option key={value} value={value}>
                {CHAIN_LABEL[value]}
              </option>
            ))}
          </select>
        </div>

        <div className="row">
          <label htmlFor="asset">Asset</label>
          <select
            id="asset"
            value={asset?.id ?? ""}
            onChange={(event) => setAssetId(event.target.value)}
          >
            {chainAssets.map((item) => (
              <option key={item.id} value={item.id}>
                {item.symbol} → {item.wrappedSymbol}
              </option>
            ))}
          </select>
        </div>

        <div className="row">
          <label htmlFor="amount">Amount</label>
          <input
            id="amount"
            inputMode="decimal"
            placeholder="0.1"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </div>

        <div className="row">
          <label htmlFor="recipient">{direction === "deposit" ? "rholo recipient" : "Native recipient"}</label>
          <input
            id="recipient"
            placeholder={direction === "deposit" ? "1111…" : "0x…"}
            value={recipient}
            onChange={(event) => setRecipient(event.target.value)}
          />
        </div>

        {direction === "withdraw" ? (
          <>
            <div className="row">
              <label htmlFor="keystore">rholo keystore</label>
              <input
                id="keystore"
                type="file"
                accept="application/json,.json"
                onChange={(event) => loadKeystore(event.target.files?.[0])}
              />
            </div>
            {keystoreAccount ? <p className="mono hint">{keystoreAccount}</p> : null}
            <div className="row">
              <label htmlFor="keystore-password">Keystore password</label>
              <input
                id="keystore-password"
                type="password"
                value={keystorePassword}
                onChange={(event) => setKeystorePassword(event.target.value)}
              />
            </div>
            <p className="hint">
              Unlocked in the browser by the WASM keystore (Web3 v3, the same file
              r-wallet uses). The decrypted key is held only for this burn.
            </p>
            <div className="row">
              <label htmlFor="secret">or dev secret</label>
              <input
                id="secret"
                type="password"
                placeholder="64-char hex secret"
                value={rholoSecret}
                onChange={(event) => setRholoSecret(event.target.value)}
              />
            </div>
            <p className="hint">
              Devnet only. The signer must hold the wrapped token and REV for phlo. It is
              kept in memory for this session and never persisted. A keystore file takes
              precedence when both are provided.
            </p>
          </>
        ) : null}

        {!account ? (
          <button type="button" onClick={connect}>
            Connect MetaMask
          </button>
        ) : (
          <p className="mono">MetaMask: {account}</p>
        )}

        <button
          type="button"
          onClick={direction === "deposit" ? lock : burn}
          disabled={(direction === "deposit" ? !canLock : !canBurn) || busy}
        >
          {busy
            ? "Submitting…"
            : direction === "deposit"
              ? token && token !== zeroAddress
                ? "Approve and lock"
                : "Lock and mint"
              : "Burn and unlock"}
        </button>
        {!supported ? (
          <p className="hint">
            {chain === "ethereum" && asset?.id === "usdt"
              ? "Set the USDT token address in Settings (from .devnet/evm.json → token) to lock the ERC-20."
              : "Writes in this UI are wired for Ethereum (ETH and USDT through MetaMask). Tron and Agoric use the same contracts and are covered by the harness and tests."}
          </p>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
        {approveTx ? (
          <p className="hint">
            Approval mined: <span className="mono">{approveTx}</span>.
          </p>
        ) : null}
        {tx ? (
          <p className="hint">
            Lock submitted: <span className="mono">{tx}</span>. The relayer will attest
            and mint; the wrapped balance appears on the Overview page.
          </p>
        ) : null}
        {withdrawal ? (
          <p className="hint">
            Withdrawal <span className="mono">{withdrawal.id}</span>: {withdrawal.state}.{" "}
            {withdrawal.state === "processedWithSuccess"
              ? "The relayer will unlock on Anvil and the destination balance updates after settlement."
              : String(withdrawal.result ?? "")}
          </p>
        ) : null}
      </section>

      <section className="card">
        <h2>What is live in this demo</h2>
        <ol>
          <li>rholo bridge reads via exploratory deploy (no key needed).</li>
          <li>Anvil vault deposits, thresholds, caps and fee accounting (10 Foundry tests).</li>
          <li>MetaMask ETH and USDT locks (approve + lock) and WASM-signed rholo burn.</li>
          <li>
            Relayer watcher (<span className="mono">make relayer-watch</span>) minting on
            rholo and unlocking on Anvil.
          </li>
        </ol>
        <p className="hint">
          The relayer rail is still undecided:{" "}
          <a href={RELAYER_ISSUE} target="_blank" rel="noreferrer">
            rhovision-org/rholo#563
          </a>
          .
        </p>
      </section>
    </div>
  );
}
