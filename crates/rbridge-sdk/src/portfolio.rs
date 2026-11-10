use rbridge_core::{Amount, AssetRef};
use serde::{Deserialize, Serialize};

/// Where a balance was read from. A bridge portfolio deliberately keeps this visible:
/// a wallet-read native balance and a node-read wrapped balance are different claims.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BalanceSource {
    Wallet,
    Relayer,
    RholoNode,
    Unavailable,
}

/// One asset's native and wrapped holdings.
///
/// Native amounts are strings because an 18-decimal wei value does not fit the JSON
/// number range safely. Wrapped amounts are the rholo `i64` base units.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AssetBalance {
    pub asset: AssetRef,
    pub symbol: String,
    pub wrapped_symbol: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub native_base_units: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub wrapped_amount: Option<Amount>,
    pub native_decimals: u8,
    pub rholo_decimals: u8,
    pub source: BalanceSource,
}

/// The user's snapshot across chains. `rholo_account` is the RBridge-managed rholo
/// address; native accounts are not stored here because they belong to the wallets.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Portfolio {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rholo_account: Option<String>,
    pub balances: Vec<AssetBalance>,
    pub fetched_at_ms: u64,
}

impl Portfolio {
    pub fn empty() -> Self {
        Self {
            rholo_account: None,
            balances: Vec::new(),
            fetched_at_ms: 0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rbridge_core::Chain;

    #[test]
    fn asset_balances_round_trip() {
        let balance = AssetBalance {
            asset: AssetRef::new(Chain::Ethereum, "usdt").expect("asset"),
            symbol: "USDT".to_string(),
            wrapped_symbol: "wUSDT.eth".to_string(),
            native_base_units: Some("1000000".to_string()),
            wrapped_amount: Some(Amount::raw(1_000_000)),
            native_decimals: 6,
            rholo_decimals: 6,
            source: BalanceSource::Wallet,
        };
        let json = serde_json::to_string(&balance).expect("json");
        let back: AssetBalance = serde_json::from_str(&json).expect("json");
        assert_eq!(back, balance);
        assert!(json.contains("wUSDT.eth"));
    }

    #[test]
    fn an_empty_portfolio_is_explicit() {
        let portfolio = Portfolio::empty();
        assert!(portfolio.balances.is_empty());
        assert!(portfolio.rholo_account.is_none());
    }
}
