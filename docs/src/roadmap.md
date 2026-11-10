# Roadmap

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Repo, scaffold, specs, node issue | this repository builds; issue #563 is open |
| 1 | rholo bridge contract + devnet | **Demo passes (2026-11-10):** a single Bridge contract + Guard/Ledger libs installed on a local devnet; 22 checks cover mint, burn, transfer, replay, threshold refusal, unknown asset, pause and conservation. The BridgeRoot/WrappedToken split is the production target, not yet done. |
| 2 | Native contracts | **Ethereum/TVM vault implemented and 9 Foundry tests pass; EVM ↔ rholo cross-chain demo passes on Anvil + local devnet (lock → mint → burn → unlock).** Sepolia deployment, Tron/Nile TVM tests and the Agoric vat with mocked IBC denoms are next. |
| 3 | Relayer implementation | **Dev watcher loop passes (2026-11-10): Anvil deposit → rholo mint and rholo burn → Anvil unlock + complete, 2-of-3.** The production rail (standalone bridge node vs node plugin/sidecar) is still undecided; journal, metrics, reorg handling and packaging are next. |
| 4 | Web dApp | MetaMask/TronLink/Keplr integration, portfolio, bridge/withdraw, activity; Playwright e2e |
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
