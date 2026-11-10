# r-bridge

`r-bridge` is a bridge application and reusable primitive set for **rholo**. It moves
assets between rholo and Cosmos/Agoric, Ethereum and Tron, and shows balances on both
sides. It is not a wallet: native accounts stay in MetaMask, TronLink and Keplr.

| Question | Answer |
|---|---|
| **What is it?** | A bridge dApp + Rust primitives for rholo. |
| **Which chains?** | Cosmos/Agoric, Ethereum, Tron first; Hyperliquid later. Bitcoin is deferred. |
| **Which assets?** | Native assets plus USDT/USDC/DAI where each chain has them, chain-qualified. |
| **What is the trust model?** | Federated m-of-n relayers (2-of-3 to start), run by rholo node operators. |
| **What does it depend on?** | An optional relayer add-on for the rholo node: [issue #563](https://github.com/rhovision-org/rholo/issues/563). |
| **Status** | **Scaffold.** Contracts are not deployed; no real value moves. |

## Wallets

r-bridge uses what the user already has:

- **MetaMask** for Ethereum accounts, network switching, approvals and vault calls.
- **TronLink** for Tron accounts and TRC-20 calls.
- **Keplr** for Cosmos/Agoric accounts and Zoe/IBC offers.
- **r-bridge's own WASM keystore** only for the rholo account, because MetaMask cannot
  sign the node's deploy preimage (BLAKE2b-256 protobuf, `shardId` field 11,
  `{prehash:false}`).

## Dependency on the rholo node

A bridge needs someone to watch foreign chains, attest deposits, submit rholo mints and
broadcast native unlocks. That is an optional add-on for node operators, proposed in
[rhovision-org/rholo#563](https://github.com/rhovision-org/rholo/issues/563). r-bridge
develops against a mock relayer; production relaying is the node add-on.

## Repository map

| Area | Path |
|---|---|
| Rust primitives | `crates/rbridge-{core,chain,sdk,cli,wasm}` |
| Web dApp | `web/` |
| Rholang bridge suite (planned) | `contracts/rholo/` |
| Native vaults/vat (planned) | `contracts/{evm,tron,agoric}/` |
| Dev harness (planned) | `harness/` |
| Specs | `spec/` |
| Book | `docs/` |
| Network configs | `configs/` |
| Generated deployment manifests | `deployments/` |

## Quick start

```bash
cargo test --workspace
cargo check -p rbridge-wasm --target wasm32-unknown-unknown
npm --prefix web install
npm --prefix web run dev
(cd docs && mdbook serve)
```

`make check` runs the Rust, web and docs gates.

## Documents

- `spec/attestation.md` — the cross-chain message and signature format.
- `spec/assets.md` — the initial asset registry and amount scaling.
- `spec/invariants.md` — conservation, idempotency, auth and finality rules.
- `spec/relayer-interface.md` — the boundary between r-bridge and the node add-on.
- `docs/src/architecture.md`, `docs/src/flows.md`, `docs/src/roadmap.md`.

## License

AGPL-3.0-only. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
