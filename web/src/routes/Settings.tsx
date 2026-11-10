import { useState } from "react";

const KEYS = {
  node: "rbridge.node",
  relayer: "rbridge.relayer",
  network: "rbridge.network",
} as const;

function read(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

export default function Settings() {
  const [node, setNode] = useState(() =>
    read(KEYS.node, import.meta.env.VITE_RBRIDGE_NODE ?? "http://localhost:40403"),
  );
  const [relayer, setRelayer] = useState(() =>
    read(KEYS.relayer, import.meta.env.VITE_RBRIDGE_RELAYER_URL ?? ""),
  );
  const [network, setNetwork] = useState(() =>
    read(KEYS.network, "rbridge-devnet"),
  );
  const [saved, setSaved] = useState(false);

  function save() {
    try {
      localStorage.setItem(KEYS.node, node);
      localStorage.setItem(KEYS.relayer, relayer);
      localStorage.setItem(KEYS.network, network);
      setSaved(true);
    } catch {
      setSaved(false);
    }
  }

  return (
    <div className="stack">
      <section>
        <h1>Settings</h1>
        <p className="muted">
          Stored in this browser only. No account keys are kept here; native
          accounts remain in their wallets.
        </p>
      </section>

      <section className="card form">
        <div className="row">
          <label htmlFor="node">rholo node</label>
          <input
            id="node"
            value={node}
            onChange={(event) => setNode(event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="relayer">Relayer add-on URL</label>
          <input
            id="relayer"
            placeholder="https://relayer.example"
            value={relayer}
            onChange={(event) => setRelayer(event.target.value)}
          />
        </div>
        <div className="row">
          <label htmlFor="network">Network id</label>
          <input
            id="network"
            value={network}
            onChange={(event) => setNetwork(event.target.value)}
          />
        </div>
        <button type="button" onClick={save}>
          Save
        </button>
        {saved ? <p className="hint">Saved in this browser.</p> : null}
      </section>

      <section className="card">
        <h2>Not configured yet</h2>
        <ul>
          <li>Bridge root URI and wrapped-token URIs.</li>
          <li>Ethereum/Tron vault addresses and the Agoric vat instance.</li>
          <li>Relayer pubkey set and threshold.</li>
        </ul>
      </section>
    </div>
  );
}
