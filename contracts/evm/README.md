# Ethereum / TVM vault

`src/BridgeVault.sol` locks native ETH and ERC-20s, and releases them on an m-of-n
relayer attestation over the same canonical digest as the rholo contract. The same source
is intended to compile for TVM (Tron); see `../tron/README.md`.

## Design

- One vault per chain. Asset keys are chain-qualified (`ethereum.usdt`, `ethereum.eth`,
  `tron.usdt`, ...).
- **Deposit:** `lock(token, amount, rholoRecipient, nonce)` pulls an ERC-20 with
  `transferFrom` (or accepts native ETH with `msg.value == amount`), enforces the
  per-asset max deposit and max locked, consumes the sender's nonce, and emits
  `Deposit(depositId, token, sender, amount, rholoRecipient, nonce)`.
- **Withdraw:** `unlock(token, to, grossAmount, withdrawalId, nonce, signatures)`
  recomputes the canonical withdrawal digest, verifies `relayerThreshold` distinct
  relayer addresses, marks the withdrawal id used, converts the rholo-unit `grossAmount`
  with the asset's `scale`, computes the withdrawal fee in native units, releases
  `grossNative - fee`, and retains `fee` in `fees[token]`.
- **Admin:** `setPaused(value, nonce, signatures)` uses the same 2-of-3 admin payload as
  rholo: `rbridge:admin:v1|setPaused|<true|false>|<nonce>`. Pause blocks `lock`, not
  `unlock` or fee withdrawal.
- **Fees:** the treasury (a constructor argument) calls `withdrawFees(token, to, amount)`.
- **Refund:** `refund(token, to, amount, depositId, nonce, signatures)` is a 2-of-3 admin
  recovery path for a deposit that was never minted on rholo (for example below the rholo
  minimum). It returns the full locked amount, is one-shot per deposit id, and uses
  `rbridge:admin:v1|refund|<token>|<to>|<amount>|<depositId>|<nonce>`.
- **Relayer set and admin set are fixed at deployment.** Changing either is a redeploy.
  This is deliberate for the testnet demo; production can add a governed update path.

Security properties: no proxy, no external dependencies, low-s ECDSA only, duplicate
signers are not counted twice, nonReentrant on value-moving arms, safe ERC-20 calls, and
per-asset caps. The contract does not use `block.chainid`, so the same bytecode is
portable to TVM; the deployment supplies `chainTag`, `chainName` and `bridgeId`.

## Constructor

```solidity
BridgeVault(
  uint256 chainTag,          // 11155111 Sepolia; 2494104990 Nile (Tron)
  string network,            // "rbridge-devnet" / "mainnet"
  string chainName,          // "ethereum" / "tron"
  string bridgeId,           // logical bridge id, e.g. "rbridge:devnet:bridge"
  address[] admins,          // 3
  uint256 adminThreshold,    // 2
  address[] relayers,        // 3
  uint256 relayerThreshold,  // 2
  address treasury,
  AssetInit[] assets         // token, assetKey, maxDeposit, maxLocked, scale, feeBps
)
```

`token == address(0)` is native ETH. `maxDeposit`/`maxLocked` are in the token's native
base units. `scale` is native units per rholo base unit (`1` for 6-decimal assets,
`1e10` for 18→8); the canonical withdrawal digest carries the **rholo** amount and the
vault converts to native units for the transfer and fee.

## Canonical withdrawal digest

```
keccak256(utf8(
  "rbridge:v1|<network>|<chainName>|<bridgeId>|<assetKey>|withdraw|" +
  "<withdrawalId>|<grossRholoAmount>|<lowercase 0x address>|<nonce>"
))
```

The rholo burn must store the same lowercase `0x` recipient string for an EVM/Tron
destination. `nonce` is `0` by convention for withdrawals. Signatures are 65-byte
`r || s || v` over this digest (not `personal_sign`). The Rust signer produces DER for
rholo and the 65-byte form for the vault: `rbridge sign-text-eth --key … --text …` and
`rbridge sign-digest-eth --key … --digest …` (the latter is also useful to a relayer).
`rbridge key-info` reports the Ethereum address of a key alongside its REV address.

## Tests

```bash
forge test --root contracts/evm -vv
```

10 tests: ERC-20 lock/unlock, ETH lock/unlock with 18→8 scale, fee retention and treasury
withdrawal, 2-of-3 admin refund of a failed deposit (including replay and below-threshold
refusals), below-threshold/duplicate-signer/wrong-digest unlock refusals, pause blocks
lock but not unlock, admin threshold and replay, max deposit and nonce replay, and the
shared Rust/EVM withdrawal digest golden vector (`d2f0ca02…e805`).

The `script/DeployAnvil.s.sol` script deploys an ETH-only vault to local Anvil for the
cross-chain demo (`make e2e-evm`).

## Deployment

`script/DeployVault.s.sol` is the generic, environment-driven deployment used by
`tools/deploy_evm.py`. The tool takes a profile from `configs/networks/`, checks the
chain id, the ERC-20 code and decimals, broadcasts, reads every parameter back from the
chain, and writes a gitignored manifest to `deployments/`. `make deploy-demo` rehearses
the whole path on its own Anvil; `make deploy-sepolia` is the public-testnet command.
See `docs/src/deployment.md` and `configs/networks/README.md`.

Mainnet is refused by the tool until the external audit. No public-testnet deployment has
been performed yet.
