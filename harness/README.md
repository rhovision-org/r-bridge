# Development harness

Devnet only. Nothing here is a production relayer, and the keys are worth nothing.

## Contents

- `render.py` — fills the deploy template (`contracts/rholo/build/00_bridge.rho`) with
  the network, bridge id, admin/relayer sets and the asset registry.
- `demo.py` — the Phase 1 end-to-end demo. Installs the bridge, signs a deposit with
  2-of-3 dev relayer keys, mints, tests replay/below-threshold/unknown-asset, burns,
  completes the withdrawal, transfers, pauses/unpauses via 2-of-3 admin signatures, and
  checks conservation. Prints PASS/FAIL for each check.
- `mock_relayer.py` — the dev-only HTTP surface from `spec/relayer-interface.md`:
  `/health`, `/v1/chains`, `POST /v1/deposits`, `/v1/deposits/{id}` and
  `/v1/deposits/{id}/attestation`. It watches no chain; it attests what it is told.
- `e2e_evm.py` — the cross-chain demo: deploys `MockERC20` + `BridgeVault` to Anvil, runs
  the ETH flow (lock 0.1 ETH → attest → mint → burn 0.05 ETH → 65-byte sigs → unlock →
  complete) and the USDT flow (mint/approve/lock 1 USDT → mint → burn 0.4 → unlock).
- `evm_refund.py` — the recovery path for a deposit the relayer journaled as failed:
  signs the vault's `rbridge:admin:v1|refund|…` payload with 2-of-3 demo admin keys and
  returns the locked native funds to the depositor.
- `dev_relayer.py` — the dev watcher loop. It scans new Anvil `Deposit` logs, decodes
  the event, reads the vault asset config, signs the 2-of-3 deposit digest, and calls
  `Bridge.mint`. It also polls rholo `pendingWithdrawals`, signs the 65-byte withdrawal
  digest, calls `vault.unlock`, and marks the withdrawal complete. Start it before
  locking; it ignores pre-existing pending withdrawals.
- `.devnet/` — generated keys (`demo-keys.json`, mode 600), the installed bridge URI,
  the Anvil vault address, rendered terms and transient files. Gitignored.

## Commands

```
make devnet-up      # local rholo devnet on :40403 (RHOLO_DIR, 8 GB node memory)
make demo           # build the CLI, install the bridge, run the checks
make mock-relayer   # HTTP relayer surface on 127.0.0.1:8099
make e2e-evm        # cross-chain demo; requires Anvil on :8545
make relayer-watch  # dev watcher loop; start it before locking
make refund-failed  # return native funds for journaled failed deposits
make devnet-down
```

The first `make demo` generates the deployer/admin/relayer/user keys. Later runs reuse
them, so a re-run installs a fresh bridge at a new URI and repeats the checks.

## What the demo proves

- The bridge contract parses and installs within the deploy budget (15.5 KiB; limit
  56 KiB client / 64 KiB node).
- The canonical attestation digest is reproduced by the Rust signer and the Rholang
  verifier; 2-of-3 works and 1-of-3 is refused.
- Deposit idempotency, asset/amount validation, fee arithmetic, burn records,
  withdrawal completion, holder-signed transfer, pause semantics and conservation.
- The admin surface is 2-of-3 over a nonce-bound canonical payload.
- `e2e_evm.py` proves the cross-chain loop on Anvil + the local devnet: native lock,
  2-of-3 deposit attestation, rholo mint, rholo burn, 65-byte EVM signatures, and the
  native unlock with the vault's scale/fee accounting.
- `dev_relayer.py` proves the watcher loop: a new Anvil deposit is decoded and minted
  automatically, and a new rholo burn is unlocked and completed automatically. The
  withdrawal watcher ignores records that were already pending at startup.
- The watcher journals a deposit it cannot mint (for example below the rholo minimum) in
  `failed_deposits` and does not silently drop it. `evm_refund.py` returns the native
  funds through the vault's 2-of-3 admin refund; the demo verified 500,000 USDT returned
  to the depositor. A production rail needs a governed refund runbook/claim path.

## What it does not prove

- Production chain custody: Anvil is a local EVM, not Sepolia; Tron/Nile and the Agoric
  vat are not deployed.
- Finality: the single-validator devnet can report `finalized: false` after
  `ProcessedWithSuccess`; the demo gates on the processed result. Testnet/production
  must require finality.
- Real chain watching, reorg handling, or the production rail. The harness performs the
  watcher/attester/submitter steps manually and `mock_relayer.py` is a fixed-key
  stand-in; the rail (standalone bridge node vs rholo plugin/sidecar) is undecided.
