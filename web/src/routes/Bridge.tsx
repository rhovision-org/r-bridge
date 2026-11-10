import { useMemo, useState } from "react";
import { parseUnits, zeroAddress, type Address } from "viem";
import { RELAYER_ISSUE } from "../App";
import { ASSETS, CHAIN_LABEL, type Chain } from "../lib/assets";
import { loadConfig } from "../lib/config";
import { depositIdFor, lockErc20, lockEth } from "../lib/evm";
import { keystoreAddress, revAddressFromEth, unlockKeystore } from "../lib/keystore";
import { loadSavedKeystores } from "../lib/keystore-store";
import {
  readRelayerDeposit,
  readRelayerWithdrawal,
  relayerUrlConfigured,
} from "../lib/relayer";
import { bridgeDeployTerm, burnCall } from "../lib/rholo";
import {
  getTronWeb,
  isTronAddress,
  lockTrc20,
  lockTrx,
  TRON_ZERO_ADDRESS,
  tronBase58ToEth,
} from "../lib/tron";
import { connectMetaMask, connectTronLink } from "../lib/wallets";

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
  const [savedAddress, setSavedAddress] = useState("");
  const [savedKeystores] = useState(() => loadSavedKeystores());
  const [account, setAccount] = useState<Address | null>(null);
  const [metaMaskRev, setMetaMaskRev] = useState<string | null>(null);
  const [tronAccount, setTronAccount] = useState<string | null>(null);
  const [tronRev, setTronRev] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tx, setTx] = useState<string | null>(null);
  const [approveTx, setApproveTx] = useState<string | null>(null);
  const [depositId, setDepositId] = useState<string | null>(null);
  const [relayerState, setRelayerState] = useState<string | null>(null);
  const [relayerError, setRelayerError] = useState<string | null>(null);
  const [withdrawal, setWithdrawal] = useState<WithdrawalState | null>(null);
  const [withdrawalRelay, setWithdrawalRelay] = useState<string | null>(null);
  const [withdrawalNativeTx, setWithdrawalNativeTx] = useState<string | null>(null);
  const [withdrawalRelayError, setWithdrawalRelayError] = useState<string | null>(null);

  // Deployment assets only: ETH/USDT on the TVM vault, ETH/USDT on Anvil. Other
  // registry assets stay read-only until they are in a deployment.
  const chainAssets = useMemo(() => {
    const deployed =
      chain === "ethereum"
        ? ["eth", "usdt"]
        : chain === "tron"
          ? ["trx", "usdt"]
          : undefined;
    return ASSETS.filter(
      (asset) =>
        asset.chain === chain &&
        asset.enabled &&
        (deployed === undefined || deployed.includes(asset.id)),
    );
  }, [chain]);
  const asset = chainAssets.find((candidate) => candidate.id === assetId) ?? chainAssets[0];
  const erc20Configured = /^0x[0-9a-fA-F]{40}$/.test(config.usdtToken);
  const evmToken: Address | null =
    chain !== "ethereum"
      ? null
      : asset?.id === "eth"
        ? zeroAddress
        : asset?.id === "usdt" && erc20Configured
          ? (config.usdtToken as Address)
          : null;
  const tronVaultConfigured = isTronAddress(config.tronVault);
  const tronToken: string | null =
    chain !== "tron"
      ? null
      : asset?.id === "trx"
        ? TRON_ZERO_ADDRESS
        : asset?.id === "usdt" && isTronAddress(config.tronUsdt)
          ? config.tronUsdt
          : null;
  const supported =
    (chain === "ethereum" && evmToken !== null) ||
    (chain === "tron" && tronToken !== null && tronVaultConfigured);
  const lockToken = chain === "tron" ? tronToken : evmToken;
  const needsApproval =
    lockToken !== null && lockToken !== zeroAddress && lockToken !== TRON_ZERO_ADDRESS;
  const lockAccount = chain === "ethereum" ? account : chain === "tron" ? tronAccount : null;
  const canLock =
    direction === "deposit" &&
    supported &&
    Boolean(lockAccount) &&
    Number(amount) > 0;
  const canBurn =
    direction === "withdraw" &&
    chain === "ethereum" &&
    evmToken !== null &&
    Boolean(config.bridgeUri) &&
    (Boolean(keystoreJson) ? Boolean(keystorePassword) : Boolean(rholoSecret)) &&
    Number(amount) > 0 &&
    /^0x[0-9a-fA-F]{40}$/.test(recipient);

  async function connect() {
    setError(null);
    try {
      const address = (await connectMetaMask()) as Address;
      setAccount(address);
      try {
        setMetaMaskRev(await revAddressFromEth(address));
      } catch {
        setMetaMaskRev(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function connectTron() {
    setError(null);
    try {
      const address = await connectTronLink();
      setTronAccount(address);
      const web = getTronWeb();
      if (web) {
        try {
          setTronRev(await revAddressFromEth(tronBase58ToEth(web, address)));
        } catch {
          setTronRev(null);
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  const RELAYER_LABEL: Record<string, string> = {
    waiting: "waiting for relayers",
    minted: "minted on rholo",
    failed: "failed",
    skipped: "skipped",
    dry_run: "dry-run (no mint)",
    unreachable: "unreachable",
  };

  const WITHDRAWAL_LABEL: Record<string, string> = {
    waiting: "waiting for relayers",
    unlocked: "unlocked on Anvil",
    failed: "unlock failed",
    ignored: "not handled by this relayer",
    unreachable: "unreachable",
  };

  /** Follow a processed burn until the relayer unlocks it (or refuses). */
  async function trackWithdrawal(base: string, withdrawalId: string) {
    setWithdrawalRelay("waiting");
    for (let attempt = 0; attempt < 30; attempt += 1) {
      try {
        const view = await readRelayerWithdrawal(base, withdrawalId);
        if (view) {
          setWithdrawalRelay(view.state);
          if (view.native_tx) setWithdrawalNativeTx(view.native_tx);
          if (view.reason || view.error) {
            setWithdrawalRelayError(view.reason ?? view.error ?? null);
          }
          if (["unlocked", "failed", "ignored"].includes(view.state)) return;
        }
      } catch (caught) {
        setWithdrawalRelay("unreachable");
        setWithdrawalRelayError(caught instanceof Error ? caught.message : String(caught));
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 2_000));
    }
  }

  async function trackDeposit(hash: string) {
    const base = config.relayerUrl.trim();
    if (!config.vault || !relayerUrlConfigured(base)) return;
    try {
      const id = await depositIdFor(
        hash as `0x${string}`,
        config.vault as Address,
        config.anvilRpc,
      );
      if (!id) return;
      setDepositId(id);
      setRelayerState("waiting");
      for (let attempt = 0; attempt < 30; attempt += 1) {
        try {
          const deposit = await readRelayerDeposit(base, id);
          if (deposit) {
            setRelayerState(deposit.state);
            if (deposit.error) setRelayerError(deposit.error);
            if (["minted", "failed", "skipped", "dry_run"].includes(deposit.state)) {
              return;
            }
          }
        } catch (caught) {
          setRelayerState("unreachable");
          setRelayerError(caught instanceof Error ? caught.message : String(caught));
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 2_000));
      }
    } catch (caught) {
      setRelayerError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function lock() {
    setError(null);
    setTx(null);
    setApproveTx(null);
    setDepositId(null);
    setRelayerState(null);
    setRelayerError(null);
    if (chain === "tron") {
      await lockOnTron();
      return;
    }
    if (!config.vault) {
      setError("Set the vault address in Settings first.");
      return;
    }
    if (!account) {
      setError("Connect MetaMask first.");
      return;
    }
    if (!evmToken) {
      setError("Set the USDT token address in Settings first.");
      return;
    }
    if (!recipient) {
      setError("Enter a rholo recipient.");
      return;
    }
    setBusy(true);
    try {
      let hash: string;
      if (evmToken === zeroAddress) {
        hash = await lockEth({
          vault: config.vault as Address,
          amountEth: amount,
          rholoRecipient: recipient,
          nonce: Date.now(),
          account,
          rpc: config.anvilRpc,
        });
      } else {
        const result = await lockErc20({
          vault: config.vault as Address,
          token: evmToken,
          amount,
          rholoRecipient: recipient,
          nonce: Date.now(),
          account,
          rpc: config.anvilRpc,
        });
        setApproveTx(result.approve ?? null);
        hash = result.lock;
      }
      setTx(hash);
      void trackDeposit(hash);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function lockOnTron() {
    if (!tronVaultConfigured) {
      setError("Set the Tron vault address in Settings first.");
      return;
    }
    if (!tronToken) {
      setError("Set the TRC-20 USDT address in Settings first.");
      return;
    }
    const web = getTronWeb();
    if (!web || !tronAccount) {
      setError("Connect TronLink first.");
      return;
    }
    if (!recipient) {
      setError("Enter a rholo recipient.");
      return;
    }
    setBusy(true);
    try {
      const nonce = Date.now();
      if (tronToken === TRON_ZERO_ADDRESS) {
        setTx(
          await lockTrx({
            tronWeb: web,
            vault: config.tronVault,
            amount,
            rholoRecipient: recipient,
            nonce,
            owner: tronAccount,
          }),
        );
      } else {
        const result = await lockTrc20({
          tronWeb: web,
          vault: config.tronVault,
          token: tronToken,
          amount,
          rholoRecipient: recipient,
          nonce,
          owner: tronAccount,
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

  function chooseSaved(address: string) {
    setSavedAddress(address);
    const item = savedKeystores.find((candidate) => candidate.address === address);
    setKeystoreJson(item?.json ?? "");
    setKeystoreAccount(item?.address ?? null);
    setError(null);
  }

  async function loadKeystore(file: File | undefined) {
    setError(null);
    setKeystoreAccount(null);
    setSavedAddress("");
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
    setWithdrawalRelay(null);
    setWithdrawalNativeTx(null);
    setWithdrawalRelayError(null);
    if (!config.bridgeUri) {
      setError("Set the bridge URI in Settings first.");
      return;
    }
    if (!keystoreJson && !rholoSecret) {
      setError("Choose a saved or on-disk keystore, or paste the devnet signer secret.");
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
        setError("Choose a saved or on-disk keystore, or paste the devnet signer secret.");
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
      let processed = false;
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
          processed = status.state === "processedWithSuccess";
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      if (processed && relayerUrlConfigured(config.relayerUrl)) {
        void trackWithdrawal(config.relayerUrl.trim(), withdrawalId);
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
          demo) mints after a native lock and unlocks after a rholo burn. Tron deposits
          build and sign the TVM `approve` + `lock` through TronLink, but the demo
          relayer watches Anvil only, so nothing is minted from Tron here. The rholo
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
            {savedKeystores.length > 0 ? (
              <div className="row">
                <label htmlFor="saved-keystore">Saved in this browser</label>
                <select
                  id="saved-keystore"
                  value={savedAddress}
                  onChange={(event) => chooseSaved(event.target.value)}
                >
                  <option value="">— choose a saved keystore —</option>
                  {savedKeystores.map((item) => (
                    <option key={item.address} value={item.address}>
                      {item.address}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <div className="row">
              <label htmlFor="keystore">
                {savedKeystores.length > 0 ? "or load from your device" : "rholo keystore"}
              </label>
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
              r-wallet uses). Pick a copy saved in this browser or load one from your
              device; the decrypted key is held only for this burn.
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

        {chain === "ethereum" ? (
          !account ? (
            <button type="button" onClick={connect}>
              Connect MetaMask
            </button>
          ) : (
            <>
              <p className="mono">MetaMask: {account}</p>
              {metaMaskRev ? (
                <p className="mono hint">
                  rholo address: {metaMaskRev}{" "}
                  {direction === "deposit" ? (
                    <button type="button" onClick={() => setRecipient(metaMaskRev)}>
                      Use as recipient
                    </button>
                  ) : null}
                </p>
              ) : null}
            </>
          )
        ) : chain === "tron" ? (
          !tronAccount ? (
            <button type="button" onClick={connectTron}>
              Connect TronLink
            </button>
          ) : (
            <>
              <p className="mono">TronLink: {tronAccount}</p>
              {tronRev ? (
                <p className="mono hint">
                  rholo address: {tronRev}{" "}
                  {direction === "deposit" ? (
                    <button type="button" onClick={() => setRecipient(tronRev)}>
                      Use as recipient
                    </button>
                  ) : null}
                </p>
              ) : null}
            </>
          )
        ) : (
          <p className="hint">
            Agoric writes use Keplr and the Zoe vat; they are not wired in this demo.
          </p>
        )}

        <button
          type="button"
          onClick={direction === "deposit" ? lock : burn}
          disabled={(direction === "deposit" ? !canLock : !canBurn) || busy}
        >
          {busy
            ? "Submitting…"
            : direction === "deposit"
              ? needsApproval
                ? "Approve and lock"
                : "Lock and mint"
              : "Burn and unlock"}
        </button>
        {!supported ? (
          <p className="hint">
            {chain === "ethereum" && asset?.id === "usdt"
              ? "Set the USDT token address in Settings (from .devnet/evm.json → token) to lock the ERC-20."
              : chain === "tron"
                ? "Set the Tron vault and TRC-20 USDT addresses in Settings to lock through TronLink."
                : "Writes in this UI are wired for Ethereum and Tron. Agoric uses the same contracts and is covered by the harness and tests."}
          </p>
        ) : null}
        {direction === "withdraw" && chain !== "ethereum" ? (
          <p className="hint">
            rholo → native withdrawal is wired for Ethereum in this demo. A Tron or
            Agoric unlock needs that chain's watcher and vault/vat adapter.
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
            Lock submitted: <span className="mono">{tx}</span>.{" "}
            {chain === "tron"
              ? "The demo relayer watches Anvil only, so a Tron deposit is not minted here; a production rail must watch the TVM vault."
              : "The relayer will attest and mint; the wrapped balance appears on the Overview page."}
          </p>
        ) : null}
        {depositId ? (
          <p className="hint">
            Deposit <span className="mono">{depositId}</span>: relayer{" "}
            {RELAYER_LABEL[relayerState ?? "waiting"] ?? relayerState}
            {relayerError ? ` (${relayerError})` : ""}.
          </p>
        ) : null}
        {withdrawal ? (
          <p className="hint">
            Withdrawal <span className="mono">{withdrawal.id}</span>: {withdrawal.state}.{" "}
            {withdrawal.state === "processedWithSuccess"
              ? withdrawalRelay
                ? `Relayer ${WITHDRAWAL_LABEL[withdrawalRelay] ?? withdrawalRelay}${
                    withdrawalNativeTx ? ` (tx ${withdrawalNativeTx})` : ""
                  }${withdrawalRelayError ? ` — ${withdrawalRelayError}` : ""}.`
                : "The relayer will unlock on Anvil and the destination balance updates after settlement."
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
            TronLink TRX/TRC-20 deposit calls against the same vault source; no Tron
            watcher runs in this demo.
          </li>
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
