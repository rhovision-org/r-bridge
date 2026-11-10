# Roadmap

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Repo, scaffold, specs, node issue | this repository builds; issue #563 is open |
| 1 | rholo bridge contract + devnet | **Demo passes (2026-11-10):** a single Bridge contract + Guard/Ledger libs installed on a local devnet; 30 checks cover mint, burn, transfer, replay, threshold refusal, unknown asset, pause, the treasury fee sweep and conservation. The BridgeRoot/WrappedToken split is the production target, not yet done. |
| 2 | Native contracts | **Ethereum/TVM vault implemented (10 Foundry tests incl. 2-of-3 refund); ETH and ERC-20 USDT ↔ rholo e2e pass on Anvil + local devnet; failed deposits are journaled and refunded. Agoric Zoe escrow/release vat implemented and tested. Profile-driven deployment, on-chain read-back, manifests and verification pass 23 checks on Anvil (`make deploy-demo`).** No public-testnet deployment yet: Sepolia needs funded keys and the operator set; Nile needs a TronWeb pass; live Agoric/IBC denoms and an Agoric watcher are next. |
| 3 | Relayer implementation | **Dev watcher loop passes (2026-11-10): Anvil deposit → rholo mint and rholo burn → Anvil unlock + complete, 2-of-3. The safe-head gate, block-hash journal and reorg halt/rewind pass `make reorg-demo` on Anvil; the SDK/CLI read client consumes the interface.** The production rail (standalone bridge node vs node plugin/sidecar) is still undecided; packaging, bond/slashing and a testnet finality run are next. |
| 4 | Web dApp | **Reads, the ETH/USDT loop and the rholo keystore are live (2026-11-10): rholo bridge config/balances via exploratory deploy, Anvil vault status per asset via RPC, MetaMask ETH lock and ERC-20 approve+lock, Web3 v3 keystore create/import/load (r-wallet compatible, device + encrypted browser copies, MetaMask keys usable as rholo keys), TronLink TRX/TRC-20 deposits, relayer status with deposit and withdrawal tracking through the read API, and WASM-signed rholo burn, 5 s portfolio polling; 46 unit + 9 Playwright browser tests + 5 opt-in live tests and a wasm deploy smoke test pass.** Tron withdrawals/watcher and Keplr are next. |
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
