# Tron / TVM vault

The Tron leg reuses `../evm/src/BridgeVault.sol`. It is compiled for TVM and deployed with
TronBox or TronWeb; the source deliberately avoids `block.chainid` and EVM-only opcodes,
so the only differences are deployment parameters and the recipient encoding.

## Deployment parameters (Nile first)

| Parameter | Value |
|---|---|
| `chainTag` | `2494104990` (Nile) |
| `chainName` | `"tron"` |
| `bridgeId` | the same logical id as rholo, e.g. `rbridge:devnet:bridge` |
| asset keys | `tron.trx`, `tron.usdt`, `tron.usdc` |
| native token | `address(0)` for TRX |
| TRC-20 tokens | USDT `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t` on mainnet; the Nile test token or a harness mock |
| admins / relayers | 3 / 3, thresholds 2 / 2 |
| treasury | the same governance treasury as the other rails |

TronLink signs user `lock`/`approve` transactions; TronGrid (or a self-hosted Tron node)
supplies reads and logs. Confirmation depth is 19 blocks for solidity and 64 for
conservative operation.

## Recipient canonicalization

The canonical withdrawal message uses a lowercase `0x` 20-byte address, not the base58
display form. When a user burns on rholo with a Tron destination, the burn record must
store the lowercase `0x` form; the relayer uses it in the digest. The dApp converts
TronLink's base58 address with `tronWeb.address.toHex(address).toLowerCase()` before
building the burn.

## Compile and test

```bash
forge build --root contracts/evm          # EVM ABI + bytecode from the shared source
forge test --root contracts/evm -vv       # digest/threshold/replay/pause tests
```

For TVM-specific verification, compile with the TronBox solc version and run the same
tests against a local Tron node or Nile in the phase-2 testnet pass. The Tron deployment
manifest records the contract address, deployment block, TRC-20 addresses and energy
estimates.

## Status

Source reuse and the digest are tested on EVM. The dApp now builds and signs the TRX and
TRC-20 `approve` + `lock` calls through TronLink, derives the rholo address from the Tron
account, and reads balances; its calls are covered by unit tests with a TronWeb stub and
a Playwright browser spec. Tron deployment, TVM tests, the Tron watcher and Tron
withdrawals are still pending a local Tron node/Nile pass; no mainnet deployment before
the audit.
