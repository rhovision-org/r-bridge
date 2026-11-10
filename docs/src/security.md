# Security model

This chapter states what the bridge assumes, what protects each asset, and what remains
unproven. The normative rules are in [Attestation](reference/attestation.md) and
[Invariants](reference/invariants.md); the implementation is in `contracts/`.

**No external audit has been performed.** Nothing in this chapter should be read as a
security guarantee for value-bearing deployment.

## Assumptions

- **Wallets are honest for their own keys.** MetaMask, TronLink and Keplr sign what the
  user approves. The dApp must explain each transaction; a malicious dApp or a
  compromised browser is outside the on-chain model.
- **The relayer set is m-of-n honest.** The threshold is 2-of-3 in the demo. A majority
  of colluding relayers can attest a false deposit or unlock; the contracts cannot
  distinguish a lie from the truth. The set is permissioned today, and there is no
  economic bond.
- **The rholo node reports finality correctly.** The contracts require a finalized,
  successfully processed deploy returning `true`. A lying node can misreport to its own
  clients; a second node or the relayer can cross-check.
- **Native finality is meaningful.** Ethereum uses the finalized tag or a confirmation
  depth; Tron uses solidity depth; Agoric uses IBC finality. The dev harness runs on
  Anvil, whose finality tag is simulated.
- **Admin keys are separate from relayer keys.** Compromise of one does not imply the
  other.
- **The Agoric vat and the Zoe/ZCF stack are correct.** They are part of the trusted
  computing base on the Cosmos side.

## Threats and protections

| Threat | Protection | Residual risk |
|---|---|---|
| Forged deposit or unlock | m-of-n secp256k1 signatures over a digest that binds network, chain, bridge, asset, direction, external id, amount, recipient and nonce | A relayer majority can sign anything |
| Signature malleability | Low-S DER for rholo; `r||s||v` with low-S recovery for EVM/Tron; duplicate signers are not counted twice | Library/curve implementation bugs |
| Replay of a deposit | Deposit id derived from chain, vault, tx and log index; consumed once | An id-derivation or attestation bug could allow a second id |
| Replay of an unlock or admin action | Used withdrawal ids; consumed admin nonces; one-shot refund ids | — |
| Reorged deposit minted | Safe-head/finalized gate; block-hash journal; rewind on an unprocessed reorg; halt if a settled deposit is reorged out | Deep reorgs need operator reconciliation |
| Double unlock | Withdrawal id marked used before/while releasing; nonReentrant on value paths | — |
| Wrong asset or chain | Chain-qualified asset keys inside the digest; per-token vault config | Misconfigured deployment, checked by read-back |
| Amount manipulation | Integer base units; scale enforced at the boundary; dust refused, never rounded | None known |
| Excessive exposure | Per-asset max deposit and max locked; pause | Params are testnet values |
| Paused-bridge escape | Pause blocks new locks/mints; burns, unlocks and refunds still work | Admin can pause indefinitely (governance risk) |
| Treasury redirection | Treasury fixed at deployment; sweep has no recipient argument on rholo | Vault treasury withdrawal chooses a recipient by design |
| Native-key theft by the app | Native keys never imported; the rholo key is the only locally handled key | Malicious page code is out of scope |
| Keystore at rest | Web3 v3 scrypt (n=2^17, r=8, p=1), AES-128-CTR, keccak MAC; encrypted browser copies only | Unaudited implementation; offline guessing remains |

## Key separation

| Key | Held by | Signs | Must not be |
|---|---|---|---|
| Native wallet key | User (MetaMask/TronLink/Keplr) | Native lock/approve/release | Imported into r-bridge |
| rholo account key | User, as a WASM-decrypted Web3 v3 keystore | rholo deploys (`mint`, `burn`, admin from governance) and pays phlo | Stored plaintext or in the repo |
| Attestation key | Relayer operator | 32-byte bridge digests (DER or 65-byte form) | The deploy key or validator key |
| Deploy/phlo key | Relayer/operator | rholo deploy submission | The attestation key |
| Validator key | Validator operator | Consensus | Used by the relayer, ever |
| Admin keys | Governance multisig | `rbridge:admin:v1` payloads | A single operator key |

The demo generates all of these as throwaway keys under `.devnet/`. The deployed rholo
contract and the vault fix the relayer and admin sets at deployment; there is no on-chain
key-update path yet, so rotation means redeploying or using a new bridge id.

## What the contracts enforce on-chain

- Threshold verification per direction with a distinct-signer count.
- Idempotency first on every mutating arm; the prior result is returned without a second
  effect.
- Caps, amount validation and pause checks before any transfer.
- Conservation: fees are retained, never minted; the treasury sweep moves existing supply.
- No proxy and no external dependencies in the vault; low-S ECDSA only.
- Collateral is held by the vault/vat, not by relayers or the dApp.

## Audit scope

An external audit should cover, at minimum:

1. `contracts/rholo` — the single demo contract now, and the planned
   `BridgeRoot`/`WrappedToken` split before it is deployed.
2. `contracts/evm/src/BridgeVault.sol` and its TVM compilation and deployment parameters.
3. `contracts/agoric` — the vat, the digest verification, invitation handling and durable
   state.
4. The canonical message and every signature encoding, against the golden vectors in
   `spec/attestation.md`.
5. `crates/rbridge-keystore` and the WASM key handling, including browser storage.
6. The chosen relayer rail: watcher correctness, journal, reorg handling, key management
   and incident tooling.
7. The deployment tool and manifest verification.

## Explicit non-goals today

- No economic bond or slashing; the relayer set is permissioned and audited socially.
- No on-chain key rotation or governance update path.
- No light-client or ZK proof of native state; trust is the m-of-n set.
- No protection against a malicious dApp build served to users; reproducible builds and
  release signing are future work.
- No mainnet deployment before the audit; `tools/deploy_evm.py` refuses mainnet chain ids.
