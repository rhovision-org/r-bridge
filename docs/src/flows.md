# Flows

## Deposit: native → rholo

```
user            dApp                 wallet              vault/vat          relayer            rholo Bridge
 │  pick asset    │                     │                    │                  │                    │
 │───────────────►│  approve + lock     │                    │                  │                    │
 │                │────────────────────►│  sign tx           │                  │                    │
 │                │                     │───────────────────►│  Deposit event   │                    │
 │                │                     │                    │─────────────────►│  wait finality     │
 │                │                     │                    │                  │  sign digest       │
 │                │                     │                    │                  │  m-of-n signatures │
 │                │  poll status        │                    │                  │───────────────────►│ verify
 │                │────────────────────►│                    │                  │                    │ consume id
 │                │                     │                    │                  │                    │ credit minus fee
 │  done          │◄────────────────────│                    │                  │                    │
```

1. The dApp builds the `approve` (ERC-20/TRC-20) and `lock` calls; the wallet signs.
2. The vault records the deposit and emits `Deposit(depositId, asset, amount, recipient,
   nonce)`.
3. Relayers wait for finality, build the canonical message, sign the digest, and expose
   the attestation.
4. `Bridge.mint` verifies m-of-n, consumes the deposit id, and credits the recipient
   `amount - depositFee`. The fee stays in `feeBalance`.
5. The dApp shows the completed state; a second submission is a no-op.

## Withdraw: rholo → native

```
user            dApp (WASM key)        rholo Bridge          relayer           vault/vat
 │  burn request  │                        │                    │                 │
 │───────────────►│  sign deploy           │                    │                 │
 │                │───────────────────────►│  burn(asset, amount, dest)           │
 │                │                        │  decrement, record withdrawal id     │
 │                │  wait finality         │───────────────────►│  observe        │
 │                │                        │                    │  verify final   │
 │                │                        │                    │  sign unlock    │
 │                │                        │                    │────────────────►│ release
 │                │                        │                    │                 │ mark id used
 │  done          │◄───────────────────────│                    │                 │
```

1. The user unlocks their Web3 v3 rholo keystore in WASM (or supplies the devnet secret)
   and signs a `burn` deploy; the app records the op id. The decrypted key is held in
   memory for the operation only.
2. After finality, relayers sign the unlock digest (direction `withdraw`, recipient =
   native address) and broadcast the native transaction.
3. The vault/vat releases `amount - withdrawFee`, marks the withdrawal id used, and the
   dApp shows the native tx.

## State machine

| State | Meaning | Next |
|---|---|---|
| `pending_native` | lock/burn submitted, not yet confirmed | `confirmed` or `failed` |
| `confirmed` | native/rholo inclusion at required depth | `attested` |
| `attested` | m-of-n signatures available | `minted` / `unlocked` |
| `minted` / `unlocked` | value delivered | terminal |
| `failed` | refused (cap, pause, reorg, invalid) | retry only if no effect |

## Failure paths

- **Reorg before signing**: drop the observation, rewind the cursor, do not sign.
- **Reorg after signing**: incident; pause, do not reuse the id, reconcile manually.
- **Insufficient threshold**: no mint/unlock; the dApp shows "waiting for relayers".
- **Paused bridge**: new deposits/mints fail closed; burns and in-flight unlocks still
  work.
- **Duplicate id**: no second effect; return the prior result.
- **Dust / amount out of range**: refused before any transfer.
- **Wrong recipient**: the digest binds the recipient; a changed recipient invalidates
  every signature.

## Fees and conservation

Deposit fee is deducted from the minted amount; withdrawal fee is retained by the vault
and accounted to the bridge treasury. Fees are never minted. The wrapped supply is
always backed by native assets held by the vault/vat; the conservation invariant and
its tests are in `spec/invariants.md`.
