# rholo bridge suite (planned)

The canonical shared deployment. One bridge root and one wrapped-token instance per
asset per network. Contracts are implemented in phase 1; this file is the design entry
point.

## Components

- `BridgeRoot.rho` — installer-gated singleton. 2-of-3 admin; relayer pubkey set and
  threshold; asset registry; fee/cap parameters; pause. Exposes the read surface the
  dApp uses.
- `WrappedToken.rho` — one per asset. State cell `(totalSupply, balances:
  Map[holder_pubkey → Int])`. Public `balanceOf`/`transfer`; the mint/burn authority is a
  private capability held by `Bridge`, never stored in a state map.
- `Bridge.rho` — `mint(attestation, signatures)` verifies m-of-n over the canonical
  digest, consumes the deposit id, credits the recipient minus fee. `burn(asset, amount,
  dest_chain, dest_address)` debits the caller, records a withdrawal, emits an event.
  Tracks processed ids, pending withdrawals, fees, caps and pause.
- `Attestation.rho` — canonical message construction, `keccak256Hash`, and the
  `rho:crypto:secp256k1Verify` loop. Bounded signer loop (n ≤ 5 in v1).

## Deploy order

1. Deploy `BridgeRoot` with the admin set, relayer set/threshold and empty registry.
2. Install one `WrappedToken` per asset; register its URI and scale in `BridgeRoot`.
3. Install `Bridge` with the mint/burn capabilities from the tokens.
4. Hand admin to the 2-of-3 set; publish the manifest to `deployments/`.

The installer is idempotent and refuses a second installation of the same component.

## Constraints

- One state cell per object; consume, validate, repost exactly once.
- No `select`; one consumable datum.
- Deploy term ≤ 56 KiB (node cap 64 KiB inclusive).
- No timers; block heights only.
- Every mutating arm checks idempotency first; every value-moving arm asserts
  conservation and has a refusal test.
- Amounts are `i64` rholo base units; dust is refused.

## Tests

The phase-1 harness runs, at minimum: valid mint, below-threshold refusal, wrong
chain/asset/direction, replay, cap, pause, burn/transfer auth, insufficient balance,
conservation, malformed DER, duplicate signer, non-32-byte digest and `|` injection.
See `spec/invariants.md` for the full matrix.
