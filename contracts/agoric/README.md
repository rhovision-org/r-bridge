# Agoric escrow vat (Zoe)

`src/bridge-vat.js` is a Zoe contract that holds an external asset (the issuer passed as
`Collateral`, representing an IBC denom on Agoric) in a contract-owned seat. A deposit
invitation records the amount and rholo recipient; a release invitation verifies the
m-of-n relayer attestation over the canonical withdrawal digest and pays the escrowed
asset to the recipient.

## API

- `makeDepositInvitation(rholoRecipient)` — the user offers `give: { Collateral: amount }`
  and receives a deposit record `{ depositId, amount, rholoRecipient }`.
- `makeReleaseInvitation({ withdrawalId, amountValue, recipient, nonce, signatures })` —
  verifies the attestation and creates a one-shot invitation. The recipient offers
  `want: { Collateral: amountValue }` and receives the escrowed asset as a payout.
- `getDeposits()` — records for the relayer.
- `getRelayerConfig()` — the relayer set and threshold.

## Attestation encoding

The digest is the shared r-bridge withdrawal message:

```
rbridge:v1|<network>|agoric|<bridgeId>|<assetKey>|withdraw|
<withdrawalId>|<amount>|<recipient>|<nonce>
```

keccak256 over the UTF-8 bytes. Signatures are **64-byte compact secp256k1** over that
digest, verified with `@noble/secp256k1` (`prehash: false`). rholo uses DER and the
EVM/Tron vault uses `r||s||v`; the same relayer key can emit each chain's encoding from
the same digest. The vat also accepts the rholo burn amount as a BigInt and checks the
escrow balance with `AmountMath.isGTE`.

## Run the tests

```bash
npm install --legacy-peer-deps
npm test
```

The tests use the SwingSet test environment directly (not ava): the current Agoric/Endo
ava wrapper has a version mismatch in this checkout. They cover deposit escrow, a 2-of-3
release, replay refusal, below-threshold refusal and wrong-digest refusal.

## Version pinning

The Agoric 0.27 / Zoe 0.27 packages need a coherent Endo/SES tree. The package.json pins
the Endo versions Agoric 0.27 was built against and overrides `ses` to `1.14.0`; newer
SES compartments omit `Float64Array`, which the ZCF bundle's marshal uses. `@noble/curves`
is not used in the vat because its bundled FFT module uses a direct `eval`, which SES
rejects; `@noble/secp256k1` is used instead (compact signatures only).

## What is proven, and what is not

Proven at the Zoe level: escrow, m-of-n attestation verification, one-shot release and
refusals.

Not yet: a live Agoric chain/IBC denoms, a relayer watching Agoric offers, durable
baggage stores, and binding the release invitation to an Agoric account address. In this
demo the release invitation is a bearer capability delivered to the recipient, and the
deposit/used-id maps are closure state. A production vat uses durable stores and the
recipient's account/key binding. The relayer rail decision also applies here.
