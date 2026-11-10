# Ethereum vault (planned)

A per-asset vault (or one registry contract with per-asset accounting) deployed to
Sepolia first. MetaMask signs every user transaction; the relayer signs only unlock
digests.

## Interface

```solidity
function lock(bytes32 assetId, uint256 amount, bytes32 rholoRecipient, uint256 nonce)
    external returns (bytes32 depositId);

function unlock(bytes32 assetId, address to, uint256 amount, bytes32 withdrawalId,
                bytes[] calldata signatures) external;

function setRelayers(address[] calldata signers, uint256 threshold) external; // admin
function pause() external; // admin; unpause is 2-of-3
```

- `lock` pulls an ERC-20 with `SafeERC20` (or accepts ETH) and emits
  `Deposit(depositId, assetId, sender, amount, rholoRecipient, nonce)`.
- `unlock` verifies m-of-n secp256k1 signatures over the r-bridge digest with
  `ECDSA.recover(digest, v, r, s)`, marks `withdrawalId` used, and transfers.
- Admin is a 2-of-3 set; no upgradeable proxy in v1 (redeploy + drain if a fix is
  needed).
- Fees and caps are read from the registry; pause blocks new locks, not unlocks.

## Events

`Deposit`, `Unlock`, `RelayerSetChanged`, `Paused`, `FeeUpdated`. The relayer indexes
`Deposit`; the dApp reads balances and status through the wallet/provider.

## Tests

Foundry: digest golden vector, threshold, duplicate signer, replay, wrong chain, cap,
pause, dust/scale boundary, reentrancy (nonReentrant on lock/unlock), fee accounting.
No mainnet deployment before an external audit.

Addresses and the deployment block are recorded in `deployments/`.
