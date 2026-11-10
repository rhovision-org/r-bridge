# Tron vault (planned)

The Tron leg reuses the Ethereum vault's Solidity source compiled for TVM. TronLink
signs user transactions; TronGrid (or a self-hosted Tron node) supplies reads and logs.

## Differences from Ethereum

- TRC-20 `approve`/`transferFrom` and TRX are the assets. USDT TRC-20 is the volume
  anchor; USDC TRC-20 is enabled where the token exists.
- TVM `ecrecover` accepts the same `(r,s,v)` signature over the same digest. The vault
  must not use `personal_sign`/EIP-191.
- Event/log pagination and confirmation depth differ: 19 blocks for solidity, 64 for
  conservative operation.
- Energy/bandwidth costs are part of the user's lock transaction; the dApp estimates
  them through TronLink.

## Deployment

Nile first. Record the contract address, deployment block and the TRC-20 addresses in
`deployments/`. Verify the source with the Tron explorer. No mainnet before audit.

## Tests

The same digest vectors and threshold/replay/pause tests as the EVM vault, run on a
local Tron node or Nile. TronLink signing is tested in the web e2e phase.
