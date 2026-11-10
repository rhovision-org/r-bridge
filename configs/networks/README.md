# Network profiles

A profile is the complete input to one native-vault deployment. `tools/deploy_evm.py`
validates it, deploys from it, reads the result back from the chain and writes a manifest
to `deployments/`.

| Field | Meaning |
|---|---|
| `network` | rholo network id written into the vault (must match the rholo bridge) |
| `chainName` | chain qualification (`ethereum`, `tron`) |
| `chainId` | the chain id the tool checks against the RPC before broadcasting |
| `bridgeId` | the logical bridge id shared with the rholo bridge |
| `rpc` | JSON-RPC endpoint; use `${ENV_VAR}` for anything but localhost |
| `deployerKeyEnv` | environment variable holding the deployer private key |
| `mainnet` | `true` triggers the audit gate refusal (chain ids 1 and Tron mainnet also do) |
| `admins` / `adminThreshold` | 2-of-3 admin set |
| `relayers` / `relayerThreshold` | m-of-n relayer set |
| `treasury` | fee recipient |
| `assets[]` | `assetKey`, `token` (`native` or an address), `nativeDecimals`, `rholoDecimals`, `maxDeposit`, `maxLocked` (native base units), `withdrawFeeBps` |

Any string may reference an environment variable as `${NAME}`; a missing variable stops
the deploy before it touches the network. Never put a private key in a profile.

`anvil.json` uses the public Anvil accounts, which are worth nothing. `ethereum-sepolia.json`
takes every operator-specific value from the environment. Neither has been broadcast to a
public testnet yet.

```bash
python3 tools/deploy_evm.py deploy --profile configs/networks/ethereum-sepolia.json --dry-run
```
