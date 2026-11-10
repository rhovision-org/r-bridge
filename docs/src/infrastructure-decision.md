# Infrastructure decision: where the relayer runs

**Status: undecided.** The final product depends on this decision. The demo is being
built in the meantime, and is designed to be useful whichever way the decision goes.

## The question

A bridge needs a relayer layer that watches Cosmos/Agoric, Ethereum and Tron, waits for
finality, signs m-of-n attestations, submits rholo mints and broadcasts native unlocks.
Where that layer lives is open:

| Option | What it means |
|---|---|
| **Standalone relayer/bridge node** | Its own repo and operator set; runs beside rholo, not inside it. Can serve several rholo networks. |
| **rholo node plugin/sidecar** | Shipped with or alongside the rholo node; node operators opt in. Reuses node-operator trust and monitoring. |
| **Hybrid** | A reference relayer in its own repo, packaged so a node operator can run it as an add-on. |

[rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563) is the
node-side proposal for the plugin/sidecar option. It is a proposal, not a decision.

## What the decision changes

- Trust anchoring: validators vs an independent operator set.
- The incentive and slashing design: phlo/validator alignment vs a separate fee market.
- Release coupling: bridge releases tied to node releases, or independent.
- Operator footprint and co-location constraints (the relayer should not share a 4 GB
  `rnode` host).
- Governance: who admits relayers, who updates the set, who holds the bond.
- Audit surface: one artefact or two.

## What the decision does **not** change

The demo deliberately isolates these, so work is not wasted:

- `spec/attestation.md` — the canonical message, digest and signature formats.
- `contracts/rholo` — the bridge contracts and their invariants.
- `contracts/{evm,tron,agoric}` — native vaults and the Agoric vat.
- `spec/relayer-interface.md` — the read API, journal schema, metrics and key rules.
- The dApp, CLI, SDK and WASM primitives.
- The asset registry and deployment manifests.

Only the process that implements the interface, and its packaging, moves.

## Demo status (2026-11-10)

The rail-agnostic demo **passes** on a local rholo devnet: the bridge contract installs,
a mock 2-of-3 relayer signs the canonical digest, and 30 checks cover mint, replay,
below-threshold refusal, burn, withdrawal completion, transfer, pause/unpause, the
treasury fee sweep and conservation. `make mock-relayer` exposes the read interface from
`spec/relayer-interface.md`.

The Ethereum/TVM vault is also implemented and passes 10 Foundry tests, including a
withdrawal digest shared with the Rust signer and a 2-of-3 refund for failed deposits. The
cross-chain demo **passes** on Anvil + the local rholo devnet for ETH and ERC-20 USDT:
lock → 2-of-3 deposit attestation → rholo mint → burn → 2-of-3 65-byte EVM signatures →
native unlock with fee/scale accounting. A deposit below the rholo minimum is journaled
by the watcher and returned through the admin refund.

The dev watcher loop also passes: a new Anvil deposit is decoded and minted on rholo
automatically, and a new rholo burn is unlocked and completed on Anvil automatically
(2-of-3, fixed dev keys). Its safe-head gate and reorg journal pass `make reorg-demo`:
an unprocessed rollback rewinds the cursor, and a rollback that removes a settled
deposit halts for reconciliation. `make metrics-demo` checks the Prometheus, health and
chains endpoints, including while halted. That makes the watcher/attester/submitter work
concrete.
The web demo now reads the live rholo bridge and Anvil vault and locks ETH and USDT
(approve + lock) through MetaMask, so the user-facing loop is observable end to end. The Agoric Zoe escrow/release
vat is tested at the contract level; a live Agoric chain/IBC denoms and an Agoric watcher
remain.

Not yet covered: Sepolia/Nile deployment, the Agoric vat, reorg handling, finality on a
multi-validator/testnet, and the production relayer (journal, metrics, packaging,
bond/slashing). Those are the evidence needed for the rail decision.

## The demo

The demo is a local rholo devnet plus the bridge contract and a **mock relayer**:

1. Install the bridge suite and register assets.
2. Lock an asset on a local/mocked native rail (or simulate the deposit event).
3. The mock relayer signs the canonical digest with 2-of-3 dev keys.
4. Mint on rholo; replay and below-threshold calls are refused.
5. Burn on rholo; the mock relayer marks the unlock and the native vault releases.
6. Check conservation, caps, pause and refusal paths.

The mock is not a production relayer. It exists to make the contracts and the interface
observable, and to produce the evidence the rail decision needs: latency, confirmation
handling, operator steps and failure modes.

## Decision gates

The rail can be chosen once the demo has shown:

- the attestation and finality loop end-to-end on at least one testnet;
- the operator steps and hardware for both shapes are documented and measured;
- the fee/bond numbers are calibrated against real volume;
- the rholo node side agrees on the plugin boundary (if that rail is chosen);
- an external audit plan covers the chosen packaging.
