# Rholang libraries

Two libraries are inlined into the deploy term at build time; they are not separately
installed.

- `Guard.rho` — canonical message helpers and m-of-n secp256k1 verification over the
  32-byte digest.
- `Ledger.rho` — REV-address identity, per-asset balances, supply and fee arithmetic.

`tools/build_contracts.py` expands the `// @@INLINE:` markers and writes the generated
term to `contracts/rholo/build/`.
