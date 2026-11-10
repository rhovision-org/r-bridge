# Current limitations

This chapter is the single consolidated list of what r-bridge does **not** do yet. It is
current as of 2026-11-10 and mirrors the evidence in [Testing and verification](testing.md)
and the plan in [Roadmap](roadmap.md). If a limitation is removed, update this chapter and
the README together.

**No external audit has been performed. No mainnet value may move.**

## Is it safe to use today?

| Use | Verdict |
|---|---|
| Reading the code, running the local devnet demo | Yes — keys are throwaway and worth nothing |
| Evaluating the dApp on Anvil with test wallets | Yes |
| A public testnet deployment with throwaway keys | Not performed yet; the tooling is ready for Sepolia once funded |
| Holding or moving real value | **No.** Unaudited, mainnet refused, no production relayer |

## Safety and operational gates

- **No external audit.** Contracts, keystore, relayer and deployment tooling are
  unaudited. Mainnet chain ids are refused by `tools/deploy_evm.py` with no override.
- **Devnet keys are throwaway.** The harness generates keys under `.devnet/`; they are
  public in development and must never hold value.
- **No production relayer in this repository.** `harness/` is a development stand-in. The
  production implementation waits on the rail decision.
- **Fixed fee and cap values.** The profiles and the demo use 5 bps and testnet caps;
  they are not calibrated against real volume.

## Bridge architecture not yet production

- **Single `Bridge` demo contract.** `contracts/rholo` is one state cell with Guard/Ledger
  libraries. The planned `BridgeRoot`/`WrappedToken`/`Bridge`/`Attestation` split is not
  implemented. The wire formats will not change when it is.
- **Fixed relayer and admin sets.** The deployed contract and vault have no on-chain set
  update. Rotating a key or admitting an operator means redeploying or using a new bridge
  id until a governance path is added.
- **No ERTP adapter.** The bridge ledger is the wrapped-asset authority; wrapped assets
  are not native ERTP purses. An adapter is a later, additive path.
- **No relayer fee distribution.** Fees accrue to a treasury fixed at deployment and can
  be swept (rholo) or withdrawn (vault). There is no per-epoch distribution to relayers.
- **No bond or slashing.** The relayer set is permissioned and trusted socially, not
  economically. A colluding majority can attest false flows.

## Relayer and trust

- **Rail undecided.** Standalone bridge node, rholo node add-on, or hybrid — see
  [Infrastructure decision](infrastructure-decision.md) and
  [rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563). The demo
  is rail-agnostic by design, so the work is not wasted either way, but no production
  packaging exists.
- **Dev relayer scope.** It settles Anvil deposits and rholo withdrawals with fixed keys.
  It has no HSM, no durable database, no multi-relayer coordination or conflict
  detection, and no authenticated API.
- **No Tron or Agoric settlement.** No watcher signs or submits for those rails.
- **Single-process assumptions.** The dev watcher assumes one operator holding all demo
  keys; it does not model independent relayers or key rotation.
- **Missing `rbridge_pending`.** The spec defines it; the dev watcher does not emit it.

## Chain coverage

- **Ethereum**: tested on Anvil only. No Sepolia deployment has been broadcast; no
  mainnet. The vault's relayer/admin sets are fixed at deploy.
- **Tron**: the vault source is reused but never compiled for TVM or deployed; there are
  no TVM tests, no Nile deployment, no Tron watcher and no Tron withdrawals. The dApp
  builds and signs TronLink deposits, but the demo relayer does not mint them.
- **Agoric/Cosmos**: the Zoe vat is tested locally. There is no live Agoric chain, no IBC
  denom setup, no Keplr write path, no Agoric watcher, no durable baggage stores and no
  account/key binding for the release invitation.
- **Hyperliquid** is a future adapter/listing venue. **Bitcoin** is deferred. Neither has
  code.

## Web dApp and keys

- **No Keplr writes.** Keplr can connect an Agoric account, but there are no Zoe offers or
  IBC transfers.
- **No MetaMask Snap.** rholo deploys need an exported key encrypted in this app;
  MetaMask cannot sign the node's deploy preimage directly.
- **No Tron withdrawals.** No destination flow and no TVM unlocker.
- **USDC/DAI are read-only** in practice: they are in the registry, but no deployment here
  includes them.
- **Keystore is demo-grade.** Web3 v3 with scrypt is interoperable and tested against
  fixtures, but unaudited; browser copies are ciphertext in `localStorage`.
- **No native wallet UI.** By design, but it means users need MetaMask/TronLink/Keplr
  installed.

## Finality and testnets

- **Single-validator devnet.** It can report `finalized: false` after
  `ProcessedWithSuccess` (rholo issue #356). The demo gates on the processed result.
- **Interactive defaults.** The dev watcher can run with `--confirmations 0`; a testnet or
  production run must use `--finalized` or a real confirmation depth.
- **No public-testnet run.** Sepolia is prepared but unfunded/unbroadcast; Nile needs a
  TronWeb deployment; Agoric needs a live chain and IST.
- **No multi-validator finality evidence.** The finality logic is exercised locally, not
  on a real validator set.

## Assets, fees and parameters

- **The asset registry is a plan, not a deployment.** `spec/assets.md` lists chains and
  assets; only Ethereum ETH and USDT are exercised end-to-end here. The Agoric USDT row is
  disabled pending a denom.
- **Asset coverage depends on vault deployment.** A wrapped symbol exists only once a
  native vault/vat for that asset is deployed and registered.
- **Fees and caps are testnet values.** 5/5 bps and the demo caps are illustrative; the
  economics chapter is a proposal.
- **No price oracle or fiat display.** Amounts are base units and symbols only.

## Platform limits

- **Deploy cap.** rholo rejects deploys over 64 KiB; the project budgets 56 KiB. The
  current term is about 15.5 KiB, leaving room but not unlimited growth.
- **Amount precision.** rholo amounts are `i64`; 18-decimal assets are scaled to 8
  decimals and non-multiple dust is refused, never rounded.
- **No proxy contracts.** The vault is immutable and has no external dependencies;
  upgrading means redeploying.

## What would change this

The roadmap phases and the decision gates in
[Infrastructure decision](infrastructure-decision.md) name the evidence needed: a
public-testnet run, a live Agoric watcher, multi-validator finality, production relayer
packaging with bond/slashing, and the external audit. Until then, treat every "tested"
claim as local to the named suite in [Testing and verification](testing.md).
