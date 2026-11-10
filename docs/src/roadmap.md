# Roadmap

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Repo, scaffold, specs, node issue | this repository builds; issue #563 is open |
| 1 | rholo bridge suite + devnet | BridgeRoot/WrappedToken/Bridge/Attestation deployed on a local rholo devnet; suites pass (mint, burn, transfer, replay, threshold refusal, caps, pause, conservation) |
| 2 | Native contracts | Ethereum vault on Sepolia, Tron vault on Nile, Agoric vat on a local chain with mocked IBC denoms; shared digest vectors pass on all three |
| 3 | Node relayer add-on | watchers/signers/submitters + journal + metrics; 2-of-3 local devnet, then testnets |
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
- Node add-on: [rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563).
- r-cash: pinned `rcash-chain`/`rcash-sdk` for deploy encoding, signing and HTTP.
- Wallets: MetaMask, TronLink, Keplr.
- Agoric: Zoe/ERTP, IBC denoms (Noble USDC), an Agoric testnet for phase 5.
