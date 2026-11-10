import { useEffect, useState } from "react";
import { formatEther } from "viem";
import { RELAYER_ISSUE } from "../App";
import {
  ASSETS,
  CHAIN_LABEL,
  CHAIN_WALLET,
  type Chain,
} from "../lib/assets";
import { loadConfig, type AppConfig } from "../lib/config";
import { readBridgeBalance, readBridgeConfig, type BridgeConfig } from "../lib/rholo";
import { readEthBalance, readVaultStatus, type VaultStatus } from "../lib/evm";
import { WALLET_FOR_CHAIN } from "../lib/wallets";

const CHAINS: Chain[] = ["ethereum", "tron", "agoric"];

export default function Overview() {
  const [config] = useState<AppConfig>(() => loadConfig());
  const [addresses, setAddresses] = useState<Partial<Record<Chain, string>>>({});
  const [errors, setErrors] = useState<Partial<Record<Chain, string>>>({});
  const [busy, setBusy] = useState<Partial<Record<Chain, boolean>>>({});
  const [bridge, setBridge] = useState<BridgeConfig | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [vault, setVault] = useState<VaultStatus | null>(null);
  const [vaultError, setVaultError] = useState<string | null>(null);
  const [balances, setBalances] = useState<Record<string, number | null>>({});
  const [ethBalance, setEthBalance] = useState<bigint | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      if (config.bridgeUri) {
        try {
          const status = await readBridgeConfig(config.node, config.bridgeUri);
          if (active) {
            setBridge(status);
            setBridgeError(status ? null : "bridge returned no config");
          }
        } catch (error) {
          if (active) setBridgeError(error instanceof Error ? error.message : String(error));
        }
        if (config.rholoAddress) {
          try {
            const entries = await Promise.all(
              ASSETS.filter((asset) => asset.enabled).map(async (asset) => {
                const key = `${asset.chain}.${asset.id}`;
                const balance = await readBridgeBalance(
                  config.node,
                  config.bridgeUri,
                  key,
                  config.rholoAddress,
                );
                return [key, balance] as const;
              }),
            );
            if (active) setBalances(Object.fromEntries(entries));
          } catch (error) {
            if (active) setBridgeError(error instanceof Error ? error.message : String(error));
          }
        }
      }

      if (config.vault && /^0x[0-9a-fA-F]{40}$/.test(config.vault)) {
        try {
          const status = await readVaultStatus(config.vault as `0x${string}`, config.anvilRpc);
          if (active) {
            setVault(status);
            setVaultError(null);
          }
        } catch (error) {
          if (active) setVaultError(error instanceof Error ? error.message : String(error));
        }
        const eth = addresses.ethereum;
        if (eth && /^0x[0-9a-fA-F]{40}$/.test(eth)) {
          try {
            const balance = await readEthBalance(config.anvilRpc, eth as `0x${string}`);
            if (active) setEthBalance(balance);
          } catch {
            if (active) setEthBalance(null);
          }
        }
      }
    }

    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [config, addresses.ethereum]);

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

  const wired = Boolean(config.bridgeUri && config.vault && config.rholoAddress);

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
          This is a devnet demo.{" "}
          {wired ? (
            <>Live reads are wired below; the ETH lock is on the Bridge page.</>
          ) : (
            <>
              Set the bridge URI, vault and rholo address in{" "}
              <a href="#/settings">Settings</a> to read the live rails.
            </>
          )}{" "}
          The relayer rail is still undecided; see{" "}
          <a href={RELAYER_ISSUE} target="_blank" rel="noreferrer">
            the proposal
          </a>
          .
        </p>
      </section>

      <section>
        <h2>Bridge state</h2>
        <div className="grid">
          <article className="card">
            <h3>rholo bridge</h3>
            {bridge ? (
              <>
                <p className="mono">{bridge.bridgeId}</p>
                <p className="muted">
                  network {bridge.network} · relayers {bridge.relayerThreshold}-of-N · admin{" "}
                  {bridge.adminThreshold}-of-N
                </p>
                <p className={bridge.paused ? "error" : "muted"}>
                  {bridge.paused ? "paused" : "active"}
                </p>
              </>
            ) : (
              <p className="muted">{bridgeError ?? "Not configured."}</p>
            )}
          </article>
          <article className="card">
            <h3>Anvil vault</h3>
            {vault ? (
              <>
                <p className="mono">{vault.assetKey}</p>
                <p className="muted">
                  locked {formatEther(vault.locked)} ETH · fees {formatEther(vault.fees)} ETH
                </p>
                <p className={vault.paused ? "error" : "muted"}>
                  {vault.paused ? "paused" : "active"}
                </p>
              </>
            ) : (
              <p className="muted">{vaultError ?? "Not configured."}</p>
            )}
          </article>
          <article className="card">
            <h3>rholo address</h3>
            <p className="mono">{config.rholoAddress || "—"}</p>
            <p className="hint">
              Balances below are read from the bridge for this address. Set it in Settings.
            </p>
          </article>
        </div>
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
                {errors[chain] ? <p className="error">{errors[chain]}</p> : null}
              </article>
            );
          })}
          <article className="card">
            <h3>rholo</h3>
            <p className="muted">r-bridge WASM keystore</p>
            <p className="mono">—</p>
            <p className="hint">Signing is the next web phase; reads are live.</p>
          </article>
        </div>
      </section>

      <section>
        <h2>Portfolio</h2>
        <p className="muted">
          Chain-qualified: USDT on Ethereum, Tron and Cosmos are distinct wrapped tokens.
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
              {ASSETS.filter((asset) => asset.enabled).map((asset) => {
                const key = `${asset.chain}.${asset.id}`;
                const wrapped = balances[key];
                const native =
                  asset.chain === "ethereum" && asset.id === "eth" && ethBalance !== null
                    ? `${formatEther(ethBalance)} ETH`
                    : "—";
                return (
                  <tr key={key}>
                    <td>{CHAIN_LABEL[asset.chain]}</td>
                    <td>{asset.symbol}</td>
                    <td className="mono">{asset.wrappedSymbol}</td>
                    <td className="muted">{native}</td>
                    <td>{wrapped === null || wrapped === undefined ? "—" : formatUnits(wrapped, asset.rholoDecimals)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="hint">
          Reads refresh every 5 seconds. After an ETH lock, the relayer mints and the
          wrapped balance appears here.
        </p>
      </section>
    </div>
  );
}

function shorten(address: string): string {
  return address.length <= 16 ? address : `${address.slice(0, 8)}…${address.slice(-6)}`;
}

function formatUnits(value: number, decimals: number): string {
  if (decimals === 0) return String(value);
  const negative = value < 0;
  const magnitude = Math.abs(value);
  const text = String(magnitude).padStart(decimals + 1, "0");
  const whole = text.slice(0, -decimals) || "0";
  const fraction = text.slice(-decimals).replace(/0+$/, "");
  return `${negative ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}
