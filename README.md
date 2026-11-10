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
| **Status** | **Phase 1 demo and Phase 2 EVM ↔ rholo cross-chain demo pass on a local rholo devnet + Anvil; the Ethereum/TVM vault passes 10 Foundry tests.** Sepolia/Nile/Agoric and the production relayer are next. No real value moves. |

## Wallets

r-bridge uses what the user already has:

- **MetaMask** for Ethereum accounts, network switching, approvals and vault calls.
- **TronLink** for Tron accounts and TRC-20 calls.
- **Keplr** for Cosmos/Agoric accounts and Zoe/IBC offers.
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
the choice. See `docs/src/infrastructure-decision.md`.

## Repository map

| Area | Path |
|---|---|
| Rust primitives | `crates/rbridge-{core,chain,sdk,cli,wasm}` |
| Web dApp | `web/` |
| Rholang bridge contract (demo) | `contracts/rholo/` |
| Ethereum/TVM vault | `contracts/evm/` (Tron reuse in `contracts/tron/`) |
| Agoric escrow vat (Zoe) | `contracts/agoric/` |
| Dev harness + mock relayer | `harness/` |
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

`make check` runs the Rust, contract, web and docs gates.

## Run the Phase 1 demo

Prereqs: Docker, a local rholo checkout at `~/RNodeRust` (override with
`RHOLO_DIR=...`), and the Rust toolchain. The EVM vault tests also need Foundry; the
Makefile expects it at `~/.foundry/bin/forge` (override with `FORGE=...`).

```bash
make devnet-up    # starts a 1-validator local devnet (8 GB node memory) on :40403
make demo         # installs the bridge, runs 22 checks, exits PASS/FAIL
make devnet-down
```

The demo installs the rholo bridge contract, signs a deposit attestation with 2 of 3
dev relayer keys, mints, replays the same deposit (refused), tries below-threshold
(refused), burns, completes the withdrawal, transfers, pauses/unpauses via 2-of-3 admin
signatures, and checks conservation. It is devnet-only; keys are generated in
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
pending when it started, so it only settles new work. It is a dev loop (fixed keys, no
reorg handling, ETH-only, no bond/slashing); the production rail is still undecided.

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

## Current status

- Phase 1 rholo demo: PASS (22 checks).
- Phase 2 EVM vault: 10 Foundry tests pass (including a 2-of-3 admin refund); ETH and
  ERC-20 USDT ↔ rholo e2e PASS on Anvil + local devnet.
- Dev relayer loop: PASS — deposit watcher mints, withdrawal watcher unlocks and
  completes; failed deposits are journaled and `make refund-failed` returns the native
  funds via the admin refund.
- Web demo: live rholo bridge/vault reads, MetaMask ETH and USDT locks (approve +
  lock), a WASM-signed rholo burn for withdraw, and rholo keystore import/create
  (Web3 v3, r-wallet compatible); 19 unit + 4 Playwright browser tests + 5 opt-in live
  tests pass, and a Node smoke test signs and submits a burn through the wasm client.
- Agoric vat: Zoe escrow/release contract passes deposit, 2-of-3 release, replay,
  below-threshold and wrong-digest tests. No live Agoric chain/IBC or Agoric watcher yet.
- Not yet: Sepolia/Nile deployment, live Agoric/IBC, reorg handling, multi-validator
  finality, production relayer, TronLink/Keplr writes, keystore session persistence in
  the browser.

The devnet is a single validator, which can report `finalized: false` even after
`ProcessedWithSuccess` (rholo issue #356). The demo uses the processed result as its
gate; testnet/production must additionally require finality.

## Documents

- `spec/attestation.md` — the cross-chain message and signature format.
- `spec/assets.md` — the initial asset registry and amount scaling.
- `spec/invariants.md` — conservation, idempotency, auth and finality rules.
- `spec/keystore.md` — the Web3 v3 rholo keystore format, interop and import limits.
- `spec/relayer-interface.md` — the boundary between r-bridge and the node add-on.
- `docs/src/architecture.md`, `docs/src/flows.md`, `docs/src/roadmap.md`.

## License

AGPL-3.0-only. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
