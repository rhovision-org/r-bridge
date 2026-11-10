# Relayer

A bridge needs a relayer layer that watches the native chains, waits for finality, signs
the m-of-n attestation, submits rholo mints and broadcasts native unlocks. **Where that
layer runs is undecided**: a standalone relayer/bridge node, a rholo node plugin/sidecar,
or a hybrid. [rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563)
is the node-side proposal, not a decision. See
[Infrastructure decision](infrastructure-decision.md).

This repository contains only a **development relayer** and the rail-agnostic boundary it
implements. It must never be presented or operated as production software.

## What exists today

| Piece | Location | What it does |
|---|---|---|
| Dev watcher | `harness/dev_relayer.py` | Watches new Anvil `Deposit` logs and mints on rholo; polls rholo `pendingWithdrawals` and unlocks on Anvil; journals everything |
| Mock relayer | `harness/mock_relayer.py` | Serves the read interface from canned/attested data; watches no chain |
| Read client | `crates/rbridge-sdk` (`RelayerClient`) | Reads health, chains, a deposit, its attestation and a withdrawal; 404 becomes `None` |
| CLI | `crates/rbridge-cli` | `rbridge relayer health\|chains\|deposit\|withdrawal\|attestation --url` |
| Interface | `spec/relayer-interface.md` | Config, read API, journal schema, metrics, key rules, rails table |

### Deposit loop

1. Start at the current safe head and scan `Deposit` logs.
2. Decode the event and read the vault's per-asset configuration.
3. Build the canonical deposit message; sign it with the configured 2-of-3 keys.
4. Call `Bridge.mint` and wait for a finalized, successful result returning `true`.
5. Record the deposit as settled. If it cannot be minted (for example below the rholo
   minimum), journal it under `failed_deposits` instead of dropping it.

### Withdrawal loop

1. Poll rholo `pendingWithdrawals` for burns that are finalized and processed.
2. Build the withdrawal message with the lowercase native recipient and sign the 65-byte
   EVM form with 2-of-3 keys.
3. Call `vault.unlock`, then `completeWithdrawal` with the native transaction hash.
4. Record the withdrawal and expose the native tx through the read API.

The watcher ignores withdrawals that were already pending when it started, so it only
settles new work. That avoids surprising a demo operator with old records.

## Finality, reorgs and the journal

- **Safe head.** The watcher settles only below `--confirmations N` or, with
  `--finalized`, only what the node marks finalized. The interactive demo defaults to
  `--confirmations 0`; a testnet run must use `--finalized` or a real depth.
- **Block-hash journal.** Each settled deposit records its block hash. Every scan compares
  recent deposits with the canonical chain.
- **Rewind.** An unprocessed reorg rolls the cursor back and the work is retried.
- **Halt.** A reorg that removes a settled deposit halts settlement for reconciliation; it
  is never silently re-minted.
- **Failed deposits.** A deposit that locked funds but could not be minted is journaled
  with its token, sender, amount and reason. `make refund-failed` signs the vault's 2-of-3
  admin refund; a production rail needs a governed claim path.

`make reorg-demo` proves both reorg paths on its own Anvil. The journal is a JSON state
file, not a production database, and there is no crash-consistency proof beyond atomic
writes.

## Read API and metrics

The dev watcher serves, on `--metrics-port`:

| Endpoint | Content |
|---|---|
| `/health` | Halted state, chain head, enabled chains |
| `/v1/chains` | Per-chain head/enabled state and relayer threshold |
| `/v1/deposits/{id}` | Journaled deposit state and reason |
| `/v1/deposits/{id}/attestation` | Canonical message and signatures |
| `/v1/withdrawals/{id}` | Journaled withdrawal state and native tx |
| `/metrics` | Prometheus text |

Actual metric names emitted by the dev watcher:

- `rbridge_chain_head{chain}`
- `rbridge_deposits_total{chain,state}`
- `rbridge_withdrawals_total{chain,state}`
- `rbridge_reorgs_total`
- `rbridge_errors_total{chain,kind}`
- `rbridge_halted`

`spec/relayer-interface.md` also defines `rbridge_pending`; the dev watcher does not emit it
yet. The endpoints stay available while the watcher is halted, which is deliberate: a halt
must remain observable.

The web dApp consumes this API (see [Web dApp](web-app.md)).

## Keys

- Attestation signing uses the relayer keys in the bridge's configured set. The dev
  watcher loads fixed demo keys; it has no HSM and no remote signer.
- Keys must be separate from the validator key and from the deploy/phlo key.
- The relayer has no custody: it observes, signs and submits.
- Production needs encrypted keys or an HSM, per-operator separation, and a rotation
  process. None of that exists here.

## Running the development relayer

```bash
make devnet-up && make demo   # rholo devnet + installed bridge
make e2e-evm                  # Anvil + vault, writes .devnet/evm.json
make relayer-watch            # start before locking/burning
make mock-relayer             # alternative: canned read surface on :8099
make refund-failed            # 2-of-3 refund for journaled failed deposits
make reorg-demo               # own Anvil; cursor rewind and halt
make metrics-demo             # own Anvil; /metrics, /health, /v1/chains
make api-demo                 # own Anvil; deposit reads and 404 paths
```

## Development vs production

| Requirement | Dev relayer today | Production requirement |
|---|---|---|
| Packaging | Python script in `harness/` | Signed binary/container, systemd/Docker, upgrades |
| Chains settled | Anvil deposits; rholo withdrawals | Ethereum, Tron and Agoric watchers and submitters |
| Finality | Safe-head flag; demo defaults to 0 confirmations | Chain-specific finalized/depth rules |
| Keys | Fixed dev keys, plaintext config | Encrypted/HSM, per-operator, rotation |
| Relayer independence | Single process with all demo keys | Independent operators, no shared keys |
| Coordination | None | Shared set/threshold, conflict detection |
| Bond and slashing | None | On-chain bond and slashing, or an explicit trust decision |
| Fee distribution | None; fees accrue to a treasury | Epoch distribution to active relayers |
| Journal | JSON file | Durable, backed-up database |
| API exposure | Local only | Authenticated or network-restricted |
| Rail | Undecided | Decided and audited |

The production gaps are part of [Current limitations](limitations.md). The rail decision
will determine which of them move into the node add-on.
