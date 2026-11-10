# Roadmap

Status as of 2026-11-10. "Done when" reflects what a named suite actually ran; the full
gap list is in [Current limitations](limitations.md), and the evidence is in
[Testing and verification](testing.md).

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Repo, scaffold, specs, node issue | Done: the repository builds; [issue #563](https://github.com/rhovision-org/rholo/issues/563) is open |
| 1 | rholo bridge contract + devnet | **Demo passes:** a single Bridge contract + Guard/Ledger installed on a local devnet; 30 checks cover mint, burn, transfer, replay, threshold refusal, unknown asset, pause, the treasury fee sweep and conservation. The BridgeRoot/WrappedToken split is the production target, not done. |
| 2 | Native contracts | **EVM vault tested (10 Foundry tests incl. 2-of-3 refund); ETH and ERC-20 USDT ↔ rholo e2e pass on Anvil; failed deposits are journaled and refunded. Agoric Zoe vat tested locally. Profile-driven deployment, read-back, manifests and verification pass 23 checks on Anvil.** Next: a funded Sepolia run; a TronWeb/Nile deployment and TVM tests; live Agoric/IBC denoms and a watcher. |
| 3 | Relayer implementation | **Dev watcher loop passes: Anvil deposit → rholo mint and rholo burn → Anvil unlock + complete, 2-of-3. Safe-head gate, block-hash journal and reorg halt/rewind pass `make reorg-demo`; `/metrics`, `/health`, `/v1/chains` and journal reads pass.** Next: the production rail (standalone bridge node vs node add-on), packaging, bond/slashing, fee distribution and a testnet finality run. |
| 4 | Web dApp | **Live rholo/vault reads, MetaMask ETH/USDT locks, TronLink TRX/TRC-20 deposits, relayer deposit/withdrawal tracking, WASM-signed burn and the Web3 v3 keystore (device + encrypted browser copies, MetaMask key mapping); 46 unit + 9 Playwright + 5 opt-in live tests pass.** Next: Keplr/Agoric writes, Tron withdrawals, a MetaMask Snap. |
| 5 | Hardening | Public testnets, fee/bond/cap tuning, external audit, incident runbooks, OCapN production path |
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
- Testnets: a funded Sepolia key, a Tron node or Nile RPC, and an Agoric devnet account
  for the phase-5 runs.
