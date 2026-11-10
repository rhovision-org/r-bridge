import { useState } from "react";
import { loadConfig, saveConfig, type AppConfig } from "../lib/config";

export default function Settings() {
  const [config, setConfig] = useState<AppConfig>(() => loadConfig());
  const [saved, setSaved] = useState(false);

  function set(key: keyof AppConfig, value: string) {
    setConfig((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  function save() {
    saveConfig(config);
    setSaved(true);
  }

  return (
    <div className="stack">
      <section>
        <h1>Settings</h1>
        <p className="muted">
          Stored in this browser only. No account keys are kept here; native accounts
          remain in their wallets and the rholo signer is a separate module.
        </p>
      </section>

      <section className="card form">
        <div className="row">
          <label htmlFor="node">rholo node</label>
          <input id="node" value={config.node} onChange={(event) => set("node", event.target.value)} />
        </div>
        <div className="row">
          <label htmlFor="bridge">Bridge URI</label>
          <input
            id="bridge"
            placeholder="rho:id:…"
            value={config.bridgeUri}
            onChange={(event) => set("bridgeUri", event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="vault">Anvil vault</label>
          <input
            id="vault"
            placeholder="0x…"
            value={config.vault}
            onChange={(event) => set("vault", event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="usdt">USDT token (Anvil)</label>
          <input
            id="usdt"
            placeholder="0x…"
            value={config.usdtToken}
            onChange={(event) => set("usdtToken", event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="rholo">rholo address</label>
          <input
            id="rholo"
            placeholder="1111…"
            value={config.rholoAddress}
            onChange={(event) => set("rholoAddress", event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="anvil">Anvil RPC</label>
          <input
            id="anvil"
            value={config.anvilRpc}
            onChange={(event) => set("anvilRpc", event.target.value)}
          />
        </div>
        <button type="button" onClick={save}>
          Save
        </button>
        {saved ? <p className="hint">Saved. Reload the page to re-read the portfolio.</p> : null}
      </section>

      <section className="card">
        <h2>Where these values come from</h2>
        <ul>
          <li>
            <span className="mono">.devnet/bridge.json</span> — the installed bridge URI.
          </li>
          <li>
            <span className="mono">.devnet/evm.json</span> — the Anvil vault address and
            the mock USDT token (the ERC-20 lock is disabled until the token is set).
          </li>
          <li>
            <span className="mono">.devnet/demo-keys.json</span> — the devnet deployer's REV
            address (rholo address). Dev keys only.
          </li>
        </ul>
      </section>
    </div>
  );
}
