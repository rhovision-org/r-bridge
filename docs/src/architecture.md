# Architecture

r-bridge is a bridge dApp and a set of reusable primitives. It is **not** a wallet:
native-chain accounts stay in MetaMask (Ethereum), TronLink (Tron) and Keplr
(Cosmos/Agoric). The only key it manages is the rholo account, because the node's deploy
signature is not something those wallets can produce.

```
 MetaMask / TronLink / Keplr          r-bridge web (React)
        │  sign native tx                  │  rholo reads/deploys (WASM keystore)
        ▼                                  ▼
 Ethereum / Tron / Agoric  ◄────►  rholo bridge contracts
   vaults / Agoric vat              BridgeRoot · WrappedToken · Bridge · Attestation
        ▲                                  ▲
        │  unlock tx / vat offer           │  mint deploy
        └──────────── rholo node relayer add-on ────────────┘
                       (optional, node-operator sidecar)
```

## Components

| Component | Location | Responsibility |
|---|---|---|
| `rbridge-core` | `crates/rbridge-core` | chains, chain-qualified assets, amount scaling, deposit/withdrawal ids, relayer set, attestation digest |
| `rbridge-chain` | `crates/rbridge-chain` | rholo node seam over the pinned r-cash client |
| `rbridge-sdk` | `crates/rbridge-sdk` | portfolio and flow types, relayer API trait, connected client |
| `rbridge-cli` | `crates/rbridge-cli` | node status, registry, digest |
| `rbridge-wasm` | `crates/rbridge-wasm` | rholo key, REV address, digest signing, scaling for the web app |
| web | `web/` | wallet connectors, portfolio, bridge/withdraw forms, activity |
| rholo contracts | `contracts/rholo` | the canonical bridge suite |
| native contracts | `contracts/{evm,tron,agoric}` | vault / TVM vault / Agoric vat |
| node add-on | external | watchers, attestation signers, mint/unlock submission |

## Identities

- **Native account**: owned by the wallet. The dApp requests signatures; it never sees
  the key.
- **rholo account**: a secp256k1 key in the WASM module, stored as an encrypted Web3 v3
  keystore in IndexedDB. It signs rholo deploys and pays phlo. It is portable to/from
  r-wallet and the r-gen/r-cash clients.
- **Relayer key**: owned by the node add-on; signs the 32-byte attestation digest. It is
  not the validator key and not the deploy key.

A bridge transfer binds a native depositor to a rholo recipient (deposit) or a rholo
holder to a native recipient (withdraw). The keys do not need to be the same.

## Trust boundaries

- The wallets are trusted for native signatures only; the dApp explains every
  transaction before the wallet prompt.
- The rholo node is trusted for reads and finality; a second node or the relayer can
  cross-check.
- Relayers are trusted as an m-of-n set. The rholo contract and native vaults verify the
  threshold on-chain, so a single compromised relayer cannot mint or unlock.
- The Agoric vat is a smart contract on the Cosmos side; its correctness is part of the
  bridge's trust surface. ERTP/OCapN is the substrate, not a replacement for
  attestation.

## State

rholo holds the authoritative wrapped ledger: per-asset `totalSupply`, holder balances,
processed deposit ids, withdrawal receipts, fees, caps and pause. Native chains hold the
backing assets in a vault (Ethereum/Tron) or an Agoric vat account. The relayer holds
only a journal of observations; it has no custody.

## Repository map

See `README.md` for the full map. The Rust workspace is deliberately small: the
production relayer is the node add-on, not a crate here. `harness/` contains the
development devnet and the mock relayer.
