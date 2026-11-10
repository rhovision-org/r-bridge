# Asset registry and amount scaling

## Chain-qualified assets

USDT on Ethereum, Tron and Cosmos are different issuer liabilities. They are distinct
wrapped tokens on rholo (`wUSDT.eth`, `wUSDT.trx`, `wUSDT.cosmos`) and must never be
merged into one balance or one mint authority. The UI may show a symbol aggregate for
display, but every transfer and contract call uses the chain-qualified id.

## Initial registry

The authoritative table is `crates/rbridge-core/src/asset.rs` (`initial_registry()`).
This is the planning record; native contract addresses are filled by each deployment
manifest and verified at deploy time.

The **Status** column describes the registry entry, not a deployment: `active` means the
asset is in the planned initial registry; `disabled` means it waits on a denom. Only
Ethereum ETH and USDT are exercised end-to-end in this repository today; a wrapped symbol
exists once a native vault/vat for it is deployed and registered.

| Chain | Asset | Wrapped symbol | Native decimals | rholo decimals | Fee (deposit/withdraw) | Status |
|---|---|---|---|---|---|---|
| Ethereum | ETH | wETH | 18 | 8 | 5/5 bps | active |
| Ethereum | USDT | wUSDT.eth | 6 | 6 | 5/5 bps | active |
| Ethereum | USDC | wUSDC.eth | 6 | 6 | 5/5 bps | active |
| Ethereum | DAI | wDAI | 18 | 8 | 5/5 bps | active |
| Tron | TRX | wTRX | 6 | 6 | 5/5 bps | active |
| Tron | USDT | wUSDT.trx | 6 | 6 | 5/5 bps | active |
| Tron | USDC | wUSDC.trx | 6 | 6 | 5/5 bps | active |
| Agoric | ATOM | wATOM | 6 | 6 | 5/5 bps | active |
| Agoric | IST | wIST | 6 | 6 | 5/5 bps | active |
| Agoric | USDC (Noble IBC) | wUSDC.noble | 6 | 6 | 5/5 bps | active |
| Agoric | USDT (IBC) | wUSDT.cosmos | 6 | 6 | 5/5 bps | disabled until a denom is registered |

Stablecoin coverage: USDT and USDC on Ethereum and Tron; USDC on Cosmos via Noble; DAI
on Ethereum only. No wrapped stablecoin is created without a native asset that a
relayer can verify and a vault/vat that can release.

## Amount scaling

rholo amounts are `i64` base units (the ERTP ledger's `NonNegI64`), so the wrapped
precision is capped at 8 decimals:

- Native precision ≤ 8: keep it (USDT/USDC/TRX/ATOM/IST = 6, BTC = 8 if added).
- Native precision > 8: scale down to 8 (ETH and DAI: 18 → 8).
- A native amount that is not an exact multiple of the scale quantum is **dust** and is
  refused. It is never rounded up (would mint more than was locked) and never rounded
  down (would break conservation). The UI must show the granularity and prevent dust
  submissions; the contract/vault enforces it as the final gate.
- At 8 decimals the `i64` range is ~92 billion whole tokens, ample for every initial
  asset.

Examples:

| Native input | Asset | rholo amount |
|---|---|---|
| 1 ETH = 1e18 wei | ETH (18→8) | 100,000,000 |
| 1,000 wei | ETH | refused (dust) |
| 1 USDT = 1,000,000 | USDT (6→6) | 1,000,000 |
| 1,000,000 USDT | USDT | 1,000,000,000,000 |

## Native addresses (planning placeholders)

These are recorded for deployment manifests; verify every one against the target
network before use.

- Ethereum mainnet: USDT `0xdAC17F958D2ee523a2206206994597C13D831ec7`, USDC
  `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`, DAI
  `0x6B175474E89094C44Da98b954EedeAC495271d0F`.
- Ethereum Sepolia: USDC (Circle) `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`;
  USDT and DAI use test tokens deployed by the harness where no canonical faucet token
  exists.
- Tron mainnet: USDT `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t` (TRC-20). Nile uses the
  network's test tokens or harness mocks; record the exact contract in the manifest.
- Agoric: ATOM and USDC (Noble) arrive as IBC denoms; record the full denom in the
  deployment manifest. IST is native to Agoric. USDT is enabled only when a registered
  IBC denom is confirmed.

## Registry changes

Adding an asset, changing a fee, a cap or a scale is a governance action on
`BridgeRoot` (2-of-3 admin). It does not change the v1 attestation format. Removing an
asset must leave an exit path: disable new deposits, keep burns/unlocks working, and
drain the wrapped supply before removing the token URI.
