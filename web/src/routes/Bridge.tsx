import { useMemo, useState } from "react";
import { RELAYER_ISSUE } from "../App";
import { ASSETS, CHAIN_LABEL, type Chain } from "../lib/assets";

type Direction = "deposit" | "withdraw";

export default function Bridge() {
  const [chain, setChain] = useState<Chain>("ethereum");
  const [assetId, setAssetId] = useState("usdt");
  const [direction, setDirection] = useState<Direction>("deposit");
  const [amount, setAmount] = useState("");
  const [recipient, setRecipient] = useState("");

  const chainAssets = useMemo(
    () => ASSETS.filter((asset) => asset.chain === chain && asset.enabled),
    [chain],
  );
  const asset =
    chainAssets.find((candidate) => candidate.id === assetId) ?? chainAssets[0];

  return (
    <div className="stack">
      <section>
        <h1>Bridge</h1>
        <p className="notice">
          The bridge contracts and the relayer add-on are not deployed. This
          form is the intended flow and cannot submit a transaction yet.
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
            placeholder="0.00"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </div>

        <div className="row">
          <label htmlFor="recipient">
            {direction === "deposit" ? "rholo recipient" : "Native recipient"}
          </label>
          <input
            id="recipient"
            placeholder={
              direction === "deposit" ? "rho:id:…" : "destination address"
            }
            value={recipient}
            onChange={(event) => setRecipient(event.target.value)}
          />
        </div>

        <button type="button" disabled>
          {direction === "deposit" ? "Lock and mint" : "Burn and unlock"}
        </button>
        <p className="hint">
          {direction === "deposit"
            ? "After the native lock reaches finality, relayers attest it and the wrapped token is minted on rholo."
            : "After the rholo burn is finalized, relayers sign the unlock and the native vault releases the asset."}
        </p>
      </section>

      <section className="card">
        <h2>What has to exist first</h2>
        <ol>
          <li>rholo bridge suite: BridgeRoot, WrappedToken, Bridge, Attestation.</li>
          <li>Native vaults: Ethereum/Tron vault, Agoric vat.</li>
          <li>
            An m-of-n relayer add-on run by node operators —{" "}
            <a href={RELAYER_ISSUE} target="_blank" rel="noreferrer">
              issue #563
            </a>
            .
          </li>
        </ol>
      </section>
    </div>
  );
}
