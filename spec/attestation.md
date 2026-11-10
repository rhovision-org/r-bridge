# Attestation format (v1)

The attestation is the only message that authorises value to cross the bridge. The
same bytes must be produced by the relayer (Rust), the rholo contract (Rholang), the
EVM/Tron vaults (Solidity) and the Agoric vat (JavaScript). This document is the
cross-implementation contract.

## Canonical message

```
message = "rbridge:v1" "|" network "|" chain "|" bridge_id "|" asset
        "|" direction "|" external_tx_id "|" amount "|" recipient "|" nonce
```

- UTF-8, no escaping, no whitespace.
- `network`: deployment id, e.g. `rbridge-devnet`, `mainnet`.
- `chain`: `ethereum`, `tron`, `agoric` (later `hyperliquid`, `bitcoin`).
- `bridge_id`: the deployed bridge root's registry URI, e.g. `rho:id:…`.
- `asset`: `chain.asset`, e.g. `ethereum.usdt`, `tron.usdt`, `agoric.usdc`.
- `direction`: `deposit` (native → rholo) or `withdraw` (rholo → native).
- `external_tx_id`: the native deposit locator (`txhash:log_index`) for a deposit; the
  rholo burn id for a withdrawal.
- `amount`: positive integer in **rholo base units** (the scaled amount, not the native
  base-unit amount). Direction carries the sign of the value movement.
- `recipient`: the rholo address for a deposit; the native address for a withdrawal.
- `nonce`: the relayer's monotonic id for this attestation, used for logging and dedupe.

Every field is non-empty, at most 256 bytes, and must not contain `|`. The amount must
be > 0. These constraints are enforced in `rbridge-core`; the Rholang and Solidity
implementations must reject the same inputs.

## Digest and signatures

```
digest = keccak256(utf8(message))
```

- Sign the **32-byte digest** with secp256k1, deterministic RFC-6979 nonces, low-S,
  **DER** encoding. `rbridge-chain::KeyPair::sign_prehash` produces exactly this.
- rholo: `rho:crypto:secp256k1Verify(digest, der_signature, pubkey)` returns a boolean.
  The system process refuses a non-32-byte prehash and a non-DER signature.
- EVM/Tron: the same key and digest, with the signature split into `(r, s, v)` and
  verified by `ECDSA.recover(digest, v, r, s)`. Do not use `personal_sign` or EIP-191:
  the prefix would change the digest.
- Agoric vat: verify with `@noble/curves` secp256k1 over the 32-byte digest, DER or
  `(r,s)` as the vat's library expects; pin the library version.

A relayer set is `m-of-n` with 65-byte uncompressed secp256k1 public keys, lowercase hex.
The threshold is met when at least `m` **distinct** keys in the set produce a valid
signature over the digest. The bridge contract stores the set and threshold; the native
vaults store the same set (or a hash of it) and verify the same rule.

## Identifiers

Deposit id (computed by the relayer and re-computed on rholo):

```
rbridge:deposit:v1|chain|vault|tx_hash|log_index
deposit_id = keccak256(utf8(that string))      // 64 lowercase hex chars
```

Withdrawal id: the rholo `Bridge.burn` op id (client-generated, 1–128 chars from
`[A-Za-z0-9._:-]`). The unlock digest uses `direction = withdraw`, `external_tx_id` =
the burn id, `recipient` = the native destination address.

Both ids are one-shot. `Bridge` stores processed deposit ids; each vault stores used
withdrawal ids. A repeat is a no-op returning the prior result, never a second transfer.

## Finality and timing

- Ethereum: wait for the `finalized` block tag (or 64 confirmations if the RPC does not
  expose finality).
- Tron: 19 blocks for solidity, 64 for conservative operation.
- Agoric/Cosmos: wait for IBC/chain finality and a configured confirmation depth.
- rholo: the containing block must answer `GET /api/is-finalized/{hash}` with `true`,
  the deploy must be `ProcessedWithSuccess`, and the contract reply must be
  `(true, …)`. Inclusion or execution alone is not finality.

A reorg before the confirmation depth means the relayer does not sign. A reorg after a
mint is a governance/incident event: pause the bridge, do not mint again for the same
deposit id, and reconcile against the native chain.

## Golden vector

Canonical message:

```
rbridge:v1|devnet|ethereum|rho:id:bridge|ethereum.usdt|deposit|0xabc:0|1000000|rho:id:recipient|7
```

Digest (keccak256):

```
b21892a96916dfd84579a2d31b6e64db43a6e8d1e94e5e360f8dea608bbd0a22
```

`crates/rbridge-core/src/digest.rs` pins this value. The Rholang, Solidity and Agoric
implementations must reproduce it in their own test suites before any testnet
deployment.

## Versioning

The `rbridge:v1` tag is part of the signed bytes. Any change to field order, separators,
meaning or hashing is a protocol change: add `rbridge:v2`, deploy a new bridge root,
and keep v1 verifying until its balances are drained. Adding an asset or a chain to the
registry does **not** change the format.
