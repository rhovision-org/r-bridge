import { useState } from "react";
import { RELAYER_ISSUE } from "../App";
import {
  ASSETS,
  CHAIN_LABEL,
  CHAIN_WALLET,
  type Chain,
} from "../lib/assets";
import { WALLET_FOR_CHAIN } from "../lib/wallets";

const CHAINS: Chain[] = ["ethereum", "tron", "agoric"];

export default function Overview() {
  const [addresses, setAddresses] = useState<Partial<Record<Chain, string>>>({});
  const [errors, setErrors] = useState<Partial<Record<Chain, string>>>({});
  const [busy, setBusy] = useState<Partial<Record<Chain, boolean>>>({});

  async function connect(chain: Chain) {
    setBusy((current) => ({ ...current, [chain]: true }));
    setErrors((current) => ({ ...current, [chain]: undefined }));
    try {
      const address = await WALLET_FOR_CHAIN[chain].connect();
      setAddresses((current) => ({ ...current, [chain]: address }));
    } catch (error) {
      setErrors((current) => ({
        ...current,
        [chain]: error instanceof Error ? error.message : String(error),
      }));
    } finally {
      setBusy((current) => ({ ...current, [chain]: false }));
    }
  }

  return (
    <div className="stack">
      <section className="hero">
        <h1>Move assets between rholo and native chains</h1>
        <p>
          Cosmos/Agoric, Ethereum and Tron. Native accounts stay in MetaMask,
          TronLink and Keplr; r-bridge adds the rholo account and the bridge
          flow.
        </p>
        <p className="notice">
          This build is a scaffold. No contracts are deployed and no value can
          move. Production relaying depends on the{" "}
          <a href={RELAYER_ISSUE} target="_blank" rel="noreferrer">
            rholo node relayer add-on
          </a>
          .
        </p>
      </section>

      <section>
        <h2>Wallets</h2>
        <div className="grid">
          {CHAINS.map((chain) => {
            const wallet = WALLET_FOR_CHAIN[chain];
            const address = addresses[chain];
            return (
              <article className="card" key={chain}>
                <h3>{CHAIN_LABEL[chain]}</h3>
                <p className="muted">{CHAIN_WALLET[chain]}</p>
                {address ? (
                  <p className="mono">{shorten(address)}</p>
                ) : (
                  <button
                    type="button"
                    onClick={() => connect(chain)}
                    disabled={busy[chain]}
                  >
                    {busy[chain] ? "Connecting…" : `Connect ${wallet.name}`}
                  </button>
                )}
                {errors[chain] ? (
                  <p className="error">{errors[chain]}</p>
                ) : null}
              </article>
            );
          })}
          <article className="card">
            <h3>rholo</h3>
            <p className="muted">r-bridge WASM keystore</p>
            <p className="mono">—</p>
            <p className="hint">
              The one account the wallets cannot sign for. Created in the next
              phase.
            </p>
          </article>
        </div>
      </section>

      <section>
        <h2>Assets</h2>
        <p className="muted">
          Chain-qualified: USDT on Ethereum, Tron and Cosmos are three distinct
          wrapped tokens.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Chain</th>
                <th>Asset</th>
                <th>Wrapped on rholo</th>
                <th>Native balance</th>
                <th>Wrapped balance</th>
              </tr>
            </thead>
            <tbody>
              {ASSETS.map((asset) => (
                <tr key={`${asset.chain}.${asset.id}`}>
                  <td>{CHAIN_LABEL[asset.chain]}</td>
                  <td>{asset.symbol}</td>
                  <td className="mono">{asset.wrappedSymbol}</td>
                  <td className="muted">—</td>
                  <td className="muted">—</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function shorten(address: string): string {
  return address.length <= 16
    ? address
    : `${address.slice(0, 8)}…${address.slice(-6)}`;
}
