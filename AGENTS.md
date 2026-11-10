# r-bridge operating notes

Authority order: `spec/` and `contracts/` > `docs/` > this file.

## What this repository is

- A bridge dApp and reusable primitives. **Not a wallet.**
- Native accounts belong to MetaMask (Ethereum), TronLink (Tron) and Keplr
  (Cosmos/Agoric). Never add native-chain key management here.
- The only key this repo manages is the **rholo** account in `rbridge-wasm`, because the
  node's deploy signing is not something the wallets can do.
- The relayer rail is **undecided**: it may be a standalone relayer/bridge node or a
  rholo node plugin/sidecar ([issue #563](https://github.com/rhovision-org/rholo/issues/563)).
  Keep r-bridge rail-agnostic: the attestation format, contracts, dApp and CLI must not
  assume either shape. This repo ships only a development mock relayer in `harness/`;
  it must never be presented as production.

## Platform rules

- **One state cell per object.** Consume first, validate, repost exactly once.
- **No `select`.** The node desugars it into parallel receives.
- **Deploy cap is 64 KiB inclusive; budget 56 KiB per term.** Measure after every change.
- **Deploys are atomic; blocks are sequential.** Repost before an external await.
- **No timers.** Use block heights; `rho:block:data`'s timestamp is the proposer's clock.
- **Finality.** Require finalized + `ProcessedWithSuccess` + `(true, …)`. Never retry a
  value-moving deploy under a new op id unless the first had no effect.
- **Amounts on rholo are `i64` base units.** Scale 18-decimal assets to 8 decimals at the
  boundary; reject or refund dust, never mint it.
- **ERTP has no burn arm.** The bridge ledger is the wrapped-asset authority; an ERTP
  adapter is a later, additive path.
- **rholo signatures** for attestations are secp256k1 **DER low-S over a 32-byte
  keccak256 digest**, verified by `rho:crypto:secp256k1Verify`. EVM/Tron verify the same
  signature as `(r,s,v)`.
- **Use pinned crates.** `rcash-*` at `49b441d…`, `rchain-crypto` at `841cb84…`; do not
  reimplement deploy encoding, signing or node HTTP.

## Rules for changes

- Every mutating bridge arm checks idempotency first and returns the prior result without a
  second effect.
- Every value-moving arm has a conservation assertion and a refusal test.
- Do not claim a behavioural result unless the named suite actually ran. "Implemented"
  means source plus static/parser gates, never behavioural verification.
- Do not modify r-cash or rholo from this repository; pin and depend.
- No secrets, keys or generated deployment manifests in git.

## Commands

```
make fmt clippy test wasm     # Rust gates
make build-contracts          # inline libs; writes contracts/rholo/build
make contracts-check          # drift + 56 KiB budget
make agoric-install agoric-test  # Agoric Zoe vat tests
make web-check                # wasm + npm typecheck + vitest + build
make web-e2e                  # Playwright browser tests (own Anvil on :8546)
make docs-check               # mdBook build
make check                    # all of the above

make devnet-up                # local rholo devnet (Docker, RHOLO_DIR)
make demo                     # Phase 1 end-to-end demo (devnet only)
make mock-relayer             # dev-only HTTP relayer surface on :8099
make relayer-watch            # dev watcher loop (Anvil -> rholo, rholo -> Anvil)
make refund-failed            # 2-of-3 admin refund of failed deposits
make reorg-demo               # safe-head/reorg journal test on its own Anvil
make metrics-demo             # /metrics, /health, /v1/chains on :9110
```

## Status labels

- **Scaffold** — types, specs, wiring; no deployed contracts.
- **Implemented** — source plus static/parser gates.
- **Tested** — a named suite passed on a named devnet/testnet.
