# Deploy terms

Phase 1 writes the installer and deploy terms here:

- `00_bridge_root.rho`
- `10_wrapped_token.rho`
- `20_bridge.rho`

Each term is rendered from a template with the network, admin set, relayer set,
threshold, asset registry and fee/cap parameters. Generated terms are measured against
the 56 KiB budget and parsed with the target node before they are committed.
