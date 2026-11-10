# Deploy terms

The current deploy term is one file:

- `00_bridge.rho` — the single-demo `Bridge` contract (mint, burn, transfer, balances,
  withdrawals, admin, fee sweep).

`tools/build_contracts.py` inlines the libraries from `../lib` and writes the generated
term to `contracts/rholo/build/00_bridge.rho`, which is committed and must not be
hand-edited. `harness/render.py` then fills the deployment placeholders (network, bridge
id, admin/relayer sets, thresholds, treasury, asset registry) at install time. The
generated term is measured against the 56 KiB budget and parsed with the target node in
the demo.

The production target is a split suite (`BridgeRoot.rho`, `WrappedToken.rho`,
`Bridge.rho`, `Attestation.rho`); it is not implemented yet. See
`../../README.md`.
