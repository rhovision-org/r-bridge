# Node operator guide

**This guide is provisional.** The relayer rail is undecided: a standalone relayer/bridge
node, a rholo node plugin/sidecar, or a hybrid. The hardware, key separation, monitoring
and incident rules apply to either shape; packaging and trust anchoring do not. The
node-side proposal is [rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563).

Nothing in this chapter describes software you can run in production today. The only
implemented relayer is the development harness in [Relayer](relayer.md).

## What the relayer does

It watches Cosmos/Agoric, Ethereum and Tron; waits for finality; signs the r-bridge
attestation digest; submits rholo mint deploys; and broadcasts native unlocks for rholo
burns. It has no custody of user keys and never uses a validator key.

## Hardware

These are planning estimates for the proposed rail, not measurements of this repository.

| Profile | CPU | RAM | Disk | Network |
|---|---|---|---|---|
| Sidecar with hosted RPC | 2 vCPU | 4 GB | 50 GB SSD | 10 Mbps |
| + self-hosted Ethereum | 4–8 cores | 32 GB (64 rec.) | 2–4 TB NVMe | 50/15 Mbps |
| + self-hosted Tron | 16 cores | 32 GB | 3–4 TB NVMe | 100 Mbps |
| + self-hosted Agoric | 8 cores | 16 GB | 250 GB SSD | ~20 Mbps |

All self-hosted: ~16–24 cores, 64–96 GB RAM, 6–9 TB NVMe, ~$600–1,100/month. Hosted-RPC
profile: ~$50–300/month. Do not co-locate the relayer with a 4 GB `rnode` host; the public
testnet has already throttled at ~547 MiB headroom on 4 GB.

Sources: [EIP-7870](https://eips.ethereum.org/EIPS/eip-7870),
[Ethereum launchpad](https://launchpad.ethereum.org/en/checklist),
[Tron node deployment](https://developers.tron.network/docs/deploy-the-fullnode-or-supernode),
[Tron 2026 requirements](https://powerdedi.com/blog/tron-node-requirements),
[Agoric hardware](https://services.validexis.com/mainnets/agoric/installation.md),
[Agoric validator guide](https://github.com/Agoric/agoric-sdk/wiki/Validator-Guide-for-Devnet).

## Economics

These figures are a proposal. The contracts currently accrue fees to a treasury; there is
no relayer bond, no slashing and no per-epoch fee distribution.

- 5 bps deposit + 5 bps withdrawal (10 bps round trip), governance-configurable, proposed
  to be split among active relayers. Fees only on successful flows.
- A relayer bond (illustrative $50k–$250k in REV/stablecoin) with slashing for provable
  misbehaviour; the bond could be delegated/staked while locked.
- Increased phlo volume for validator operators, fee revenue, governance seats and a
  differentiated service.
- Break-even illustration at 10 bps and a 3-way split: hosted-RPC operator
  ~$0.9–1.8M/month total volume; all self-hosted ~$3–4.5M/month. At $10M/month each
  operator earns ~$3.3k; at $100M/month ~$33k.

What exists on-chain today: the rholo fee bucket and the 2-of-3 `withdrawFees` sweep to a
treasury fixed at deployment; the vault's treasury-gated native fee withdrawal. There is
no distribution to relayers.

## Keys

- Separate **attestation** and **deploy/phlo** keys. Encrypted at rest or in an HSM.
- Never the validator key. Never shared between operators.
- The on-chain relayer and admin sets are **fixed at deployment**. Unlike the planned
  production suite, the current `Bridge` demo contract and vault have no on-chain set
  update: changing a key means redeploying the contract or starting a new bridge id,
  unless a governance path is added first.
- The admin set is a governance multisig, not an individual operator.

## Running

There is no packaged production binary. The development loop is in
[Relayer](relayer.md). The proposed production steps for either rail:

1. Fund the deploy account with REV; confirm the node's shard id and phlo price.
2. Register the attestation pubkey in the bridge set at deployment (governance).
3. Start the relayer with the config in [Relayer interface](reference/relayer-interface.md);
   point it at the node's public API.
4. Expose `/health` and `/metrics` only to the monitoring network; never expose signing
   keys or an attestation-signing endpoint publicly.
5. Watch the actual implemented metrics: `rbridge_chain_head`,
   `rbridge_deposits_total`, `rbridge_withdrawals_total`, `rbridge_reorgs_total`,
   `rbridge_errors_total` and `rbridge_halted`, plus RPC latency and chain-head lag.
6. Alert on any chain RPC failure, on `rbridge_halted 1`, and on `reorg` errors.

## Incident runbook

- **RPC unhealthy / cursor ambiguous**: stop signing; do not guess.
- **Reorg before signing**: rewind the cursor and drop the work.
- **Reorg after signing**: pause the bridge via governance, do not reuse the id, reconcile
  with the native chain, publish an incident note.
- **Failed deposit**: keep the journal entry; use the vault's 2-of-3 refund path; do not
  manually re-mint under a new id.
- **Key compromise**: there is no on-chain rotation in the current contracts. Pause,
  redeploy or move to a new bridge id, rotate the key set, and audit everything the key
  signed.
- **Bridge pause**: new deposits/mints fail closed; burns, refunds and in-flight unlocks
  remain available.
