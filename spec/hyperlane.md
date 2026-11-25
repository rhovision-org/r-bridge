# Hyperlane v3 on rholo

Hyperlane is an interoperability standard expressed as on-chain interfaces. This document
defines the rholo/Rholang implementation: the message bytes, the message id, the
checkpoint digest, the ISM metadata, the r-bridge payload and the deployment conventions.
It is the cross-implementation contract for the Rholang Mailbox, the Rust oracle
(`crates/rbridge-core/src/hyperlane.rs`) and any EVM peer.

**Status.** The Mailbox, the depth-32 merkle hook, the test/TrustedRelayer/MessageIdMultisig
ISMs, the Router and the wired Bridge pass `make hyperlane-demo` (59 checks) and
`make hyperlane-bridge-demo` (31 checks) on a local devnet. The standalone EVM peer passes
11 Foundry tests. The rholo agent is not implemented, so nothing here is live-network
compatible yet and no mainnet value moves.

## Message

Version 3. Packed, no padding:

```
version        uint8    1 byte
nonce          uint32   4 bytes, big-endian
origin         uint32   4 bytes, big-endian
sender         bytes32  32 bytes
destination    uint32   4 bytes, big-endian
recipient      bytes32  32 bytes
body           bytes    the rest
```

The header is 77 bytes. Byte offsets: version 0, nonce 1, origin 5, sender 9,
destination 41, recipient 45, body 77.

```
message_id = keccak256(message)
```

`nonce` is the origin Mailbox's dispatch counter, incremented once per dispatch.
`localDomain` is immutable for a deployment. The sender is the dispatching contract's
configured 32-byte id, not the transaction caller.

## Checkpoint

Validators sign a checkpoint over the origin's merkle tree. The digest follows the
Hyperlane EVM `CheckpointLib`:

```
domain_hash    = keccak256(origin_u32_be || merkle_tree_bytes32 || "HYPERLANE")
checkpoint     = keccak256(domain_hash || root_bytes32 || index_u32_be || message_id)
digest         = keccak256("\x19Ethereum Signed Message:\n32" || checkpoint)
```

The EIP-191 prefix is literal ASCII. The first field is the origin merkle tree hook (the
Hyperlane EVM convention); the alt-VM guide calls the same slot the mailbox address.

## ISM metadata

Multisig metadata for a message-id checkpoint:

```
origin merkle tree   bytes32   32
signed root          bytes32   32
signed index         uint32     4, big-endian
validator signatures bytes     65 bytes each, r || s || v
```

The tail must be a whole number of 65-byte signatures. Signatures are over the checkpoint
digest above. A repeated signer counts once; a below-threshold message is refused.

## ISM modules

| Module | `moduleType` | Rule |
|---|---|---|
| `hyperlaneTestIsm` | 6 (NULL) | Returns the test switch. Devnet only. |
| `hyperlaneTrustedRelayerIsm` | 6 (NULL) | Accepts when the Mailbox records the configured relayer as the message processor. |

The Mailbox records the processor as `keccak256(caller 65-byte secp256k1 public key)`.
The configured relayer is the same lowercase hex value.

The Mailbox passes the processor to the module as an internal fourth argument so the
module does not call back into the Mailbox while its single state cell is consumed. The
three-argument `verify(metadata, message)` form remains for the standard interface.

## r-bridge payload

The payload rides in the message body as UTF-8 with `|` separators:

```
rbridge:hyperlane:v1|action|assetKey|amount|recipient|externalId|nonce
```

- `action`: `deposit` (native → rholo) or `withdraw` (rholo → native).
- `assetKey`: chain-qualified, e.g. `ethereum.usdt`.
- `amount`: positive integer in rholo base units.
- `recipient`: rholo address for a deposit; native address for a withdrawal.
- `externalId`: native deposit locator or rholo burn id.
- `nonce`: unsigned decimal.

Every field is non-empty, at most 256 bytes and must not contain `|`. Exactly seven
fields are required, so a delimiter smuggled into a field is refused.

## Deployment conventions

- `localDomain`: a uint32 deployment parameter. The devnet uses `9999`; it is not a
  registered Hyperlane domain. `0` is refused.
- EVM addresses are left-padded into `bytes32`; the low 20 bytes are the address.
- rholo contract identities are a configured 32-byte id (for example
  `keccak256(utf8(id))`), not a REV address string. Beneficiary strings live in the body.
- Dispatch is capability-gated. The public Mailbox bundle exposes reads and `process`; a
  separate dispatch door, held by the Router or harness, fixes the sender id. There is no
  public dispatch arm.

## Mailbox behaviour

`process(metadata, message)`:

1. Refuse a version other than 3.
2. Refuse a destination other than `localDomain`.
3. Refuse a message id already delivered.
4. Ask the configured ISM. A false verdict leaves no delivery record.
5. Call the recipient's `handle(origin, sender, body)`.
6. On success, record the delivery (processor, block number) and return the id.

`processedAt` is the block number reported by `rho:block:data`. The state is one cell:
consume, validate, repost exactly once on every path. A refused delivery reposts the prior
state unchanged.

## Merkle tree and checkpoint

The default hook is Hyperlane's depth-32 tree. `count` is the 1-based number of inserted
leaves; `zero[0] = 0x00…00` and `zero[i+1] = keccak256(zero[i] ‖ zero[i])`.

- **Insert:** carry the leaf from level 0; at level `i`, if `count` has bit `i` set, store
  the carried node in `branch[i]` and stop; otherwise `node = keccak256(branch[i] ‖ node)`
  and continue.
- **Root:** start with a zero current node and walk levels 0–31; for a set bit
  `current = keccak256(branch[i] ‖ current)`, for a clear bit
  `current = keccak256(current ‖ zero[i])`.
- **latestCheckpoint:** `(root, count - 1)`; `(root, 0)` when empty.

The hook is reached only through the Mailbox's private hook name, so it trusts the message
it is handed; it does not call back into the Mailbox while the Mailbox state cell is
consumed.

## Router and the wired Bridge

The Router is the Mailbox's recipient.

- **Inbound:** check `sender == byDomain[origin]`; convert the ASCII body to a string;
  require exactly seven `|`-separated fields, the tag and `action == deposit`; parse the
  amount and nonce; call the Bridge's private `bridgeHyperlaneMint` capability. A refused
  mint returns `false`, so the Mailbox records no delivery.
- **Outbound:** `burn` records the withdrawal and calls the Router's
  `dispatchWithdrawal`. The Router builds
  `rbridge:hyperlane:v1|withdraw|assetKey|amount|destAddress|withdrawalId|nonce`, looks up
  the chain's `{domain, peer}` route, and dispatches through the Mailbox door. The
  withdrawal record stores the dispatch message id (or `"failed"`; the burn still stands).
- Routes are deployment state: `byDomain` for inbound and `routes` by chain name for
  outbound. Runtime enrolment is not implemented.

## EVM peer

`contracts/evm/src/HyperlanePeer.sol` is a standalone single-asset endpoint; the attested
`BridgeVault` is unchanged.

- `lock(amount, rholoRecipient)` pulls an ERC-20, scales native units to rholo units,
  derives a deposit id from `keccak256(chainid, peer, sender, nonce)`, and dispatches the
  canonical deposit payload.
- `handle(origin, sender, body)` requires the Mailbox caller and the enrolled
  origin/sender, parses the withdraw payload, refuses a used withdrawal id, and releases
  `rholoAmount × scale`.
- The message-id and checkpoint golden vectors are asserted in
  `contracts/evm/test/HyperlanePeer.t.sol`.

## Golden vectors

Message (nonce 7, origin 11155111, sender `0x…aa`, destination 84532,
recipient `0x…bb`, body = the payload below):

```
message = 030000000700aa36a7
          00000000000000000000000000000000000000000000000000000000000000aa
          00014a34
          00000000000000000000000000000000000000000000000000000000000000bb
          726272696467653a68797065726c616e653a76317c6465706f7369747c657468657265756d
          2e757364747c313030303030307c72686f3a69643a726563697069656e747c30786162633a
          307c37
id      = f44504e00b9ef65496c962d2c682804f0ec047ee58f0b3cd30c6b116895e04e9
```

Payload:

```
rbridge:hyperlane:v1|deposit|ethereum.usdt|1000000|rho:id:recipient|0xabc:0|7
keccak256 = f1002c175ee8b36016c88541a7e5999996266b07214ab76367e11683cfe06770
```

Checkpoint (origin 11155111, merkle tree `0x11…11`, root `0x22…22`, index 3, message id
above):

```
digest = a4411138366886244ae59b3f44587dc9f12edd373b6c0603f8909e3785e3d963
```

A self-addressed demo message (nonce 0, origin 9999, destination 9999, the same sender,
recipient and body) has id
`a5e13d7667b24ff9b58d33b0b21d9805d372e4d79e8115c787481330fad3ecd2`. These values are
pinned by `cargo test -p rbridge-core hyperlane`, by `make hyperlane-demo` and by the CLI
(`rbridge hyperlane message|checkpoint|payload`).

## Versioning

The `rbridge:hyperlane:v1` tag is part of the payload. The message version is 3. Any
change to the message layout, the checkpoint digest, the metadata layout, the payload
fields or the processor derivation is a protocol change: add a new tag/version, deploy a
new Mailbox, and keep the old one verifying until its transfers are settled.
