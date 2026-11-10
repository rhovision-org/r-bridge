# Deployments

Generated manifests live here and are gitignored except this file. Each network
gets one manifest recording:

- the rholo bridge root URI and per-asset wrapped-token URIs;
- the Ethereum/Tron vault address per asset and the deployment block;
- the Agoric vat address / instance handle and IBC denoms;
- the relayer pubkey set and threshold;
- fee, cap and pause parameters.

Nothing in this directory is hand-edited after generation; the build/install tools
write it. The first manifests will be produced in the contracts phase.
