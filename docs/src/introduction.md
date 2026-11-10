# Introduction

`r-bridge` moves assets between **rholo** and **Ethereum**, **Tron** and
**Cosmos/Agoric**, and shows the balance on both sides. It is a bridge dApp plus a set of
reusable Rust primitives — not a wallet. Native-chain accounts stay in MetaMask,
TronLink and Keplr; the only key this project manages is the rholo account, because the
node's deploy signature is not something those wallets can produce.

The bridge is federated: an m-of-n set of relayers watches each native chain, attests
deposits and withdrawals over a canonical digest, and submits the rholo mint or the native
unlock. The **rail** those relayers run on is not decided (standalone bridge node or a
rholo node add-on); everything in this repository is built to be rail-agnostic. See
[Infrastructure decision](infrastructure-decision.md) and
[Relayer](relayer.md).

## Status at a glance

Everything below was run on the date in the roadmap. "Tested" means a named suite passed
in this repository, not that a public network was used.

| Area | State (2026-11-10) | Evidence |
|---|---|---|
| rholo bridge contract | Tested on a local devnet | `make demo`: 30 checks |
| Ethereum/TVM vault | Tested on Anvil | 10 Foundry tests; `make e2e-evm` |
| Vault deployment tooling | Rehearsed on Anvil, not broadcast to a public testnet | `make deploy-demo`: 23 checks |
| Development relayer | Tested against Anvil and the devnet | watcher loop; `reorg-demo`, `metrics-demo`, `api-demo` |
| Web dApp | Tested with stubs and a local chain | 46 unit, 9 Playwright, 5 opt-in live tests |
| Agoric Zoe vat | Tested locally | vat test suite, no live chain |
| Tron | Source reuse and wallet deposits only | unit + Playwright tests; no deployment |
| External audit | Not started | mainnet is refused by the deployment tool |

Detailed evidence, including what each suite cannot prove, is in
[Testing and verification](testing.md). The consolidated gaps are in
[Current limitations](limitations.md).

## Safety gates

- **Nothing here moves real value.** Devnet and testnet keys are throwaway and are never
  worth anything. The harness generates keys under `.devnet/`, which is gitignored.
- **No mainnet before an external audit.** `tools/deploy_evm.py` refuses Ethereum and
  Tron mainnet chain ids outright; there is no override flag.
- **No production relayer in this repository.** `harness/` contains a development
  stand-in; the production implementation belongs to whichever rail is chosen.
- **Native keys are never imported into the bridge.** The dApp asks MetaMask, TronLink
  or Keplr to sign; it does not hold native-chain keys.

## Authority and reading order

`spec/` and `contracts/` are normative; this book explains and links them; `AGENTS.md`
holds operating notes for contributors. The five specs are included verbatim in the
[Reference](reference/attestation.md) section so the book can be read on its own, but the
files under `spec/` are the source of truth.

| If you are… | Start with |
|---|---|
| New to the project | This chapter, then [Architecture](architecture.md) |
| Reviewing the design | [Flows](flows.md), [Security model](security.md), [Current limitations](limitations.md) |
| Running a node or relayer | [Relayer](relayer.md), [Node operator guide](operator-guide.md) |
| Deploying contracts | [Deployment](deployment.md) |
| Using the dApp | [Web dApp](web-app.md) |
| Checking a claim | [Testing and verification](testing.md) |
