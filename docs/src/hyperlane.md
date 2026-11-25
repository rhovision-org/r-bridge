# Hyperlane on rholo

Hyperlane's Mailbox, ISM, hook and Router interfaces are a set of on-chain interoperability
standards, not an EVM-only product. r-bridge implements those standards **as Rholang
contracts**, so rholo is a Hyperlane endpoint and can be used as a Hyperlane bridge. The
off-chain Hyperlane agent/bridge node is a later target; the on-chain half stands on its
own.

This chapter covers what is implemented, how it maps onto the standard, and what is not
done. The normative formats are in [Hyperlane reference](reference/hyperlane.md).

## Components

| Contract | Role |
|---|---|
| `hyperlaneMailbox` | public reads + `process`; dispatch is capability-gated |
| `hyperlaneDispatchDoor` | the dispatch capability; fixes the sender id |
| `hyperlaneMerkleTreeHook` | depth-32 tree; `root`, `count`, `latestCheckpoint` |
| `hyperlaneIsm` | module switch + `verify`/`moduleType` |
| `hyperlaneTestIsm` | switchable verdict for refusal tests (devnet only) |
| `hyperlaneTrustedRelayerIsm` | Hyperlane's TrustedRelayerISM |
| `hyperlaneMultisigIsm` | MessageIdMultisigISM, 2-of-3 in the demos |
| `hyperlaneRouter` | peer check, payload parse, mint capability, outbound dispatch |
| `HyperlanePeer` (EVM) | multi-asset ERC-20 lock/release; returns its application ISM |
| `RbridgeTrustedRelayerIsm` (EVM) | trusts the relayer the Mailbox records as processor |

The bridge arms live in `lib/Bridge.rho` and are shared by two deploy terms:

- `10_hyperlane.rho` — the suite alone, with a recording test recipient.
- `11_rbridge_hyperlane.rho` — the Bridge wired to the suite: inbound deposits mint through
  `bridgeHyperlaneMint`, and a burn dispatches the outbound withdrawal payload.

The EVM companion is `contracts/evm/src/HyperlanePeer.sol`, a standalone multi-asset
ERC-20 endpoint for Ethereum stables; the attested `BridgeVault` is unchanged. Its
`RbridgeTrustedRelayerIsm` is the EVM analogue of the rholo trusted module, so the same
dev relayer can carry messages in both directions before the rholo agent exists.

## Ethereum stables

The first route is Ethereum USDT and USDC (6 decimals, scale 1). The peer locks the token
on the EVM side, and the rholo Bridge mints/credits the chain-qualified wrapped balance
(`ethereum.usdt`, `ethereum.usdc`). `configs/networks/ethereum-sepolia-hyperlane.json`
pins the canonical Sepolia Mailbox and the Sepolia test USDC/USDT addresses; mainnet is
refused until the audit. On Anvil, `make hyperlane-stables-e2e` runs both assets through
lock → mint → burn → release with the same message and payload bytes a Sepolia deployment
uses.

## Flows

```
EVM peer ──lock + dispatch──► relayer ──process──► rholo Mailbox
                                                    │ ISM (test/trusted/multisig)
                                                    │ Router.handle (peer + payload)
                                                    │ bridgeHyperlaneMint
                                                    ▼
                                               wrapped balance

rholo Bridge.burn ──► Router.dispatchWithdrawal ──► Mailbox.dispatch
                                                    │ merkle hook
                                                    ▼
                                               EVM peer.handle → release
```

The Mailbox's public surface follows the alt-VM guide: `localDomain`, `nonce`,
`latestDispatchedId`, `delivered`, `processor`, `processedAt`, `dispatched`,
`quoteDispatch`, `defaultIsm`, `defaultHook`, `requiredHook` and `process`. `process` is
permissionless; the ISM decides. A refused delivery leaves no record. Dispatch is not
public: the door fixes the configured sender id and only the Router holds it.

## Mapping to the standard

- Message version 3, 77-byte header, `id = keccak256(message)`.
- Checkpoint digest: `eth_sign(keccak(keccak(origin ‖ merkleTree ‖ "HYPERLANE") ‖ root ‖
  index ‖ messageId))`.
- ISM metadata: `originMerkleTree(32) ‖ root(32) ‖ index(4) ‖ signatures(65 × m)`.
- TrustedRelayerISM: `processor(messageId) == trustedRelayer`; the processor is
  `keccak256(caller pubkey)`.
- MultisigISM: compact `r‖s‖v` signatures are converted to DER and counted by
  `Guard.rho`; each validator counts once.
- Payload: `rbridge:hyperlane:v1|action|assetKey|amount|recipient|externalId|nonce`.

## Commands

```bash
make devnet-up                # local rholo devnet
make hyperlane-demo           # suite alone; 59 checks
make hyperlane-bridge-demo    # wired Bridge (USDT + USDC); 35 checks
make hyperlane-stables-e2e    # Anvil USDT/USDC lock -> mint -> burn -> release; 22 checks
make hyperlane-peer-demo      # peer deployment rehearsal on its own Anvil; 12 checks
make evm-test                 # 25 Foundry tests (15 peer + 10 vault)
cargo test -p rbridge-core hyperlane

# Sepolia (funded key + operator env; mainnet is refused)
make deploy-hyperlane-sepolia
make verify-hyperlane-sepolia

cargo run -p rbridge-cli -- hyperlane message --nonce 7 --origin 11155111 \
  --sender 0x… --destination 84532 --recipient 0x… --body 'rbridge:hyperlane:v1|…'
```

The demos write `.devnet/hyperlane.json` and `.devnet/hyperlane_bridge.json`. The CLI's
`hyperlane` subcommands are the shared oracle: `message`, `checkpoint`, `payload`,
`parse-message`, `parse-metadata` and `processor`.

## Current limits

- **No rholo agent.** rholo is not on the live Hyperlane network. The contracts conform to
  the standard and pass local/golden tests; the rholo-side agent/bridge node is the
  longer-term work. Do not describe this as live interoperability.
- **Sepolia is prepared, not broadcast.** The peer profile and tooling are rehearsed on
  Anvil; no public-testnet deployment has been performed. Mainnet is refused.
- **Dev relayer only.** `hyperlane-stables-e2e` plays the relayer in-process. The EVM side
  uses `RbridgeTrustedRelayerIsm` and the rholo side uses the trusted module; production
  needs the rholo agent and a real validator/ISM policy.
- **Static routes and validator set.** `byDomain`/`routes` and the validators are set at
  install; there is no runtime enrolment or rotation arm. The ISM mode switch is a devnet
  arm.
- **Term size.** The wired term is about 56 KiB unrendered and about 60 KiB rendered: under
  the node's 64 KiB cap but over the 56 KiB planning budget. Splitting the suite and the
  Bridge into separate terms with a registry-carried capability is the next size step.
- **ERC-20 only.** The peer supports ERC-20 stables; native-ETH is not implemented.
- **Provisional domain.** The devnet domain is `9999`, not a registered Hyperlane domain.
- **Devnet only.** No mainnet, no Tron, no Agoric, no economic security.
