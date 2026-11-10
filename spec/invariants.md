# Bridge invariants

These are the properties the contracts and tests must preserve. A change that weakens
one is a protocol change, not an implementation detail.

## Conservation

For each wrapped asset on rholo:

```
totalMinted = circulating + feeBalance + totalBurned
```

- `mint(A)` with fee `F`: `totalMinted += A`, recipient `+= A - F`, `feeBalance += F`.
- `burn(B)`: `circulating -= B`, `totalBurned += B`.
- `admin("withdrawFees", asset)`: `feeBalance -= F`, treasury `+= F`, where `F` is the
  whole accrued bucket. This moves fees into circulation; it mints nothing.
- No balance may be negative. `transfer` moves value between holders without changing
  the totals.
- On the native side, the vault's locked balance must never be less than the wrapped
  supply it backs plus fees it is holding. A withdraw fee retained in the vault is not
  lost; it is accounted for in the fee treasury.

Every value-moving path has a conservation assertion in the contract and a test that
checks the totals before and after.

## Idempotency and replay

- A deposit id can mint at most once. `processedDepositIds` is checked **before** any
  effect and the prior result is returned on a repeat.
- A withdrawal id can unlock at most once. Each vault stores used ids and refuses a
  repeat rather than transferring twice.
- The attestation digest binds network, chain, bridge id, asset, direction, external tx
  id, amount, recipient and nonce. A signature for one chain, asset or direction must
  not verify for another.
- Relayers must not sign two different messages for the same external tx id. Conflicting
  signatures are slashable once the bond exists.

## Authority

- `transfer` and `burn` act on the caller's `rho:rchain:deployerId` (65-byte pubkey).
  No arm accepts a caller-supplied `from` address.
- Mint authority is a capability held in the `Bridge` closure. It is not stored in a
  state map and is not exposed at a public name.
- Admin arms (registry, fee, caps, pause, relayer set) require the 2-of-3 admin set.
  The fee sweep credits the treasury address fixed at deploy; there is no arm that
  moves fees to a caller-chosen recipient.
- A pause must not block `burn`, refunds, or completion of an in-flight transfer. New
  deposits/mints fail closed.

## Caps and limits

- Per-transaction `min_deposit` / `max_deposit` from the asset spec.
- Per-asset epoch cap (block-height window) on minted amount.
- Global outstanding cap per asset (the minted supply ceiling).
- Refusals are explicit `(false, reason)` replies, never silent partial fills.

## Finality

- A native deposit is attested only after the configured confirmation depth.
- A rholo burn is unlocked only after the containing block is finalized, the deploy is
  `ProcessedWithSuccess`, and the contract reply is `(true, …)`.
- A reorg before signing cancels the attestation. A reorg after signing is an incident:
  pause, do not reuse the id, reconcile.

## Rholang platform rules

- One state cell per object: consume, validate the consumed snapshot, repost exactly
  once on every path.
- No `select`; use one consumable datum.
- Deploy terms ≤ 56 KiB (node cap 64 KiB inclusive).
- No timers; use block heights. `rho:block:data`'s timestamp is the proposer's clock.
- A deploy is atomic; blocks are sequential. Repost before an external await where
  possible.
- Every arm has a refusal test and, where it moves value, a conservation test.

## Test matrix

| Area | Cases |
|---|---|
| mint | valid threshold; below threshold; wrong asset/chain/direction; replay; paused; cap; dust amount |
| burn | holder only; insufficient balance; destination validation; idempotent op id; paused (must still allow burn) |
| transfer | holder only; zero/negative; self-transfer; conservation |
| fees | treasury sweep at threshold; below threshold; empty bucket; unknown asset; conservation |
| attestation | golden digest; each field bound; malformed DER; duplicate signer; non-32-byte digest; `|` injection |
| registry | admin only; scale bounds; fee/cap bounds; disabled asset exit path |
| scaling | 18→8; 6→6; dust refusal; i64 overflow; round trip |
