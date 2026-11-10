use std::fmt;

use serde::{Deserialize, Serialize};

use crate::chain::Chain;
use crate::error::BridgeError;

/// A native asset identifier on one chain, e.g. `usdt`, `usdc`, `dai`, `trx`, `atom`.
/// Chain qualification lives in [`AssetRef`]; the id itself is a closed character set so
/// it can be embedded in a rholang string or an attestation digest without escaping.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(transparent)]
pub struct AssetId(String);

impl AssetId {
    pub fn new(value: impl Into<String>) -> Result<Self, BridgeError> {
        let value = value.into();
        let valid = !value.is_empty()
            && value.len() <= 48
            && value.chars().all(|c| {
                c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, '.' | '-' | '_')
            });
        if valid {
            Ok(Self(value))
        } else {
            Err(BridgeError::BadAssetId(value))
        }
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for AssetId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// A chain-qualified asset. USDT on Ethereum, Tron and Cosmos are three distinct
/// liabilities and therefore three distinct [`AssetRef`]s.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct AssetRef {
    pub chain: Chain,
    pub id: AssetId,
}

impl AssetRef {
    pub fn new(chain: Chain, id: impl Into<String>) -> Result<Self, BridgeError> {
        Ok(Self {
            chain,
            id: AssetId::new(id)?,
        })
    }

    /// The canonical wire form, e.g. `ethereum.usdt`.
    pub fn as_string(&self) -> String {
        format!("{}.{}", self.chain.as_str(), self.id.as_str())
    }
}

impl fmt::Display for AssetRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.as_string())
    }
}

/// One entry in the canonical asset registry.
///
/// `native_decimals` is the chain's own precision; `rholo_decimals` is the precision of
/// the wrapped token's ledger on rholo. The latter is capped at 8 because rholo amounts
/// are `i64` base units and 18-decimal precision cannot represent a useful range.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AssetSpec {
    pub asset: AssetRef,
    /// Display symbol on the native chain, e.g. `USDT`.
    pub symbol: String,
    /// Display symbol of the wrapped token on rholo, e.g. `wUSDT.eth`.
    pub wrapped_symbol: String,
    pub native_decimals: u8,
    pub rholo_decimals: u8,
    /// Minimum and maximum deposit in rholo base units.
    pub min_deposit: i64,
    pub max_deposit: i64,
    pub fee_bps_deposit: u16,
    pub fee_bps_withdraw: u16,
    pub enabled: bool,
}

impl AssetSpec {
    pub fn validate(&self) -> Result<(), BridgeError> {
        if self.rholo_decimals > 8 {
            return Err(BridgeError::BadAssetSpec(
                "rholo_decimals must be <= 8 (i64 base units)",
            ));
        }
        if self.rholo_decimals > self.native_decimals {
            return Err(BridgeError::BadAssetSpec(
                "rholo_decimals must not exceed native_decimals",
            ));
        }
        if self.min_deposit < 0 || self.min_deposit > self.max_deposit {
            return Err(BridgeError::BadAssetSpec(
                "min_deposit must be >= 0 and <= max_deposit",
            ));
        }
        if self.max_deposit <= 0 {
            return Err(BridgeError::BadAssetSpec("max_deposit must be positive"));
        }
        if self.fee_bps_deposit > 10_000 || self.fee_bps_withdraw > 10_000 {
            return Err(BridgeError::BadAssetSpec("fee bps must be <= 10000"));
        }
        if self.symbol.is_empty() || self.wrapped_symbol.is_empty() {
            return Err(BridgeError::BadAssetSpec("symbols must not be empty"));
        }
        Ok(())
    }
}

#[allow(clippy::too_many_arguments)]
fn spec(
    chain: Chain,
    id: &str,
    symbol: &str,
    wrapped_symbol: &str,
    native_decimals: u8,
    rholo_decimals: u8,
    min_whole: i64,
    max_whole: i64,
    enabled: bool,
) -> Result<AssetSpec, BridgeError> {
    let quantum = 10_i64
        .checked_pow(u32::from(rholo_decimals))
        .ok_or(BridgeError::AmountOutOfRange)?;
    let min_deposit = min_whole
        .checked_mul(quantum)
        .ok_or(BridgeError::AmountOutOfRange)?;
    let max_deposit = max_whole
        .checked_mul(quantum)
        .ok_or(BridgeError::AmountOutOfRange)?;
    Ok(AssetSpec {
        asset: AssetRef::new(chain, id)?,
        symbol: symbol.to_string(),
        wrapped_symbol: wrapped_symbol.to_string(),
        native_decimals,
        rholo_decimals,
        min_deposit,
        max_deposit,
        fee_bps_deposit: 5,
        fee_bps_withdraw: 5,
        enabled,
    })
}

/// The initial canonical registry. Hyperliquid and Bitcoin entries are deliberately
/// absent until their adapters exist; adding them is a registry change, not a protocol
/// change.
pub fn initial_registry() -> Result<Vec<AssetSpec>, BridgeError> {
    let specs = vec![
        // Ethereum
        spec(
            Chain::Ethereum,
            "eth",
            "ETH",
            "wETH",
            18,
            8,
            1,
            1_000_000,
            true,
        )?,
        spec(
            Chain::Ethereum,
            "usdt",
            "USDT",
            "wUSDT.eth",
            6,
            6,
            1,
            1_000_000_000,
            true,
        )?,
        spec(
            Chain::Ethereum,
            "usdc",
            "USDC",
            "wUSDC.eth",
            6,
            6,
            1,
            1_000_000_000,
            true,
        )?,
        spec(
            Chain::Ethereum,
            "dai",
            "DAI",
            "wDAI",
            18,
            8,
            1,
            1_000_000_000,
            true,
        )?,
        // Tron
        spec(
            Chain::Tron,
            "trx",
            "TRX",
            "wTRX",
            6,
            6,
            1,
            1_000_000_000,
            true,
        )?,
        spec(
            Chain::Tron,
            "usdt",
            "USDT",
            "wUSDT.trx",
            6,
            6,
            1,
            1_000_000_000,
            true,
        )?,
        spec(
            Chain::Tron,
            "usdc",
            "USDC",
            "wUSDC.trx",
            6,
            6,
            1,
            1_000_000_000,
            true,
        )?,
        // Cosmos / Agoric
        spec(
            Chain::Agoric,
            "atom",
            "ATOM",
            "wATOM",
            6,
            6,
            1,
            1_000_000_000,
            true,
        )?,
        spec(
            Chain::Agoric,
            "ist",
            "IST",
            "wIST",
            6,
            6,
            1,
            1_000_000_000,
            true,
        )?,
        spec(
            Chain::Agoric,
            "usdc",
            "USDC",
            "wUSDC.noble",
            6,
            6,
            1,
            1_000_000_000,
            true,
        )?,
        // Enabled once a registered IBC denom for USDT is confirmed on the target network.
        spec(
            Chain::Agoric,
            "usdt",
            "USDT",
            "wUSDT.cosmos",
            6,
            6,
            1,
            1_000_000_000,
            false,
        )?,
    ];
    for spec in &specs {
        spec.validate()?;
    }
    Ok(specs)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_is_valid_and_chain_qualified() {
        let specs = initial_registry().expect("registry");
        assert!(specs.len() >= 10);
        let mut refs = std::collections::BTreeSet::new();
        let mut symbols = std::collections::BTreeSet::new();
        for spec in &specs {
            assert!(spec.validate().is_ok(), "{:?}", spec.asset);
            assert!(refs.insert(spec.asset.clone()), "duplicate {}", spec.asset);
            assert!(
                symbols.insert(spec.wrapped_symbol.clone()),
                "duplicate wrapped symbol {}",
                spec.wrapped_symbol
            );
        }
        let usdt_eth = AssetRef::new(Chain::Ethereum, "usdt").expect("eth usdt");
        let usdt_tron = AssetRef::new(Chain::Tron, "usdt").expect("tron usdt");
        assert_ne!(usdt_eth, usdt_tron);
        assert_eq!(usdt_eth.as_string(), "ethereum.usdt");
        assert_eq!(usdt_tron.as_string(), "tron.usdt");
    }

    #[test]
    fn asset_ids_refuse_injection() {
        assert!(AssetId::new("usdt").is_ok());
        assert!(AssetId::new("usdt.eth").is_ok());
        assert!(AssetId::new("USDT").is_err());
        assert!(AssetId::new("").is_err());
        assert!(AssetId::new("u|sdt").is_err());
        assert!(AssetId::new("u\"sdt").is_err());
    }

    #[test]
    fn eighteen_decimal_assets_scale_to_eight() {
        let specs = initial_registry().expect("registry");
        let eth = specs
            .iter()
            .find(|s| s.asset.chain == Chain::Ethereum && s.asset.id.as_str() == "eth")
            .expect("eth");
        assert_eq!((eth.native_decimals, eth.rholo_decimals), (18, 8));
        let usdt = specs
            .iter()
            .find(|s| s.asset.chain == Chain::Tron && s.asset.id.as_str() == "usdt")
            .expect("tron usdt");
        assert_eq!((usdt.native_decimals, usdt.rholo_decimals), (6, 6));
    }
}
