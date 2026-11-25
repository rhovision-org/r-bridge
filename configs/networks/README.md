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

## Hyperlane peer profiles

`ethereum-sepolia-hyperlane.json` is the input to `tools/deploy_hyperlane_peer.py`. It
pins the canonical Sepolia Mailbox (`0xfFAEF09B3cd11D9b20d1a19bECca54EEC2884766`), the
rholo domain and peer, the relayer/owner, and the Sepolia test USDC/USDT (6 decimals).
Fields: `network`, `chainName`, `chainId`, `rpc`, `mailbox`, `localDomain`, `remoteDomain`,
`remotePeer` (32-byte hex), `relayer`, `owner`, `deployerKeyEnv`, and `assets[]` with
`assetKey`, `token`, `decimals`, `scale`, `maxDeposit`, `maxLocked`. Mainnet is refused;
a non-local chain needs `--yes`. The same `${ENV_VAR}` interpolation and key rules as the
vault profiles apply.
