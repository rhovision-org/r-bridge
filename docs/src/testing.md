# Testing and verification

A claim of "tested" in this book means a named suite in this repository passed. It does not
mean a public network was used or that an auditor reviewed the code. This chapter lists
every suite, what it proves, and what it cannot prove.

## Suites

| Suite | Command | Proves | Does not prove |
|---|---|---|---|
| Rust workspace | `cargo test --workspace` | digest/amount/id logic, relayer client (both chain response shapes, 404-to-null, path-safe ids), keystore interop, chain seam | On-chain behaviour |
| Contract build | `make contracts-check` | generated deploy terms match the sources; 56 KiB budget; no drift | Semantics |
| rholo demo | `make demo` (30 checks) | install, config, asset lookup, 2-of-3 mint, replay refusal, below-threshold refusal, unknown asset, burn, withdrawal completion, transfer, pause/unpause, admin nonce replay, treasury fee sweep, conservation | Multi-validator finality; native chains |
| Foundry | `make evm-test` (10 tests) | vault lock/unlock, 18→8 scaling, fees, refund, threshold/duplicate-signer/wrong-digest refusals, pause semantics, admin replay, shared Rust/EVM digest golden vector | Any real chain; TVM compilation |
| Cross-chain e2e | `make e2e-evm` | ETH and USDT lock → 2-of-3 attestation → rholo mint → burn → 65-byte signatures → Anvil unlock → completion, with fee and scale accounting | Sepolia, Tron, Agoric; decentralized relayers |
| Deployment rehearsal | `make deploy-demo` (23 checks) | profile deploy, chain read-back, manifest write/verify/tamper detection, ERC-20 code/decimals checks, mainnet and non-local refusals, missing-env refusal, `print-env` | A public-testnet deployment |
| Reorg demo | `make reorg-demo` | safe-head cursor rewind on an unprocessed reorg; halt when a settled deposit is reorged out | A deep real-chain reorg |
| Metrics demo | `make metrics-demo` | `/metrics`, `/health`, `/v1/chains`, including while halted | Production monitoring |
| API demo | `make api-demo` | journaled deposit state/message, 404 paths, health stays up | Authenticated or multi-relayer API |
| Agoric vat | `make agoric-test` | Zoe escrow, 2-of-3 release, replay, below-threshold and wrong-digest refusals | A live Agoric chain, IBC, durable stores |
| Web unit | `npm --prefix web run test` (46 tests) | wallet stubs, relayer client, keystore store, EVM/Tron builders, scaling and refusal logic | A browser or real wallets |
| Web browser | `make web-e2e` (9 specs) | ETH lock, USDT approve+lock, TronLink TRC-20 lock, relayer card, cap refusal, keystore create/download/import, WASM-signed withdrawal with relayer follow-through | A real node or real extensions; the node API is stubbed in the withdrawal spec |
| Web live | `RBRIDGE_LIVE=1 npm --prefix web run test` (5 tests) | reads against the devnet/Anvil, MetaMask-shaped approve+lock on Anvil | Browser extensions |
| WASM smoke | Node script that calls `init(wasmBytes)` and submits a burn | the wasm client signs and submits a real deploy shape | A full UI path |
| Docs | `make docs-check` | book links/includes/orphans resolve; mdBook builds | Content correctness |

`make check` runs the Rust gates, contract build check, Foundry tests, the deployment
rehearsal, the web checks and the docs build. It does **not** run `agoric-test` or
`web-e2e`; those have their own targets and CI jobs.

## What the demos actually exercise

- **Real cryptography.** The rholo demo and the cross-chain demo use the Rust signer and
  the on-chain verifier. The withdrawal digest has a shared golden vector
  (`d2f0ca02…e805`) between Rust and Solidity.
- **Real installs.** The rholo contract is rendered, measured and installed on a local
  node; the vault is deployed to Anvil by Forge. These are not mocks.
- **Conservation and refusals.** Every value-moving arm has a refusal test and a
  conservation check; the fee sweep asserts that circulating plus fees is unchanged.
- **Idempotency.** Replayed deposits, admin nonces and withdrawal ids are refused with the
  prior result, and the tests assert no second effect.
- **Honest stubs.** The Playwright withdrawal spec stubs the node's HTTP API because
  starting a rholo cluster per browser test is impractical; the WASM signing, burn term
  and relayer polling are real. The EVM/TRON providers are wallet-shaped stubs over a
  local chain, not the browser extensions.

## CI map

| Job | Runs |
|---|---|
| `rust` | fmt, clippy, workspace tests, wasm32 check, contract drift/budget |
| `evm` | Foundry tests, deployment rehearsal, reorg demo, metrics demo, API demo |
| `agoric` | `npm ci` and the vat tests |
| `web` | wasm build, typecheck, Vitest, production build |
| `e2e` | Playwright with its own Anvil and injected providers |
| `docs` | documentation checker and mdBook build |

## Running everything locally

```bash
make check          # rust, contracts, evm, deployment, web, docs
make agoric-test    # separate
make web-e2e        # separate; Playwright
```

The devnet and cross-chain demos need Docker and a local rholo checkout
(`RHOLO_DIR`, default `../RNodeRust`) plus Foundry. The deployment rehearsal needs only
Foundry; it starts its own Anvil on :8547. Playwright starts its own Anvil on :8546.

## What remains unverified

Public testnets, multi-validator finality, Tron/TVM, a live Agoric chain, production
relayer packaging, bond/slashing and the external audit. These are the evidence gaps listed
in [Current limitations](limitations.md) and the gates in
[Infrastructure decision](infrastructure-decision.md).
