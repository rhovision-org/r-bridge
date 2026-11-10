# Deploying a native vault

The rholo side is installed by the harness (`make demo`). The native side is deployed by
`tools/deploy_evm.py`, which is driven by a profile in `configs/networks/` and writes a
manifest to `deployments/`.

**Status (2026-11-10).** The deployment path is tested against Anvil: `make deploy-demo`
runs 23 checks covering a profile deploy, on-chain read-back, manifest verification,
tamper detection, an ERC-20 asset, and every refusal path. **No public testnet deployment
has been performed.** Sepolia needs funded keys, operator addresses and a decision on who
holds the admin set; Nile additionally needs a TronWeb deployment pass (see
`contracts/tron/README.md`). Nothing here moves real value.

## What a deployment does

1. Resolves the profile, including `${ENV_VAR}` references. A missing variable stops
   before any network call.
2. Refuses mainnet (chain ids 1 and Tron mainnet, or `"mainnet": true`): no mainnet
   value before the external audit.
3. Refuses a non-local chain unless `--yes` is passed.
4. Compares the RPC's `eth_chainId` with the profile.
5. Checks every ERC-20 in the registry: code exists, and `decimals()` matches the
   profile.
6. Broadcasts `contracts/evm/script/DeployVault.s.sol` with the profile's parameters.
7. Reads every constructor parameter and asset config back from the chain and compares
   them with the profile.
8. Records the deployed runtime-code hash, deploy block and transaction in the manifest.
   The deployer key is never written or printed.

## Sepolia runbook

Prepare the operator values first. These are the addresses of the 2-of-3 admin set, the
2-of-3 relayer set, the treasury, and the testnet USDC token (verify its address and
decimals before using it).

```bash
export SEPOLIA_RPC_URL=https://…
export SEPOLIA_DEPLOYER_KEY=0x…        # funded testnet key; never commit
export SEPOLIA_ADMIN_1=0x… SEPOLIA_ADMIN_2=0x… SEPOLIA_ADMIN_3=0x…
export SEPOLIA_RELAYER_1=0x… SEPOLIA_RELAYER_2=0x… SEPOLIA_RELAYER_3=0x…
export SEPOLIA_TREASURY=0x…
export SEPOLIA_USDC=0x…
export ETHERSCAN_API_KEY=…             # optional; enables source verification
```

Review without a key or a transaction:

```bash
python3 tools/deploy_evm.py deploy \
  --profile configs/networks/ethereum-sepolia.json --dry-run
```

Deploy and verify:

```bash
make deploy-sepolia
RBRIDGE_RPC_URL="$SEPOLIA_RPC_URL" make verify-sepolia
```

Point the web app at the new vault:

```bash
python3 tools/deploy_evm.py print-env --manifest deployments/ethereum-sepolia.json
```

`bridgeId` and `network` must match the rholo bridge the vault talks to; a mismatch makes
every attestation digest disagree. Fees and caps in the profile are testnet values, not
calibrated production numbers.

## Manifests

`deployments/<network>.json` is generated, gitignored, and never hand-edited. It records
the profile, chain id, contract address, transaction, deploy block, runtime-code hash,
admin/relayer sets and thresholds, treasury, and the full asset registry with base-unit
caps and scales. `verify` re-reads all of it from the chain and fails on any drift,
including a hand-edited manifest.

The development watcher still reads `.devnet/evm.json`; wiring manifests into the
production relayer belongs to the rail decision (`infrastructure-decision.md`).

## Tron / Nile

The TVM leg reuses the same Solidity source but needs a TronWeb or TronBox deployment
and the Tron `chainTag` (2494104990 for Nile). There is no Tron deployment script yet;
the profile format and the manifest are chain-agnostic, so the EVM tool can be extended
once a local Tron node or Nile RPC is available.
