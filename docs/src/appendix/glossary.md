# Glossary

| Term | Meaning |
|---|---|
| **rholo** | The RChain-derived chain this bridge targets; its node is `rnode` in this project's context. |
| **REV** | The rholo native token used for phlo. A REV address is derived from a secp256k1 public key, and a MetaMask address maps to one. |
| **phlo** | The compute/gas currency paid for rholo deploys. |
| **Deploy** | A rholo transaction: Rholang source plus signature. The bridge's mint, burn, admin and keystore operations are deploys. |
| **Bridge id** | A logical identifier shared by the rholo contract and every native vault; part of the attestation digest. |
| **Network id** | The rholo network a deployment targets; also part of the digest. |
| **Attestation** | The canonical message plus m-of-n signatures that authorises a mint or unlock. |
| **Deposit id** | An id derived from the native chain, vault, transaction and log index; consumed once by `mint`. |
| **Withdrawal id** | The rholo burn's identifier; consumed once by the native unlock. |
| **Safe head** | The chain height below which the relayer settles, based on confirmations or the finalized tag. |
| **Finality** | The point at which a native block or rholo deploy is considered irreversible enough to attest. rholo requires finalized + `ProcessedWithSuccess` + `(true, …)`. |
| **Dust** | A native amount that is not an exact multiple of the scale quantum; refused, never rounded. |
| **Scale** | Native base units per rholo base unit (1 for 6-decimal assets, 1e10 for 18→8). |
| **ERC-20 / TRC-20** | Fungible-token standards on Ethereum and Tron. |
| **TVM** | Tron Virtual Machine; the vault source is compiled for it. |
| **Zoe / ZCF** | Agoric's smart-contract framework and contract facet, used by the escrow vat. |
| **ERTP** | Agoric's electronic rights transfer protocol (issuers, purses, payments). |
| **IBC** | Inter-blockchain communication; how Cosmos assets such as Noble USDC reach Agoric. |
| **OCapN** | Object-capability networking; the proposed Cosmos/Agoric transport. |
| **Manifest** | The generated deployment record in `deployments/`, written from on-chain read-back. |
| **Profile** | The deployment input in `configs/networks/`; addresses may reference environment variables. |
| **Rollup / bundle** | Not used: the vault is not a proxy and has no upgrade path. |
