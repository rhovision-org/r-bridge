# Flows

Every value-moving path is m-of-n attested over the canonical digest in
[Attestation](reference/attestation.md). This chapter describes the user-visible flows and
the current state of each one. The invariants behind them are in
[Invariants](reference/invariants.md).

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

1. The dApp builds the `approve` (ERC-20/TRC-20) and `lock` calls; the wallet signs. Native
   assets use `msg.value`/`callValue`; ETH/Tron addresses are canonicalised to lowercase
   `0x` form where a digest is involved.
2. The vault records the deposit and emits
   `Deposit(depositId, token, sender, amount, rholoRecipient, nonce)`. The id binds the
   chain, vault, transaction and log index; the sender's nonce is consumed.
3. Relayers wait for finality, build the canonical message, sign the digest, and expose
   the attestation through the read API (or return signatures directly).
4. `Bridge.mint` verifies m-of-n, consumes the deposit id, and credits the recipient
   `amount - depositFee`. The fee stays in the per-asset `fees` bucket.
5. The dApp follows `/v1/deposits/{id}` and shows minted/failed/unreachable. A second
   submission of the same id is a no-op.

**State today.** The full flow is tested on Anvil plus the local rholo devnet for ETH and
ERC-20 USDT (`make e2e-evm`). TronLink deposits are built and signed by the dApp and
covered by unit and Playwright tests, but the demo relayer watches Anvil only and no TVM
vault is deployed, so a Tron deposit is not minted here. Agoric deposits have a tested
vat but no Keplr write path.

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

1. The user unlocks their Web3 v3 rholo keystore in WASM (or supplies a devnet secret) and
   signs a `burn` deploy; the app records the op id. The decrypted key is held in memory
   for that operation only.
2. The burn debits the holder, records `(withdrawalId, asset, gross, destChain,
   destAddress)` and exposes it through `pendingWithdrawals`. Burns remain available while
   the bridge is paused.
3. After finality, relayers sign the unlock digest (direction `withdraw`, recipient = the
   lowercase native address) with 65-byte `r||s||v` signatures and broadcast the unlock.
4. The vault releases `grossNative - withdrawFee`, marks the withdrawal id used, and keeps
   the fee in `fees[token]`. The relayer calls `completeWithdrawal` with the native tx id.
5. The dApp follows `/v1/withdrawals/{id}` and shows the native tx or the reason it was
   not handled.

**State today.** Tested on Anvil for ETH and USDT. There is no Tron unlocker or Agoric
payout relayer, and the dApp does not offer a Tron destination yet.

## Refund: a deposit that cannot be minted

A deposit can lock native funds and still be un-mintable (for example below the rholo
minimum). The relayer journals it as a failed deposit instead of dropping it, and the
vault's 2-of-3 admin refund returns the full locked amount:

```
admin keys ──sign rbridge:admin:v1|refund|token|to|amount|depositId|nonce──► vault.refund
                                                                           │ one-shot per deposit id
                                                                           ▼ returns full amount
```

The refund is a vault-side recovery, not a rholo mint. It is one-shot per deposit id and
requires the admin threshold. `make refund-failed` exercises it on Anvil; the demo
returned 500,000 USDT to a depositor. A production rail needs a governed claim/refund
runbook rather than fixed-key scripts.

## Admin: pause and fee sweep

Both the rholo bridge and the vault verify a 2-of-3 admin payload
`rbridge:admin:v1|<action>|<args>|<nonce>` and reject replayed nonces.

| Action | Where | Effect |
|---|---|---|
| `setPaused` | rholo, vault | Blocks new deposits/mints and vault locks. Burns, unlocks and refunds remain available. |
| `withdrawFees` | rholo | Sweeps the whole accrued per-asset fee bucket to the treasury's **wrapped** balance. |
| `withdrawFees` | vault | Treasury-gated (not a 2-of-3 action): moves native fees to a chosen recipient up to the accrued amount. |
| `refund` | vault | 2-of-3 recovery of a deposit that was never minted. |

The rholo fee sweep is
`Bridge!("admin", "withdrawFees", assetKey, nonce, [sigs], *ret)`. It credits `treasury`
with the accrued amount and zeroes the bucket; circulating supply plus fees is unchanged,
so the sweep mints nothing and preserves conservation. The treasury is fixed at
deployment, so the action cannot redirect fees to a caller-chosen account.

**State today.** Pause/unpause, the admin nonce replay refusal and the fee sweep are in the
30-check devnet demo. The vault's pause and refund have Foundry tests.

## State machine

| State | Meaning | Next |
|---|---|---|
| `pending_native` | lock/burn submitted, not yet confirmed | `confirmed` or `failed` |
| `confirmed` | inclusion at the required depth | `attested` |
| `attested` | m-of-n signatures available | `minted` / `unlocked` |
| `minted` / `unlocked` | value delivered | terminal (relayer confirms completion) |
| `failed` | refused (cap, pause, reorg, invalid, below minimum) | refund or retry only if the first attempt had no effect |

The dev relayer's journal uses these states per deposit and withdrawal; the read API
exposes them.

## Failure paths

- **Reorg before signing**: drop the observation, rewind the cursor, do not sign. The dev
  relayer journals block hashes and proves this in `make reorg-demo`.
- **Reorg after signing**: incident; halt, pause via governance, never reuse the id,
  reconcile with the native chain and publish a note.
- **Insufficient threshold**: no mint/unlock; the dApp shows "waiting for relayers".
- **Paused bridge**: new deposits/mints fail closed; burns and in-flight unlocks still
  work.
- **Duplicate id**: no second effect; the prior result is returned.
- **Dust or out-of-range amount**: refused before any transfer; dust is never minted or
  rounded.
- **Wrong recipient**: the digest binds the recipient; changing it invalidates every
  signature.
- **RPC or cursor ambiguity**: stop signing; do not guess.

## Fees and conservation

Deposit fee is deducted from the minted amount and accrues in the bridge's per-asset
`fees` bucket. Withdrawal fee is retained by the vault and accounted in `fees[token]`.
The rholo sweep turns accrued fees into the treasury's wrapped balance; the vault's
treasury withdrawal moves native fees. Fees are never minted. Wrapped supply is backed by
native assets held by the vault/vat, and `totalMinted - totalBurned = circulating +
feeBalance` (plus the treasury after a sweep). The conservation invariant, its test matrix
and the treasury accounting are in [Invariants](reference/invariants.md).
