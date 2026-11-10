# r-bridge

`r-bridge` is a bridge application and reusable primitive set for **rholo**. It moves
assets between rholo and Cosmos/Agoric, Ethereum and Tron, and shows balances on both
sides. It is not a wallet: native accounts stay in MetaMask, TronLink and Keplr.

| Question | Answer |
|---|---|
| **What is it?** | A bridge dApp + Rust primitives for rholo. |
| **Which chains?** | Cosmos/Agoric, Ethereum, Tron first; Hyperliquid later. Bitcoin is deferred. |
| **Which assets?** | Native assets plus USDT/USDC/DAI where each chain has them, chain-qualified. |
| **What is the trust model?** | Federated m-of-n relayers (2-of-3 to start). The rail they run on is undecided. |
| **What does it depend on?** | A relayer layer: standalone bridge node or rholo plugin/sidecar — undecided ([issue #563](https://github.com/rhovision-org/rholo/issues/563)). |
| **Status** | **Phase 1 demo and Phase 2 EVM ↔ rholo cross-chain demo pass on a local rholo devnet + Anvil; the Ethereum/TVM vault passes 10 Foundry tests, and profile-driven deployment + manifest verification pass 23 checks on Anvil.** No public-testnet or mainnet deployment yet; see [Current limitations](docs/src/limitations.md). **No real value moves.** |

## Documentation

The [mdBook](docs/src/SUMMARY.md) is the detailed reference; `spec/` is normative. Build
or serve it locally with `cd docs && mdbook serve`.

| Chapter | Covers |
|---|---|
| [Introduction](docs/src/introduction.md) | scope, status at a glance, safety gates |
| [Architecture](docs/src/architecture.md) | components, identities, current vs planned contracts |
| [Flows](docs/src/flows.md) | deposit, withdraw, refund, admin, failure paths |
| [Security model](docs/src/security.md) | assumptions, threats, key separation, audit scope |
| [Relayer](docs/src/relayer.md) | dev watcher, read API, metrics, dev-vs-production gaps |
| [Node operator guide](docs/src/operator-guide.md) | hardware, economics, keys, incident runbook |
| [Web dApp](docs/src/web-app.md) | wallets, keystore, settings, flows, web limitations |
| [Deployment](docs/src/deployment.md) | rholo install, profiles, manifests, Sepolia runbook |
| [Testing and verification](docs/src/testing.md) | every suite, what it proves, what it does not |
| [Current limitations](docs/src/limitations.md) | the consolidated, grouped gap list |
| [Roadmap](docs/src/roadmap.md) and [infrastructure decision](docs/src/infrastructure-decision.md) | phases and the open relayer-rail choice |

## Wallets

r-bridge uses what the user already has:

- **MetaMask** for Ethereum accounts, network switching, approvals and vault calls. The
  same secp256k1 key addresses a rholo account: the Bridge derives the REV address from
  the connected account, and a key exported from MetaMask can be encrypted into a rholo
  keystore (Settings) so it signs deploys too.
- **TronLink** for Tron accounts and TRC-20 calls.
- **Keplr** for Cosmos/Agoric accounts. Account connection exists; Zoe/IBC writes are
  not wired yet.
- **r-bridge's own WASM keystore** only for the rholo account, because MetaMask cannot
  sign the node's deploy preimage (BLAKE2b-256 protobuf, `shardId` field 11,
  `{prehash:false}`). It is a Web3 v3 file (scrypt + AES-128-CTR) that opens in
  r-wallet; the browser decrypts it in WASM and keeps the key in memory for the
  operation.

## Infrastructure decision pending — demo first

A bridge needs a relayer layer to watch foreign chains, attest deposits, submit rholo
mints and broadcast native unlocks. **The rails are not decided.** Two shapes are on the
table:

1. a **standalone relayer/bridge node** repo, run independently of rholo validators; or
2. a **plugin/sidecar for the rholo node**, run by node operators.

The final product depends on that decision. In the meantime we are building a **demo**
that is deliberately rail-agnostic: the attestation format, bridge contracts, dApp and
CLI do not assume which rail wins. A mock relayer stands in for the real one. The demo,
and the discussion in
[rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563), will inform
the choice. See [Infrastructure decision](docs/src/infrastructure-decision.md).

## Repository map

| Area | Path |
|---|---|
| Rust primitives | `crates/rbridge-{core,chain,sdk,cli,keystore,wasm}` |
| Web dApp | `web/` |
| Rholang bridge contract (demo) | `contracts/rholo/` |
| Ethereum/TVM vault | `contracts/evm/` (Tron reuse in `contracts/tron/`) |
| Agoric escrow vat (Zoe) | `contracts/agoric/` |
| Dev harness, mock and watcher | `harness/` |
| Specs | `spec/` |
| Book | `docs/` |
| Network configs | `configs/` |
| Generated deployment manifests | `deployments/` |

## Quick start

```bash
cargo test --workspace
cargo check -p rbridge-wasm --target wasm32-unknown-unknown
npm --prefix web install
npm --prefix web run dev
(cd docs && mdbook serve)
```

`make check` runs the Rust, contract, deployment, web and docs gates.

## Run the Phase 1 demo

Prereqs: Docker, a local rholo checkout at `~/RNodeRust` (override with
`RHOLO_DIR=...`), and the Rust toolchain. The EVM vault tests also need Foundry; the
Makefile expects it at `~/.foundry/bin/forge` (override with `FORGE=...`).

```bash
make devnet-up    # starts a 1-validator local devnet (8 GB node memory) on :40403
make demo         # installs the bridge, runs 30 checks, exits PASS/FAIL
make devnet-down
```

The demo installs the rholo bridge contract, signs a deposit attestation with 2 of 3
dev relayer keys, mints, replays the same deposit (refused), tries below-threshold
(refused), burns, completes the withdrawal, transfers, pauses/unpauses via 2-of-3 admin
signatures, sweeps the accrued deposit fees to the treasury via a 2-of-3 admin action,
and checks conservation. It is devnet-only; keys are generated in
`.devnet/` and are worth nothing.

`make mock-relayer` starts the dev-only HTTP relayer surface from
`spec/relayer-interface.md` on `127.0.0.1:8099` after `make demo` has created the keys.

## Run the cross-chain demo (EVM ↔ rholo)

With the rholo devnet and bridge from above still running, start Anvil in another
terminal and run the harness:

```bash
~/.foundry/bin/anvil &     # local EVM on :8545
make e2e-evm               # lock -> attest -> mint -> burn -> 65-byte sigs -> unlock
```

It deploys the vault to Anvil, locks 0.1 ETH, mints 9,995,000 wrapped units on rholo
after a 2-of-3 attestation, burns 0.05 ETH worth, and unlocks 49,975,000,000,000,000 wei
(0.049975 ETH after fee) to an Anvil account. This is the evidence the relayer-rail
decision needs: the harness performs the watcher/attester/submitter steps manually.

To run those steps automatically, start the dev watcher instead of using the manual
script:

```bash
make relayer-watch         # watches Anvil deposits and rholo withdrawals
# in another shell, lock or burn through the harness/dApp
```

The watcher starts at the current Anvil block and ignores withdrawals that were already
pending when it started, so it only settles new work. It only settles below a safe head
(`--confirmations N`, or `--finalized` to follow the finalized tag) and journals block
hashes: a reorg rolls the cursor back, and a reorg that removes a settled deposit halts
it for reconciliation. `make reorg-demo` proves both paths on Anvil. It is still a dev
loop (fixed keys, ETH-only, no bond/slashing); the production rail is undecided.

## Run the web demo

With the devnet, bridge, Anvil vault and relayer from above still running:

```bash
npm --prefix web install
npm --prefix web run dev
```

In Settings, set the node, bridge URI (`.devnet/bridge.json`), vault
(`.devnet/evm.json`), rholo address (`.devnet/demo-keys.json` → `deployer.rev_address`)
and Anvil RPC. The Overview reads the live bridge config, per-asset balances and vault
status. On Bridge, connect MetaMask, let it add the Anvil network, and lock ETH or USDT
(the ERC-20 path approves the vault first); the relayer mints and the wrapped balance
appears in the portfolio. For withdraw, paste the devnet deployer secret into the
in-memory signer field, enter a 0x destination, and burn; the relayer unlocks on Anvil.

Live reads are tested against the devnet with `RBRIDGE_LIVE=1`; see `web/README.md`.

## Deploy a native vault

`tools/deploy_evm.py` deploys `BridgeVault` from a profile in `configs/networks/`, checks
the chain id and every ERC-20's code and decimals first, reads the deployed configuration
back from the chain, and writes a gitignored manifest to `deployments/`. `verify`
re-checks that manifest against the chain; `print-env` emits the web app's settings.

```bash
make deploy-demo        # rehearses deploy + verify + refusals on its own Anvil (:8547)
make deploy-sepolia     # SEPOLIA_* env from docs/src/deployment.md; --yes included
RBRIDGE_RPC_URL="$SEPOLIA_RPC_URL" make verify-sepolia
```

Mainnet is refused until the external audit, and no public-testnet deployment has been
performed yet. See [Deployment](docs/src/deployment.md).

## Read the relayer

The SDK exposes the rail-agnostic read API (`RelayerClient`) and the CLI wraps it. With
`make mock-relayer` running on `:8099`:

```bash
cargo run -p rbridge-cli -- relayer health
cargo run -p rbridge-cli -- relayer chains
cargo run -p rbridge-cli -- relayer deposit --id <deposit-id>
cargo run -p rbridge-cli -- relayer attestation --id <deposit-id>
```

`--url` (or `RBRIDGE_RELAYER`) points at the dev watcher instead (its `--metrics-port`,
for example `http://127.0.0.1:9110`). The client accepts the mock's bare chain names and
the watcher's per-chain objects; a 404 becomes `null`, so "not attested yet" is
distinguishable from an error.

## Current status

Evidence as of 2026-11-10. Every count below is a named suite; the full table, including
what each suite cannot prove, is in
[Testing and verification](docs/src/testing.md).

- Phase 1 rholo demo: PASS, 30 checks (mint, replay, below-threshold, burn, withdrawal,
  transfer, pause, treasury fee sweep, conservation).
- Phase 2 EVM vault: 10 Foundry tests pass; ETH and ERC-20 USDT ↔ rholo e2e PASS on
  Anvil + local devnet; failed deposits are journaled and refunded.
- Phase 2 deployment: `make deploy-demo` passes 23 checks on its own Anvil. Sepolia is
  prepared but not deployed.
- Dev relayer loop: PASS — deposit watcher mints, withdrawal watcher unlocks and
  completes; safe-head/reorg handling passes `make reorg-demo`; `/metrics`, `/health`,
  `/v1/chains` and the journal reads pass `metrics-demo` and `api-demo`.
- Web dApp: 46 unit + 9 Playwright + 5 opt-in live tests pass; MetaMask and TronLink
  deposits, relayer tracking, WASM-signed burn and the Web3 v3 keystore are wired.
- Agoric vat: Zoe escrow/release passes deposit, 2-of-3 release, replay,
  below-threshold and wrong-digest tests. No live chain.

The devnet is a single validator, which can report `finalized: false` even after
`ProcessedWithSuccess` (rholo issue #356). The demo uses the processed result as its
gate; testnet/production must additionally require finality.

## Current limitations

This is a summary; the consolidated, grouped list with "what unblocks it" is
[Current limitations](docs/src/limitations.md). Nothing here moves real value.

**Safety gates.** No external audit has been performed, and `tools/deploy_evm.py`
refuses mainnet chain ids with no override. Devnet keys are throwaway. There is no
production relayer in this repository.

**Architecture.** The rholo side is a single demo `Bridge` contract; the
`BridgeRoot`/`WrappedToken` split is planned. The deployed contract and vault fix the
relayer/admin sets at deployment, so a key change is a redeploy. There is no ERTP adapter
and no relayer fee distribution.

**Relayer.** The rail is undecided ([issue #563](https://github.com/rhovision-org/rholo/issues/563)).
The implemented watcher is dev-only, with fixed keys, a JSON journal, no bond/slashing,
no conflict detection and no Tron or Agoric settlement.

**Chains.** Ethereum is tested on Anvil only. Tron has no deployment, TVM tests, watcher
or withdrawals, and Tron deposits are not minted in the demo. Agoric has only a locally
tested vat: no live chain, IBC denoms, Keplr writes or watcher. Hyperliquid and Bitcoin
have no code.

**Web dApp.** No Keplr writes, no MetaMask Snap, no Tron withdrawals; USDC/DAI are
read-only until a deployment includes them; the keystore is unaudited.

**Finality and testnets.** No public-testnet run has been performed; Sepolia needs a
funded key and operator addresses, Nile needs a TronWeb deployment, Agoric needs IST and a
live chain. The interactive dev watcher defaults to zero confirmations.

**Assets and parameters.** The registry is a plan; only Ethereum ETH and USDT are
exercised end to end here. Fees/caps are testnet values. The deploy budget is 64 KiB
(56 KiB planning), currently ~15.5 KiB.

## Specifications

The normative specs live in `spec/` and are included verbatim in the book's
[Reference](docs/src/reference/attestation.md) section.

- [`spec/attestation.md`](spec/attestation.md) — canonical message, signatures, golden
  vectors.
- [`spec/assets.md`](spec/assets.md) — registry and amount scaling.
- [`spec/invariants.md`](spec/invariants.md) — conservation, idempotency, authority,
  finality.
- [`spec/keystore.md`](spec/keystore.md) — Web3 v3 rholo keystore format and interop.
- [`spec/relayer-interface.md`](spec/relayer-interface.md) — the boundary between
  r-bridge and the node add-on.

## License

AGPL-3.0-only. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
