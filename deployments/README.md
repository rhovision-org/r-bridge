# Deployments

Generated manifests live here and are gitignored except this file. They are written by
`tools/deploy_evm.py` after a vault deployment, from values read back off the chain — not
from the input profile. Do not hand-edit a manifest; `verify` detects edits.

One file per network (`deployments/<network>.json`), schema `rbridge.deployment.v1`:

```json
{
  "schema": "rbridge.deployment.v1",
  "createdAt": "2026-11-10T00:00:00Z",
  "profile": "configs/networks/ethereum-sepolia.json",
  "network": "rbridge-sepolia",
  "chain": "ethereum",
  "chainId": 11155111,
  "bridgeId": "rbridge:sepolia:bridge",
  "contract": {
    "name": "BridgeVault",
    "address": "0x…",
    "txHash": "0x…",
    "deployBlock": 1234567,
    "deployer": "0x…",
    "runtimeCodeKeccak": "0x…"
  },
  "admins": ["0x…", "0x…", "0x…"],
  "adminThreshold": 2,
  "relayers": ["0x…", "0x…", "0x…"],
  "relayerThreshold": 2,
  "treasury": "0x…",
  "assets": [
    {
      "assetKey": "ethereum.eth",
      "token": "0x0000000000000000000000000000000000000000",
      "nativeDecimals": 18,
      "rholoDecimals": 8,
      "maxDeposit": "…",
      "maxLocked": "…",
      "scale": "10000000000",
      "withdrawFeeBps": 5
    }
  ]
}
```

The rholo bridge URI, Agoric instance handle and IBC denoms are recorded by their own
deployment steps; this manifest is the native vault record. Manifests never contain
private keys, RPC credentials or mnemonics.

```bash
make deploy-sepolia                     # needs the SEPOLIA_* environment variables
RBRIDGE_RPC_URL=… make verify-sepolia   # re-read the manifest against the chain
python3 tools/deploy_evm.py print-env --manifest deployments/<network>.json
```
