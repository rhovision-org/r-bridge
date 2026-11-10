# Development harness (planned)

The harness is for local development only. It must never be pointed at a network
holding real value.

## Contents (phase 1+)

- `devnet.py` / Make targets — start a local rholo devnet via `~/RNodeRust/tools/devnet.sh`,
  wait for it, install the bridge suite, and tear it down.
- `install.py` — render and deploy the rholo bridge terms; write `deployments/devnet.json`.
- `keys.py` — generate the dev rholo account and the 3 relayer keys.
- `mock_relayer.py` — a development relayer with the `spec/relayer-interface.md` HTTP
  shape: it watches the local Ethereum/Tron/Agoric mocks, signs with the dev keys, and
  serves attestations. It is deliberately single-process and fixed-key; it is not the
  node add-on and is not production.
- `suites/` — behavioural suites: install, mint (threshold/refusal/replay/cap/pause),
  burn, transfer, conservation, digest conformance.

## Commands (to be implemented)

```
make devnet-up
make keys
make install
make unit-all
make down
```

Until phase 1, this directory is a design placeholder; no harness code is claimed to
work.
