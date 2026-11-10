# Third-party notices

r-bridge is AGPL-3.0-only.

It links, at pinned git revisions, crates from:

- **r-cash** (`rhovision-org/r-cash`, rev `49b441d…`) — AGPL-3.0-only. Supplies the
  node HTTP client, deploy encoding and secp256k1 signing.
- **rholo** (`rhovision-org/rholo`, rev `841cb84…`) — AGPL-3.0-only. Supplies
  `rchain-crypto` and `rchain-shared`.

The keystore uses RustCrypto crates from crates.io — `scrypt`, `aes`, `ctr`, `pbkdf2`,
`sha2` and `k256` — under MIT/Apache-2.0. They are linked as libraries, not copied.

The web client's wallet connectors use the wallets' own injected providers
(MetaMask, TronLink, Keplr). No r-wallet source is copied in this scaffold; the
r-wallet project is GPL-3.0 and is referenced only as a behavioural/UX reference.
If code is copied from it later, the combined work must remain AGPL-3.0 (which
GPLv3 permits), and this file must record the copied files.
