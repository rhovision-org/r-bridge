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
- **MetaMask ERC-20 approve+lock** for USDT: reads the token decimals and the vault's
  per-asset cap/scale, approves the vault for exactly the deposit amount when the
  allowance is short, waits for the approval receipt, then calls `lock`.
- **rholo keystore create/import/load** on Settings and Bridge: a Web3 v3 file (scrypt +
  AES-128-CTR, the same format r-wallet and MetaMask use) is decrypted in WASM; the
  decrypted key stays in memory for the operation. Settings can create an account,
  encrypt an existing key (for example one exported from MetaMask), load a file from
  disk, download any saved copy, and keep an encrypted copy in the browser. Import also
  accepts geth PBKDF2 files.
- **MetaMask ↔ rholo address mapping**: the Bridge derives the REV address from the
  connected MetaMask account and offers it as the deposit recipient. The same secp256k1
  key addresses both chains; to sign rholo deploys, export the key from MetaMask and
  encrypt it in Settings (MetaMask itself cannot sign the rholo deploy preimage).
- **TronLink TRX/TRC-20 deposits**: builds `approve` + `lock` against the configured TVM
  vault, derives the rholo address from the Tron account (the same 20-byte key payload),
  and reads TRX/USDT balances in the portfolio. The demo relayer watches Anvil only, so a
  Tron deposit is not minted here yet; a production rail must watch the TVM vault.
- **WASM-signed rholo burn** for the withdraw direction: either the imported keystore or
  the dev secret signs the deploy in the browser, and the relayer unlocks on Anvil.
- **Portfolio** polls every 5 seconds, so a lock that the relayer mints appears as a
  wrapped balance. The Overview shows native ETH and USDT balances for the connected
  MetaMask account and the vault's per-asset locked/fee totals.

Not wired in the UI yet: Tron withdrawals (the unlock watcher and TVM destination
handling), Keplr writes, and a MetaMask Snap for signing rholo deploys inside MetaMask
(today the key is exported and encrypted here). Saved keystore copies live in
`localStorage` as ciphertext; the password is entered per signing operation. The dev
secret input is for the devnet only. USDC/DAI remain read-only until those tokens are
added to a vault deployment.

The web build runs `wasm-pack` in `predev`/`pretypecheck`/`prebuild`/`pretest`; it needs
the Rust toolchain with the `wasm32-unknown-unknown` target and `wasm-pack`.

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
| USDT token | `.devnet/evm.json` → `token` |
| Tron vault | a Nile/TVM deployment manifest (base58); optional for the demo |
| TRC-20 USDT | a Nile test token or the mainnet contract; required to test Tron USDT |
| rholo address | `.devnet/demo-keys.json` → `deployer.rev_address` |
| Anvil RPC | `http://127.0.0.1:8545` |

Connect MetaMask on the Bridge page (it offers to add the Anvil network), lock 0.1 ETH,
and watch the Overview wrapped balance after the relayer mints. To lock USDT, set the
token address in Settings first; the button becomes "Approve and lock" and asks for two
MetaMask confirmations. `make e2e-evm` mints the mock USDT to Anvil account 0, which
MetaMask uses by default, so there is a balance to test with.

For withdraw, pick a keystore saved in the browser, load one from disk, or paste the
devnet deployer secret; enter its password and burn. The signer must match the configured
rholo address. Enter a 0x destination; the relayer unlocks on Anvil. To make a keystore,
use **Settings → Create a rholo keystore**; to use a MetaMask key, use **Settings → Use a
MetaMask key for rholo**. Both download a v3 file (also importable into r-wallet and
MetaMask) and can keep an encrypted copy in this browser. A newly created account needs
REV before it can submit deploys. The devnet key is throwaway; never use it with real
value.

## Tests

```bash
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run build
```

## Browser tests

```bash
npm --prefix web exec -- playwright install chromium   # once
make web-e2e                                          # or npm --prefix web run test:e2e
```

Playwright starts its own Anvil on `:8546`, deploys the vault and mock USDT with
`forge`, mints 2 USDT to Anvil account 0, serves the app on `:4173`, and injects a
MetaMask-shaped EIP-1193 provider backed by that account, and a TronLink/TronWeb stub.
The specs cover the ETH lock, the USDT approve+lock, the TronLink TRC-20 approve+lock,
the client-side cap refusal and keystore create/download/import. They do not need the
rholo devnet because they stop before mint/burn. Requires Foundry; the CI `e2e` job
installs Chromium and runs it.

Live reads are opt-in:

```bash
RBRIDGE_LIVE=1 \
RBRIDGE_URI=$(jq -r .uri .devnet/bridge.json) \
RBRIDGE_OWNER=$(jq -r .deployer.rev_address .devnet/demo-keys.json) \
RBRIDGE_VAULT=$(jq -r .vault .devnet/evm.json) \
RBRIDGE_USDT=$(jq -r .token .devnet/evm.json) \
npm --prefix web run test
```

The keystore tests are not gated: they load the built WASM, create an account, unlock it,
and check the wrong-password path (scrypt runs in the test, about a second). The EVM live
tests include an approve+lock against Anvil. They inject a MetaMask-shaped EIP-1193
provider backed by an unlocked Anvil account, so the browser code path runs unchanged in
Node. The rholo live tests need `make devnet-up` (they skip when the bridge URI or node
is absent); to run only the EVM cases:

```bash
RBRIDGE_LIVE=1 RBRIDGE_VAULT=… RBRIDGE_USDT=… \
npm --prefix web exec vitest run --root web src/lib/evm.live.test.ts
```
