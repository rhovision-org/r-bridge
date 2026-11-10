import { useState } from "react";
import { loadConfig, saveConfig, type AppConfig } from "../lib/config";
import { createKeystore } from "../lib/keystore";

export default function Settings() {
  const [config, setConfig] = useState<AppConfig>(() => loadConfig());
  const [saved, setSaved] = useState(false);
  const [ksPassword, setKsPassword] = useState("");
  const [ksConfirm, setKsConfirm] = useState("");
  const [ksBusy, setKsBusy] = useState(false);
  const [ksError, setKsError] = useState<string | null>(null);
  const [created, setCreated] = useState<{
    revAddress: string;
    ethAddress: string;
    filename: string;
  } | null>(null);

  async function createAccount() {
    setKsError(null);
    setCreated(null);
    if (ksPassword !== ksConfirm) {
      setKsError("Passwords do not match.");
      return;
    }
    setKsBusy(true);
    try {
      const result = await createKeystore(ksPassword);
      const url = URL.createObjectURL(
        new Blob([result.json], { type: "application/json" }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setCreated({
        revAddress: result.revAddress,
        ethAddress: result.ethAddress,
        filename: result.filename,
      });
      setKsPassword("");
      setKsConfirm("");
    } catch (caught) {
      setKsError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setKsBusy(false);
    }
  }

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

      <section className="card form">
        <h2>Create a rholo keystore</h2>
        <p className="muted">
          A Web3 v3 keystore (scrypt + AES-128-CTR) for a new rholo account. The same
          file opens in r-wallet. It encrypts the key; the password is never stored and
          cannot be recovered, so back up both.
        </p>
        <div className="row">
          <label htmlFor="ks-password">Password</label>
          <input
            id="ks-password"
            type="password"
            value={ksPassword}
            onChange={(event) => setKsPassword(event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="ks-confirm">Confirm</label>
          <input
            id="ks-confirm"
            type="password"
            value={ksConfirm}
            onChange={(event) => setKsConfirm(event.target.value)}
          />
        </div>
        <button type="button" onClick={createAccount} disabled={ksBusy || !ksPassword}>
          {ksBusy ? "Encrypting…" : "Create and download"}
        </button>
        {ksError ? <p className="error">{ksError}</p> : null}
        {created ? (
          <div>
            <p className="hint">
              Downloaded <span className="mono">{created.filename}</span>. Fund this
              account with REV before it can submit deploys.
            </p>
            <p className="mono">REV {created.revAddress}</p>
            <p className="mono">ETH {created.ethAddress}</p>
          </div>
        ) : null}
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
