# Operator guide

**The relayer rail is undecided.** It may be a standalone relayer/bridge node, a
plugin/sidecar for the rholo node, or a hybrid. The final product depends on that
decision; the demo is being built in the meantime to inform it. The node-side proposal,
with the interface and the economics, is
[rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563).

This chapter is the operator summary for either rail. The hardware, key separation,
monitoring and incident rules are the same; only packaging and trust anchoring differ.

## What the relayer does

It watches Cosmos/Agoric, Ethereum and Tron; waits for finality; signs the r-bridge
attestation digest; submits rholo mint deploys; and broadcasts native unlocks for
rholo burns. It has no custody of user keys and never uses the validator key.

## Hardware

| Profile | CPU | RAM | Disk | Network |
|---|---|---|---|---|
| Sidecar with hosted RPC | 2 vCPU | 4 GB | 50 GB SSD | 10 Mbps |
| + self-hosted Ethereum | 4–8 cores | 32 GB (64 rec.) | 2–4 TB NVMe | 50/15 Mbps |
| + self-hosted Tron | 16 cores | 32 GB | 3–4 TB NVMe | 100 Mbps |
| + self-hosted Agoric | 8 cores | 16 GB | 250 GB SSD | ~20 Mbps |

All self-hosted: ~16–24 cores, 64–96 GB RAM, 6–9 TB NVMe, ~$600–1,100/month. Hosted-RPC
profile: ~$50–300/month. Do not co-locate with a 4 GB `rnode` host; the public testnet
has already throttled at ~547 MiB headroom on 4 GB.

Sources: [EIP-7870](https://eips.ethereum.org/EIPS/eip-7870),
[Ethereum launchpad](https://launchpad.ethereum.org/en/checklist),
[Tron node deployment](https://developers.tron.network/docs/deploy-the-fullnode-or-supernode),
[Tron 2026 requirements](https://powerdedi.com/blog/tron-node-requirements),
[Agoric hardware](https://services.validexis.com/mainnets/agoric/installation.md),
[Agoric validator guide](https://github.com/Agoric/agoric-sdk/wiki/Validator-Guide-for-Devnet).

## Economics

- 5 bps deposit + 5 bps withdrawal (10 bps round trip), governance-configurable, paid to
  a bridge treasury and split among active relayers. Fees only on successful flows.
- A relayer bond (illustrative $50k–$250k in REV/stablecoin) with slashing for provable
  misbehaviour; the bond can be delegated/staked while locked.
- Increased phlo volume for validator operators, fee revenue, governance seats and a
  differentiated service.
- Break-even at 10 bps and a 3-way split: hosted-RPC operator ~$0.9–1.8M/month total
  volume; all self-hosted ~$3–4.5M/month. At $10M/month each operator earns ~$3.3k; at
  $100M/month ~$33k.

## Keys

- Separate **attestation** and **deploy/phlo** keys. Encrypted at rest or HSM.
- Never the validator key. Never shared between operators.
- The on-chain relayer set and threshold live in `BridgeRoot` and each native vault;
  changing them is a 2-of-3 admin action.

## Running

1. Fund the deploy account with REV; confirm the node's shard id and phlo price.
2. Register the attestation pubkey in the bridge set (governance).
3. Start the relayer with the config in `spec/relayer-interface.md`; point it at the
   node's public API. The same config works for either rail.
4. Expose `/health` and `/metrics` only to your monitoring network; do not expose the
   signing keys or an attestation-signing endpoint to the public internet.
5. Watch `rbridge_pending`, `rbridge_errors_total`, chain head lag and confirmation
   depth. Alert on any chain RPC failure.

## Incident runbook

- **RPC unhealthy / cursor ambiguous**: stop signing; do not guess.
- **Reorg before signing**: rewind the cursor and drop the work.
- **Reorg after signing**: pause the bridge via governance, do not reuse the deposit id,
  reconcile with the native chain, publish an incident note.
- **Key compromise**: remove the key from the on-chain set via governance, rotate,
  audit all attestations it signed.
- **Bridge pause**: new deposits/mints fail closed; burns and in-flight unlocks remain
  available.
