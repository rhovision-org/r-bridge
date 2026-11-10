## Summary

`r-bridge` is a bridge dApp that will move assets between rholo and Cosmos/Agoric, Ethereum and Tron (USDT/USDC/DAI where each chain has them; Hyperliquid later). The rholo side can lock, mint, burn and verify signatures in rholang, but it cannot watch foreign chains or broadcast foreign transactions. Today that job has no owner in the node stack.

This issue proposes an **optional bridge-relayer add-on for node operators**: a sidecar (later an optional `rnode` subcommand) that watches the supported foreign chains, signs m-of-n deposit/withdrawal attestations, submits rholo mint deploys, and broadcasts native unlocks. It changes no consensus rules and never uses the validator key. Operators choose to run it.

## Why node operators should own it

- Relaying is infrastructure work: a funded rholo account, reliable RPC, persistent state, 24/7 monitoring — the operational profile of a node operator.
- A federated set of independent operators is the security model: m-of-n attestations are verified on-chain by rholo and by the native vaults.
- Operators already earn from phlo/validation; a bridge fee adds revenue and drives transaction volume.

## What the node already provides

- ERTP at genesis (`rho:rchain:ertp`, `casper/src/genesis/resources/ERTP.rho`), with native mint/withdraw/deposit.
- OCapN listeners and ERTP interop (issues #249–#256).
- `rho:crypto:secp256k1Verify` (32-byte prehash, DER signature, 65-byte pubkey) and `keccak256Hash`.
- HTTP deploy/status/finality/data-at-name APIs, `GET /api/is-finalized/{blockHash}`, 64 KiB deploy cap, 50-block lifespan.

## Proposal

A sidecar binary (working name `rbridge-relayer`) shipped alongside `rnode`; later an optional `rnode relayer` subcommand if operators prefer one package.

Responsibilities:

1. Watch Cosmos/Agoric, Ethereum and Tron for vault/vat deposits; wait for finality.
2. Sign the canonical r-bridge attestation digest; expose signatures to the bridge/app.
3. Submit rholo `mint` deploys (or return signatures for user submission) and track finality.
4. Watch rholo burn records; sign and broadcast native unlocks; handle reorgs and idempotency.
5. Persist a SQLite journal; expose Prometheus metrics/health; support encrypted keys or an HSM.

Non-goals: no consensus changes; no validator-key reuse; no custody of user keys; no token policy (the bridge contracts own policy).

Requested from the node project:

- Agree on and document the sidecar lifecycle, and supply packaging (systemd/Docker).
- Optional `rnode relayer` subcommand or feature flag.
- On-chain relayer registration and fee-distribution hooks (the bridge contract can own these; the node should not hardcode them).
- Promote/harden OCapN + ERTP for the Cosmos/Agoric leg.
- Any missing read APIs for finalized deposit/withdraw queries; otherwise use the existing endpoints.
- Operator docs: key separation, firewalling, RPC providers, reorg/pause runbooks.

## Hardware estimate for a relay

Sidecar with hosted RPC is the baseline. Self-hosted chain nodes are optional but improve trust and independence.

| Profile | CPU | RAM | Disk | Network | Notes |
|---|---|---|---|---|---|
| Relayer sidecar only, hosted RPC | 2 vCPU | 4 GB | 50 GB SSD | 10 Mbps | SQLite + metrics; RPC subscription |
| + self-hosted Ethereum full node | 4–8 cores | 32 GB (64 rec.) | 2 TB min / 4 TB NVMe | 50/15 Mbps | EIP-7870 |
| + self-hosted Tron FullNode | 16 cores | 32 GB | 3–4 TB NVMe | 100 Mbps | SR node 32 cores / 64 GB |
| + self-hosted Agoric full node | 8 cores | 16 GB | 250 GB SSD | ~20 Mbps | 6–12 GB/month growth |
| All self-hosted | ~16–24 cores | 64–96 GB | 6–9 TB NVMe | 200 Mbps | split across hosts; do not co-locate with a 4 GB rnode |

Cloud cost ranges: sidecar $20–40/month; Ethereum full node $200–400; Tron $300–500; Agoric $80–150 → **$600–1,100/month per operator self-hosting all three**, or **$50–300/month** with hosted RPC. Co-locating the relayer with a 4 GB `rnode` host is not recommended (the public testnet has already throttled at ~547 MiB headroom on 4 GB hosts).

Sources: [EIP-7870](https://eips.ethereum.org/EIPS/eip-7870), [Ethereum launchpad checklist](https://launchpad.ethereum.org/en/checklist), [Tron node deployment](https://developers.tron.network/docs/deploy-the-fullnode-or-supernode), [Tron 2026 requirements](https://powerdedi.com/blog/tron-node-requirements), [Agoric mainnet hardware](https://services.validexis.com/mainnets/agoric/installation.md), [Agoric validator guide](https://github.com/Agoric/agoric-sdk/wiki/Validator-Guide-for-Devnet).

## Economic incentive to run a relay

- **Bridge fee:** 5 bps deposit + 5 bps withdrawal (10 bps round trip), configurable by governance, accrued to a bridge treasury and distributed pro-rata to active relayers per epoch. Fees only on successful flows.
- **Bond + slashing:** each relayer posts a bond (illustrative $50k–$250k in REV or a stablecoin) on rholo. Provable misbehaviour (conflicting attestations, invalid mint, double-unlock) is slashed. The bond can be delegated/staked while locked, so it earns REV yield.
- **Node-operator upside:** increased phlo volume for validators, fee revenue, governance seats, and a differentiated service offering. Testnet bootstrap can be grant-funded.
- **Break-even illustrations** (10 bps round trip, 3-way split): hosted-RPC operator ~$0.9–1.8M/month total bridge volume; all self-hosted ~$3–4.5M/month. At $10M/month each operator earns ~$3.3k; at $100M/month ~$33k.

Incentives must not pay per attestation regardless of correctness; slash for fraud; caps and pause bound exposure.

## Security and operations

- m-of-n independent operators; separate attestation key and deploy/phlo key; never the validator key; encrypted keystore or HSM.
- Confirmation depths: Ethereum `finalized`/64 confirmations; Tron 19–64 blocks; Agoric IBC finality; rholo finalized + `ProcessedWithSuccess` + `(true, …)`.
- Caps, 2-of-3 pause, bond/slashing, monitoring, reorg and incident runbooks.
- External audit before any mainnet value.

## Boundary with r-bridge

r-bridge owns the rholo bridge contracts, the native vault/vat contracts, the attestation format, the web dApp and the Rust core/CLI/WASM primitives. It will ship a **development mock relayer** in its harness. Production relaying is this node add-on. The attestation spec and the add-on interface will be versioned in the r-bridge repo so both sides can implement against one contract.

## Open questions

- Sidecar vs `rnode relayer` subcommand; packaging preference.
- Relayer registration: on-chain set vs config file; governance update flow.
- Fee distribution: bridge treasury vs node-level accounting.
- Minimum independent operators and bond sizing.
- Whether OCapN replaces any relayer path for Agoric or remains a notification/read transport.

The companion app repository will follow at `rhovision-org/r-bridge`; this issue is raised first because the app depends on this add-on for production operation.
