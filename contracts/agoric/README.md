# Agoric vat (planned)

Agoric is a Cosmos SDK chain; the Cosmos leg is a vat that holds IBC denoms and pays
out on attested burns. Keplr signs the user's deposit offer.

## Design

- The vat holds the canonical IBC assets (ATOM from the Cosmos Hub, USDC from Noble,
  USDT from a registered denom, IST native to Agoric) in its own account.
- A user deposits with a Zoe offer: `give` the IBC asset, `want` a receipt/record, and
  include the rholo recipient in the offer terms. The vat records the deposit and emits
  an event/offer result.
- The node relayer watches the vat/offer result and attests the deposit to rholo.
- On a rholo burn, the relayer submits a release offer to the vat; the vat verifies the
  m-of-n rholo burn attestation (secp256k1 in JS) and pays the destination Agoric
  address. The user can then IBC-transfer onward.
- ERTP is the token model on both sides; OCapN is the preferred transport for
  notifications/reads between the vat and rholo. The mint authority remains the m-of-n
  attestation, not a single vat capability.

## Assets

ATOM, IST, USDC (Noble IBC), USDT only when a denom is registered. Record the full IBC
denom in the deployment manifest; denoms are network-specific.

## Tests

Local Agoric chain with mocked IBC denoms first; then an Agoric testnet with Noble USDC.
Test deposit offer, attestation verification, release offer, duplicate suppression,
wrong denom, threshold refusal and conservation. OCapN integration is a phase-5
hardening item; the v1 path is relayer attestation.
