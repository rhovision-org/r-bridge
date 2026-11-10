# Roadmap

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Repo, scaffold, specs, node issue | this repository builds; issue #563 is open |
| 1 | rholo bridge contract + devnet | **Demo passes (2026-11-10):** a single Bridge contract + Guard/Ledger libs installed on a local devnet; 22 checks cover mint, burn, transfer, replay, threshold refusal, unknown asset, pause and conservation. The BridgeRoot/WrappedToken split is the production target, not yet done. |
| 2 | Native contracts | **Ethereum/TVM vault implemented (10 Foundry tests incl. 2-of-3 refund); ETH and ERC-20 USDT ↔ rholo e2e pass on Anvil + local devnet; failed deposits are journaled and refunded. Agoric Zoe escrow/release vat implemented and tested.** Sepolia/Nile deployment, live Agoric/IBC denoms and a real Agoric watcher are next. |
| 3 | Relayer implementation | **Dev watcher loop passes (2026-11-10): Anvil deposit → rholo mint and rholo burn → Anvil unlock + complete, 2-of-3.** The production rail (standalone bridge node vs node plugin/sidecar) is still undecided; journal, metrics, reorg handling and packaging are next. |
| 4 | Web dApp | **Reads, the ETH/USDT loop and the rholo keystore are live (2026-11-10): rholo bridge config/balances via exploratory deploy, Anvil vault status per asset via RPC, MetaMask ETH lock and ERC-20 approve+lock, Web3 v3 keystore import/create (r-wallet compatible) and WASM-signed rholo burn, 5 s portfolio polling; 19 unit + 5 opt-in live tests and a wasm deploy smoke test pass.** TronLink/Keplr, keystore session persistence and Playwright e2e are next. |
| 5 | Hardening | public testnets, fee/bond/cap tuning, external audit, incident runbooks, OCapN production path |
| 6 | Expansion | Hyperliquid adapter/listing, Bitcoin adapter (P2WSH vault + PSBT) |

## Explicitly out of scope for v1

- A native-chain wallet UI or native key storage.
- A production relayer in this repository; it is the node add-on.
- Bitcoin (deferred) and Hyperliquid (future).
- Mainnet value before an external audit.

## Dependencies

- rholo node: `rho:crypto:secp256k1Verify`, `keccak256Hash`, ERTP, OCapN, finality API.
- Relayer rail: standalone bridge node vs rholo plugin/sidecar, decided after the demo;
  [rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563) is the
  node-side proposal.
- r-cash: pinned `rcash-chain`/`rcash-sdk` for deploy encoding, signing and HTTP.
- Wallets: MetaMask, TronLink, Keplr.
- Agoric: Zoe/ERTP, IBC denoms (Noble USDC), an Agoric testnet for phase 5.
