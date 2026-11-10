# Deployment

A bridge deployment has two sides: the **rholo bridge contract** and the **native
vault/vat** on each chain, joined by the same network id, bridge id and asset keys.

**Status (2026-11-10).** The rholo side is installed by the development harness on a local
devnet. The native-vault deployment path is tested against Anvil: `make deploy-demo` runs
23 checks covering a profile deploy, on-chain read-back, manifest verification, tamper
detection, an ERC-20 asset, and every refusal path. **No public-testnet deployment has
been performed.** Sepolia is prepared; Nile needs a TronWeb deployment pass; Agoric needs
a live chain, the Agoric CLI and IST for fees. Nothing here moves real value.

## rholo side

Today the bridge is installed by the harness:

```bash
make devnet-up          # local rholo devnet on :40403
make demo               # build the CLI, render + install the bridge, run 30 checks
make devnet-down
```

`harness/render.py` fills `contracts/rholo/build/00_bridge.rho` with the network id,
bridge id, admin and relayer sets, thresholds, treasury and asset registry. The installer
returns the registry URI, which lands in `.devnet/bridge.json` for the dApp and relayer.

There is no packaged production installer, no network-specific governance deployment
script, and no on-chain set-update path. The current contract is the single-contract demo;
the production `BridgeRoot`/`WrappedToken` split is planned. Deploying against a public
rholo network follows the same install term but needs a funded phlo account, a reviewed
rendering and an operator runbook that does not exist yet.

The deploy-term budget is 64 KiB inclusive with a 56 KiB planning budget; the current term
is about 15.5 KiB. `make contracts-check` enforces drift and the budget.

## Native vault deployment

`tools/deploy_evm.py` drives `contracts/evm/script/DeployVault.s.sol` from a profile in
`configs/networks/`. A profile is the complete input: chain id, rholo network id, bridge
id, admin/relayer sets and thresholds, treasury, RPC, deployer-key variable and the asset
registry. Any string may reference an environment variable as `${NAME}`; a missing
variable stops the deploy before any network call. Never put a private key in a profile.

`deploy`:

1. Validates the profile (addresses, thresholds, chain-qualified asset keys, decimals,
   caps, fees).
2. Refuses mainnet (chain ids 1 and Tron mainnet, or `"mainnet": true`). There is no
   override: no mainnet value before the external audit.
3. Refuses a non-local chain unless `--yes` is passed.
4. Compares the RPC's `eth_chainId` with the profile.
5. Checks every ERC-20: code exists and `decimals()` matches the profile.
6. Broadcasts the vault with the profile's parameters.
7. Reads every constructor parameter and asset config back from the chain and compares.
8. Writes a gitignored manifest to `deployments/<network>.json` with the address,
   transaction, deploy block, deployer, runtime-code hash and full configuration. The
   deployer key is never printed or persisted.

`verify` re-reads a manifest against the chain, including the deploy transaction (it must
have created that address at that block), the runtime-code hash and every parameter.
`print-env` turns a manifest into the web app's `VITE_RBRIDGE_*` settings.

### Profiles

| Profile | Use |
|---|---|
| `configs/networks/anvil.json` | Local chain 31337 with public Anvil accounts; used by `make deploy-demo` |
| `configs/networks/ethereum-sepolia.json` | Sepolia 11155111; every operator value from the environment |

The Sepolia profile ships with `${SEPOLIA_*}` references for the RPC, admin/relayer sets,
treasury and USDC token. The tool verifies any token's code and decimals before use, so a
wrong address fails loudly. `bridgeId` and `network` must match the rholo bridge; a
mismatch makes every digest disagree.

### Sepolia runbook

```bash
export SEPOLIA_RPC_URL=https://…
export SEPOLIA_DEPLOYER_KEY=0x…        # funded testnet key; never commit
export SEPOLIA_ADMIN_1=0x… SEPOLIA_ADMIN_2=0x… SEPOLIA_ADMIN_3=0x…
export SEPOLIA_RELAYER_1=0x… SEPOLIA_RELAYER_2=0x… SEPOLIA_RELAYER_3=0x…
export SEPOLIA_TREASURY=0x…
export SEPOLIA_USDC=0x…
export ETHERSCAN_API_KEY=…             # optional; enables source verification
```

Review without a key or a transaction, deploy, then verify:

```bash
python3 tools/deploy_evm.py deploy \
  --profile configs/networks/ethereum-sepolia.json --dry-run
make deploy-sepolia
RBRIDGE_RPC_URL="$SEPOLIA_RPC_URL" make verify-sepolia
python3 tools/deploy_evm.py print-env --manifest deployments/ethereum-sepolia.json
```

Testnet ETH comes from a faucet (account- or captcha-gated; see the README); Circle's
Sepolia faucet dispenses test USDC. Fees and caps in the profile are testnet values, not
calibrated production numbers.

### Manifests

`deployments/<network>.json` is generated, gitignored and never hand-edited. It records
the profile, chain id, contract address, transaction, deploy block, deployer, runtime-code
hash, admin/relayer sets and thresholds, treasury, and the full asset registry with
base-unit caps and scales. The schema is documented in `deployments/README.md`.

The development watcher still reads `.devnet/evm.json`; wiring manifests into the
production relayer belongs to the rail decision.

## Testnet status

| Rail | Testnet | Contract source | Deployment tooling | Status |
|---|---|---|---|---|
| Ethereum | Sepolia 11155111 | `contracts/evm` | `tools/deploy_evm.py` | Prepared; not broadcast |
| Tron | Nile 2494104990 | `contracts/evm` compiled for TVM | None yet (TronWeb/TronBox) | Source reuse and wallet calls only |
| Agoric | Devnet | `contracts/agoric` | None yet (Agoric CLI, IST fees) | Local vat tests only |

## Tron / Nile

The TVM leg reuses `BridgeVault.sol`. It avoids `block.chainid` and EVM-only opcodes, so
the differences are deployment parameters and recipient encoding. Nile needs:
`chainTag = 2494104990`, TRX as `address(0)`, the Nile USDT token, lowercase `0x`
recipients, and 19–64 block confirmation depth. There is no Tron deployment script yet;
the profile format and manifest are chain-agnostic and can be extended once a local Tron
node or Nile RPC is available. See `contracts/tron/README.md`.

## Agoric

The Zoe escrow/release vat is tested locally. Deploying it to an Agoric network needs the
Agoric CLI/wallet, IST for Zoe installation and offers, IBC denoms for USDC/ATOM, a
relayer that watches Agoric offers, durable baggage stores and an account/key binding for
the release invitation. None of that exists in this repository yet. See
`contracts/agoric/README.md`.

## Mainnet

Mainnet is refused by the tooling until the external audit is complete. Do not treat a
testnet run as evidence of mainnet readiness; the audit scope is in
[Security model](security.md).
