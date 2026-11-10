# Web dApp

`web/` is a React 18 + Vite + TypeScript application. It is a bridge dApp, not a wallet:
MetaMask owns the Ethereum account, TronLink owns the Tron account, Keplr owns the
Cosmos/Agoric account, and the rholo account is a Web3 v3 keystore decrypted in WASM.

## What the app does

| Area | Behaviour |
|---|---|
| Reads | rholo bridge config and per-asset balances through an exploratory deploy; Anvil/TVM vault status per asset over RPC; native balances through the wallets |
| Ethereum deposits | MetaMask ETH `lock`; ERC-20 `approve` + `lock` (reads token decimals and the vault cap/scale, approves exactly the amount, waits for the receipt) |
| Tron deposits | TronLink TRX/TRC-20 `approve` + `lock` against the configured TVM vault |
| rholo withdraw | WASM-signed `burn` with a saved/loaded keystore or a devnet secret; the destination is a lowercase `0x` address |
| Relayer tracking | After a lock, the app reads the deposit id from the receipt and follows `/v1/deposits/{id}`; after a burn it follows `/v1/withdrawals/{id}` and shows the native tx |
| Portfolio | Polls every 5 seconds; native and wrapped balances appear together |
| Settings | Node, bridge URI, vault, USDT token, Tron vault/USDT, relayer URL, rholo address, RPC |

Routes: **Overview** (portfolio, bridge config, relayer card), **Bridge** (deposit and
withdraw), **Settings** (configuration and keystore).

## Wallets

- **MetaMask** via EIP-1193. The app offers to add/switch to the configured network,
  requests signatures, and reads receipts.
- **TronLink** via injected TronWeb. Addresses are canonicalised to the 20-byte lowercase
  `0x` payload for digest purposes.
- **Keplr** is detected and can connect an Agoric account, but **no Agoric write path is
  wired**: there are no Zoe offers, IBC transfers or Agoric deposits in the UI.
- **MetaMask ↔ rholo mapping**: secp256k1 is shared, so the same key addresses a rholo
  account. The app derives the REV address from the connected MetaMask account and offers
  it as a deposit recipient. To sign rholo deploys, the user exports the key from MetaMask
  and encrypts it in Settings; MetaMask itself cannot sign the node's deploy preimage.

## rholo keystore

The only locally handled key is the rholo account. `rbridge-keystore` implements Web3
Secret Storage v3:

- scrypt `n=2^17, r=8, p=1`, AES-128-CTR, keccak MAC; PBKDF2 files are accepted on import.
- Create an account, import a private key (including a MetaMask key), or load a file from
  disk; download a copy; keep an encrypted copy in `localStorage` (`rbridge.keystores`).
- The password is never stored; the ciphertext is; decryption happens in WASM and the key
  lives in memory for the operation only.
- The format is portable to/from r-wallet and the r-gen/r-cash clients.

This is a demo path, not an audited custody product. See
[Keystore](reference/keystore.md).

## Settings

| Setting | Where it comes from in the demo |
|---|---|
| rholo node | `http://localhost:40403` |
| Bridge URI | `.devnet/bridge.json` → `uri` |
| Anvil vault | `.devnet/evm.json` → `vault` |
| USDT token | `.devnet/evm.json` → `token` |
| Tron vault | a TVM deployment manifest (base58); optional |
| TRC-20 USDT | the Nile test token or a mainnet address; required to test Tron USDT |
| Relayer URL | `http://127.0.0.1:8099` (mock) or the dev watcher's metrics port |
| rholo address | `.devnet/demo-keys.json` → `deployer.rev_address` |
| Anvil RPC | `http://127.0.0.1:8545` |

Nothing is baked in: every value is a user setting, and the app stores no keys in git.

## Deposit and withdrawal UX

1. Connect MetaMask (or TronLink) and pick an asset.
2. Enter an amount and, for a deposit, the rholo recipient — the app offers the connected
   account's mapped REV address.
3. Sign `lock` (and `approve` for ERC-20/TRC-20). The app waits for the receipt and
   extracts the deposit id from the `Deposit` event.
4. The relayer card and the deposit status line show waiting → minted, or the relayer's
   failed/unreachable reason.
5. For a withdrawal, unlock a keystore, enter the amount and a `0x` destination, and sign
   the `burn`. The relayer unlocks on the native chain; the app shows the native tx.

## Tests

| Suite | Count | Runs against |
|---|---|---|
| Vitest unit | 46 | pure logic, wallet stubs, relayer client |
| Opt-in live | 5 | the local devnet/Anvil when `RBRIDGE_LIVE=1` |
| Playwright | 9 | its own Anvil, injected MetaMask/TronLink stubs, routed relayer API |
| WASM smoke | 1 | signs and submits a burn through the wasm client in Node |

The Playwright withdrawal spec stubs the rholo node's HTTP API (`/api/v1/status`,
`/api/v1/deploy`, `/api/v1/deploy-status`); the WASM signer, the burn term and the relayer
polling are real. The other specs inject wallet-shaped providers backed by Anvil. See
`web/README.md` for commands.

## Not wired yet

- Keplr/Agoric writes (Zoe offers, IBC deposits) and Agoric withdrawals.
- Tron withdrawals: no TVM unlocker, watcher or destination flow.
- A MetaMask Snap for signing rholo deploys inside MetaMask.
- USDC/DAI deposits: the registry lists them, but no vault deployment includes them here;
  the app treats them as read-only.
- Native wallet UI. The app deliberately does not rebuild MetaMask, TronLink or Keplr.

These and the other gaps are consolidated in [Current limitations](limitations.md).
