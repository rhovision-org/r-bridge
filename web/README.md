# r-bridge web

React 18 + Vite + TypeScript. The app is a bridge dApp, not a wallet: MetaMask owns the
Ethereum account, TronLink/Keplr own their chains, and the rholo signer is a separate
module (next phase).

## What is live

- **rholo reads** via the node's exploratory deploy: bridge config and per-asset
  balances for the configured rholo address. No key or phlo is needed.
- **Anvil vault reads** via the configured RPC: locked balance, fees, pause state and
  the ETH asset config.
- **MetaMask ETH lock** against the configured vault: adds/switches to the Anvil
  network, then calls `lock` with the amount and rholo recipient.
- **Portfolio** polls every 5 seconds, so a lock that the relayer mints appears as a
  wrapped balance.

Not wired in the UI yet: ERC-20 approves/locks, the rholo burn/withdraw direction, and
the WASM rholo keystore. The harness/relayer covers those paths today.

## Run the demo

```bash
# repo root, terminal 1
make devnet-up && make demo          # rholo + bridge; writes .devnet/bridge.json
make e2e-evm                         # Anvil + vault; writes .devnet/evm.json
make relayer-watch                   # terminal 2

# terminal 3
npm --prefix web install
npm --prefix web run dev
```

Set these in the app's Settings (values come from `.devnet/`):

| Setting | Source |
|---|---|
| rholo node | `http://localhost:40403` |
| Bridge URI | `.devnet/bridge.json` → `uri` |
| Anvil vault | `.devnet/evm.json` → `vault` |
| rholo address | `.devnet/demo-keys.json` → `deployer.rev_address` |
| Anvil RPC | `http://127.0.0.1:8545` |

Connect MetaMask on the Bridge page (it offers to add the Anvil network), lock 0.1 ETH,
and watch the Overview wrapped balance after the relayer mints. The devnet key is
throwaway; never use it with real value.

## Tests

```bash
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run build
```

Live reads are opt-in:

```bash
RBRIDGE_LIVE=1 \
RBRIDGE_URI=$(jq -r .uri .devnet/bridge.json) \
RBRIDGE_OWNER=$(jq -r .deployer.rev_address .devnet/demo-keys.json) \
RBRIDGE_VAULT=$(jq -r .vault .devnet/evm.json) \
npm --prefix web run test
```
