import { useMemo, useState } from "react";
import type { Address, Hash } from "viem";
import { RELAYER_ISSUE } from "../App";
import { ASSETS, CHAIN_LABEL, type Chain } from "../lib/assets";
import { loadConfig } from "../lib/config";
import { lockEth } from "../lib/evm";
import { connectMetaMask } from "../lib/wallets";

type Direction = "deposit" | "withdraw";

export default function Bridge() {
  const [config] = useState(() => loadConfig());
  const [chain, setChain] = useState<Chain>("ethereum");
  const [assetId, setAssetId] = useState("eth");
  const [direction, setDirection] = useState<Direction>("deposit");
  const [amount, setAmount] = useState("");
  const [recipient, setRecipient] = useState(config.rholoAddress);
  const [account, setAccount] = useState<Address | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tx, setTx] = useState<Hash | null>(null);

  const chainAssets = useMemo(
    () => ASSETS.filter((asset) => asset.chain === chain && asset.enabled),
    [chain],
  );
  const asset = chainAssets.find((candidate) => candidate.id === assetId) ?? chainAssets[0];
  const ethDeposit = direction === "deposit" && chain === "ethereum" && asset?.id === "eth";
  const canLock = ethDeposit && Boolean(config.vault) && Boolean(account) && Number(amount) > 0;

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
    if (!config.vault) {
      setError("Set the vault address in Settings first.");
      return;
    }
    if (!account) {
      setError("Connect MetaMask first.");
      return;
    }
    if (!recipient) {
      setError("Enter a rholo recipient.");
      return;
    }
    setBusy(true);
    try {
      const hash = await lockEth({
        vault: config.vault as Address,
        amountEth: amount,
        rholoRecipient: recipient,
        nonce: Date.now(),
        account,
        rpc: config.anvilRpc,
      });
      setTx(hash);
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
          The ETH lock is live against the configured Anvil vault. The relayer
          (or <span className="mono">make relayer-watch</span> in the demo) mints on rholo
          after finality. Withdraw is still settled by the harness/relayer in this pass.
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

        {!account ? (
          <button type="button" onClick={connect}>
            Connect MetaMask
          </button>
        ) : (
          <p className="mono">MetaMask: {account}</p>
        )}

        <button type="button" onClick={lock} disabled={!canLock || busy}>
          {busy ? "Locking…" : direction === "deposit" ? "Lock and mint" : "Burn and unlock"}
        </button>
        {!ethDeposit ? (
          <p className="hint">
            This UI wires the ETH lock only. ERC-20 locks and the withdrawal direction
            use the same vault/contracts and are covered by the harness and tests.
          </p>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
        {tx ? (
          <p className="hint">
            Lock submitted: <span className="mono">{tx}</span>. The relayer will attest
            and mint; the wrapped balance appears on the Overview page.
          </p>
        ) : null}
      </section>

      <section className="card">
        <h2>What is live in this demo</h2>
        <ol>
          <li>rholo bridge reads via exploratory deploy (no key needed).</li>
          <li>Anvil vault deposits, thresholds, caps and fee accounting (9 Foundry tests).</li>
          <li>MetaMask ETH lock into the configured vault.</li>
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
