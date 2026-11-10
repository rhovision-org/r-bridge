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
- `e2e_evm.py` — the cross-chain demo: deploys `BridgeVault` to Anvil, locks 0.1 ETH,
  attests the deposit with 2-of-3 relayer signatures, mints on rholo, burns 0.05 ETH
  worth, signs the withdrawal in 65-byte EVM form, and calls `unlock`.
- `.devnet/` — generated keys (`demo-keys.json`, mode 600), the installed bridge URI,
  the Anvil vault address, rendered terms and transient files. Gitignored.

## Commands

```
make devnet-up      # local rholo devnet on :40403 (RHOLO_DIR, 8 GB node memory)
make demo           # build the CLI, install the bridge, run the checks
make mock-relayer   # HTTP relayer surface on 127.0.0.1:8099
make e2e-evm        # cross-chain demo; requires Anvil on :8545
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

## What it does not prove

- Production chain custody: Anvil is a local EVM, not Sepolia; Tron/Nile and the Agoric
  vat are not deployed.
- Finality: the single-validator devnet can report `finalized: false` after
  `ProcessedWithSuccess`; the demo gates on the processed result. Testnet/production
  must require finality.
- Real chain watching, reorg handling, or the production rail. The harness performs the
  watcher/attester/submitter steps manually and `mock_relayer.py` is a fixed-key
  stand-in; the rail (standalone bridge node vs rholo plugin/sidecar) is undecided.
