# Relayer interface (rail-agnostic)

**The relayer rail is undecided.** It may be a standalone relayer/bridge node repo, or a
plugin/sidecar for the rholo node. The final product depends on that decision; the demo
is being built in the meantime to inform it. This document defines the interface either
rail must provide, so the contracts, dApp and CLI do not depend on the answer.
[rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563) is the
node-side proposal, not a decision.

## Responsibilities

| r-bridge | Relayer implementation (either rail) |
|---|---|
| Rholang bridge suite and native vaults/vat | Watch Cosmos/Agoric, Ethereum, Tron |
| Attestation format and golden vectors | Wait for finality; sign the digest |
| dApp, CLI, SDK and WASM primitives | Submit rholo mints; broadcast native unlocks |
| Registry and fee/cap parameters | Persist a journal, expose metrics/health |
| Deployment manifests | Key management and operator runbooks |

r-bridge ships a **development mock relayer** in `harness/` with the same HTTP shape and
a fixed dev key. It must never be pointed at a network holding real value. The mock is
what makes the demo independent of the rail decision.

## Configuration

The relayer reads (names are a proposal; either rail can implement them):

```toml
node = "http://127.0.0.1:40403"       # local rnode public API
admin_node = "http://127.0.0.1:40405" # only if proposing/administrative actions are needed
network = "rbridge-devnet"
bridge_id = "rho:id:..."
db = "/var/lib/rbridge-relayer/relayer.sqlite"
metrics = "127.0.0.1:9100"
threshold = 2
signers = ["04...", "04...", "04..."]  # the on-chain relayer set the add-on is part of

[chains.ethereum]
rpc = "https://..."                   # must expose the finalized tag
vault = "0x..."
confirmations = "finalized"

[chains.tron]
rpc = "https://..."
vault = "T..."
confirmations = 19

[chains.agoric]
rpc = "https://..."
vat = "agoric1..."                    # instance/address, recorded in the manifest
confirmations = 30

[keys]
attestation = "/etc/rbridge-relayer/attestation.key"  # separate from the deploy key
deploy = "/etc/rbridge-relayer/deploy.key"
```

Keys must never be the validator key. The attestation key signs digests; the deploy key
pays phlo and submits deploys. Both are encrypted at rest or held in an HSM.

## Read API (for the dApp/CLI)

Read-only in production; the relayer should not expose a signing endpoint to the public
internet without authentication.

| Method | Path | Result |
|---|---|---|
| `GET` | `/health` | `{version, chains, threshold, signers, paused}` |
| `GET` | `/v1/chains` | per-chain head, confirmations, enabled |
| `GET` | `/v1/deposits/{deposit_id}` | `{state: pending\|attested\|minted\|failed, message?, signatures?}` |
| `GET` | `/v1/deposits/{deposit_id}/attestation` | `{message, signatures}` or 404 while pending |
| `GET` | `/v1/withdrawals/{withdrawal_id}` | `{state: pending\|signed\|unlocked\|failed, native_tx?}` |

The dApp polls these. Anyone may submit a valid attestation to `Bridge.mint`; the
verification is on-chain, so a relayer does not need to be the submitter.

## Journal

The relayer persists at least:

- `deposits(deposit_id, chain, tx_hash, log_index, block_hash, block_number, asset,
  amount, recipient, state, attempts, last_error)`
- `attestations(deposit_id, signer_pubkey, signature, signed_at)`
- `withdrawals(withdrawal_id, chain, asset, amount, recipient, rholo_block, state,
  native_tx, attempts, last_error)`
- `chain_cursor(chain, last_processed_block, last_processed_hash)`
- `used_deposit_ids`, `used_withdrawal_ids` (or rely on the on-chain sets and mirror
  them)

The journal is the reorg/idempotency record. A cursor is advanced only after the block
is final; a reorg rewinds the cursor and drops unsigned work.

## Reorg handling

- The safe head is the chain's `finalized` block where the RPC supports it, otherwise
  `latest - confirmations`. Logs above the safe head are not settled.
- The last `reorg_window` block hashes are journaled. On a mismatch the relayer walks
  back to the common ancestor, rewinds the cursor, and rescans the range. Unprocessed
  work is dropped with the reorged blocks.
- If a **settled** deposit is reorged out, the relayer halts instead of continuing: the
  rholo mint may already exist and a watcher cannot undo it. The operator reconciles
  (pause/refund path) and restarts from a reset journal.
- A failed-deposit journal entry in the reorged range is removed, because the native
  lock no longer exists.
- `harness/reorg_demo.py` proves both paths on Anvil: a rollback with no settled deposits
  rewinds cleanly; a rollback that removes a settled deposit halts.

## Metrics

```
rbridge_chain_head{chain}
rbridge_deposits_total{chain,state}
rbridge_attestations_signed_total{chain}
rbridge_mints_submitted_total{state}
rbridge_withdrawals_total{chain,state}
rbridge_unlocks_broadcast_total{chain,state}
rbridge_errors_total{chain,kind}
rbridge_pending{chain}
```

Health is a separate endpoint so a load balancer does not parse Prometheus text.

The dev watcher implements this surface on `--metrics-port`: `/metrics` (Prometheus),
`/health` (JSON) and `/v1/chains`. Settled deposits and withdrawals are counters, failed
deposits and reorgs are error counters, and `rbridge_halted` is 1 while it refuses to
settle. The endpoints stay up while halted so alerting can fire; `metrics_demo.py`
checks the scrape and the halt transition.

## Registration and economics

- The relayer set and threshold live in `BridgeRoot` and in each native vault; a change
  is a 2-of-3 admin action.
- Fee parameters live in `BridgeRoot`; fees accrue to a bridge treasury and are
  distributed to active relayers per epoch. Fee collection must not change conservation.
- A relayer bond and slashing are proposed as a later phase; until then, the set is
  permissioned and audited rather than economically bonded.
- Hardware, cost and break-even estimates are in the node issue and in
  `docs/src/operator-guide.md`.

## Security

- Independent operators, jurisdictions and RPC providers; do not share infra or keys.
- Confirmation depths are configuration, but the contracts enforce the minimum.
- The relayer must fail closed: if a chain RPC is unhealthy or a cursor is ambiguous, do
  not sign. A paused bridge stops new mints; burns and unlocks of in-flight transfers
  remain available.

## Rails under discussion

| Rail | Strengths | Costs |
|---|---|---|
| Standalone relayer/bridge node | Independent of validator operations; can serve several rholo networks; single deployment/audit surface; no node release coupling | A second operator set and incentive scheme; operators must run rholo light/full access; trust is not anchored to validators |
| rholo node plugin/sidecar | Reuses node-operator trust and monitoring; one package; phlo/validator alignment | Couples bridge releases to node releases; co-location/security constraints; every operator must opt in |
| Hybrid | Reference relayer in its own repo, packaged as a node add-on; either deployment | Two artefacts to keep in sync |

What is already rail-independent: the attestation format (`spec/attestation.md`), the
bridge contracts, the dApp/CLI interfaces, the read API above, the journal schema and
the metrics names. The demo exercises exactly these.
