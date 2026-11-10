import { useState } from "react";
import { loadConfig, saveConfig, type AppConfig } from "../lib/config";
import {
  createKeystore,
  keystoreAddress,
  keystoreFilename,
  keystoreFromSecret,
} from "../lib/keystore";
import {
  downloadKeystore,
  forgetKeystore,
  loadSavedKeystores,
  saveKeystore,
  type SavedKeystore,
} from "../lib/keystore-store";

interface CreatedAccount {
  revAddress: string;
  ethAddress: string;
  filename: string;
}

export default function Settings() {
  const [config, setConfig] = useState<AppConfig>(() => loadConfig());
  const [saved, setSaved] = useState(false);

  const [ksPassword, setKsPassword] = useState("");
  const [ksConfirm, setKsConfirm] = useState("");
  const [ksSaveBrowser, setKsSaveBrowser] = useState(false);
  const [ksBusy, setKsBusy] = useState(false);
  const [ksError, setKsError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreatedAccount | null>(null);

  const [importKey, setImportKey] = useState("");
  const [importPassword, setImportPassword] = useState("");
  const [importConfirm, setImportConfirm] = useState("");
  const [importSaveBrowser, setImportSaveBrowser] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [imported, setImported] = useState<CreatedAccount | null>(null);

  const [loadJson, setLoadJson] = useState("");
  const [loadAddress, setLoadAddress] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [savedKeystores, setSavedKeystores] = useState<SavedKeystore[]>(() =>
    loadSavedKeystores(),
  );
  const [storeMessage, setStoreMessage] = useState<string | null>(null);

  function refreshSaved() {
    setSavedKeystores(loadSavedKeystores());
  }

  function persist(json: string) {
    saveKeystore(json);
    refreshSaved();
    setStoreMessage("Saved an encrypted copy in this browser. The password is not stored.");
  }

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
      downloadKeystore(result.json, result.filename);
      if (ksSaveBrowser) persist(result.json);
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

  async function importAccount() {
    setImportError(null);
    setImported(null);
    if (importPassword !== importConfirm) {
      setImportError("Passwords do not match.");
      return;
    }
    setImportBusy(true);
    try {
      const result = await keystoreFromSecret(importKey, importPassword);
      downloadKeystore(result.json, result.filename);
      if (importSaveBrowser) persist(result.json);
      setImported({
        revAddress: result.revAddress,
        ethAddress: result.ethAddress,
        filename: result.filename,
      });
      setImportKey("");
      setImportPassword("");
      setImportConfirm("");
    } catch (caught) {
      setImportError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setImportBusy(false);
    }
  }

  async function loadFromDevice(file: File | undefined) {
    setLoadError(null);
    setLoadAddress(null);
    setLoadJson("");
    if (!file) return;
    if (file.size > 32 * 1024) {
      setLoadError("That file is too large to be a keystore.");
      return;
    }
    try {
      const text = await file.text();
      setLoadAddress(keystoreAddress(text));
      setLoadJson(text);
    } catch (caught) {
      setLoadError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  function saveLoaded() {
    if (!loadJson) return;
    persist(loadJson);
  }

  function forget(address: string) {
    forgetKeystore(address);
    refreshSaved();
    setStoreMessage("Removed the encrypted copy from this browser.");
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
          These settings are stored in this browser only. Native accounts remain in their
          wallets. The rholo keystore can be saved as an encrypted JSON file on your
          device and, optionally, as an encrypted copy in this browser; the plaintext key
          is never stored.
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
          A Web3 v3 keystore (scrypt + AES-128-CTR) for a new rholo account. Download it
          to your device and keep it with the password; optionally keep an encrypted copy
          in this browser. The file also opens in r-wallet and MetaMask.
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
        <div className="row">
          <label htmlFor="ks-save">Also keep an encrypted copy in this browser</label>
          <input
            id="ks-save"
            type="checkbox"
            checked={ksSaveBrowser}
            onChange={(event) => setKsSaveBrowser(event.target.checked)}
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

      <section className="card form">
        <h2>Use a MetaMask key for rholo</h2>
        <p className="muted">
          MetaMask and rholo both use secp256k1, so one key addresses an Ethereum account
          and a rholo account. Export the key in MetaMask (Account details → Show private
          key), paste it here, and r-bridge encrypts it into a rholo keystore. The key is
          then held by this app (encrypted with your password), so prefer a dedicated
          account rather than your main one.
        </p>
        <div className="row">
          <label htmlFor="import-key">Private key</label>
          <input
            id="import-key"
            type="password"
            autoComplete="off"
            placeholder="0x… (32-byte hex)"
            value={importKey}
            onChange={(event) => setImportKey(event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="import-password">Keystore password</label>
          <input
            id="import-password"
            type="password"
            value={importPassword}
            onChange={(event) => setImportPassword(event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="import-confirm">Confirm keystore password</label>
          <input
            id="import-confirm"
            type="password"
            value={importConfirm}
            onChange={(event) => setImportConfirm(event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="import-save">
            Also keep the imported key's encrypted copy in this browser
          </label>
          <input
            id="import-save"
            type="checkbox"
            checked={importSaveBrowser}
            onChange={(event) => setImportSaveBrowser(event.target.checked)}
          />
        </div>
        <button type="button" onClick={importAccount} disabled={importBusy || !importKey}>
          {importBusy ? "Encrypting…" : "Encrypt and download"}
        </button>
        {importError ? <p className="error">{importError}</p> : null}
        {imported ? (
          <div>
            <p className="hint">
              Encrypted into <span className="mono">{imported.filename}</span>. The same
              key is your MetaMask account and this rholo account.
            </p>
            <p className="mono">REV {imported.revAddress}</p>
            <p className="mono">ETH {imported.ethAddress}</p>
          </div>
        ) : null}
      </section>

      <section className="card form">
        <h2>Load a keystore from your device</h2>
        <div className="row">
          <label htmlFor="load-file">Keystore file</label>
          <input
            id="load-file"
            type="file"
            accept="application/json,.json"
            onChange={(event) => loadFromDevice(event.target.files?.[0])}
          />
        </div>
        {loadError ? <p className="error">{loadError}</p> : null}
        {loadAddress ? (
          <div>
            <p className="mono">ETH {loadAddress}</p>
            <button type="button" onClick={saveLoaded}>
              Save encrypted copy in this browser
            </button>
          </div>
        ) : null}
      </section>

      <section className="card">
        <h2>Saved in this browser</h2>
        {savedKeystores.length === 0 ? (
          <p className="muted">No encrypted keystore is stored here yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ethereum address</th>
                  <th>Saved</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {savedKeystores.map((item) => (
                  <tr key={item.address}>
                    <td className="mono">{item.address}</td>
                    <td className="muted">{new Date(item.savedAt).toLocaleString()}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() =>
                          downloadKeystore(
                            item.json,
                            keystoreFilename(item.address, new Date(item.savedAt)),
                          )
                        }
                      >
                        Download
                      </button>{" "}
                      <button type="button" onClick={() => forget(item.address)}>
                        Forget
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {storeMessage ? <p className="hint">{storeMessage}</p> : null}
        <p className="hint">
          Only the encrypted v3 JSON is stored, never the password or the private key.
          Anyone with this browser profile can try to crack it offline, so use a strong
          password and Forget copies you no longer need.
        </p>
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
