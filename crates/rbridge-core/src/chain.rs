use std::fmt;
use std::str::FromStr;

use serde::{Deserialize, Serialize};

use crate::error::BridgeError;

/// A native chain r-bridge can move value from or to.
///
/// `Agoric` is the Cosmos leg: Agoric is a Cosmos SDK chain and the bridge vat lives
/// there. `Hyperliquid` and `Bitcoin` are reserved for later adapters; keeping them in
/// the enum now makes the registry and digest stable when those adapters land.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Chain {
    Ethereum,
    Tron,
    Agoric,
    Hyperliquid,
    Bitcoin,
}

impl Chain {
    pub const ALL: [Chain; 5] = [
        Chain::Ethereum,
        Chain::Tron,
        Chain::Agoric,
        Chain::Hyperliquid,
        Chain::Bitcoin,
    ];

    /// The canonical wire name used in the attestation digest.
    pub const fn as_str(self) -> &'static str {
        match self {
            Chain::Ethereum => "ethereum",
            Chain::Tron => "tron",
            Chain::Agoric => "agoric",
            Chain::Hyperliquid => "hyperliquid",
            Chain::Bitcoin => "bitcoin",
        }
    }

    /// Whether this chain is in the first release.
    pub const fn is_initial(self) -> bool {
        matches!(self, Chain::Ethereum | Chain::Tron | Chain::Agoric)
    }
}

impl fmt::Display for Chain {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for Chain {
    type Err = BridgeError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "ethereum" | "eth" => Ok(Chain::Ethereum),
            "tron" | "trx" => Ok(Chain::Tron),
            "agoric" | "cosmos" => Ok(Chain::Agoric),
            "hyperliquid" => Ok(Chain::Hyperliquid),
            "bitcoin" | "btc" => Ok(Chain::Bitcoin),
            other => Err(BridgeError::BadChain(other.to_string())),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wire_names_round_trip() {
        for chain in Chain::ALL {
            assert_eq!(chain.as_str().parse::<Chain>(), Ok(chain));
        }
        assert_eq!("cosmos".parse::<Chain>(), Ok(Chain::Agoric));
        assert_eq!("eth".parse::<Chain>(), Ok(Chain::Ethereum));
    }

    #[test]
    fn unknown_chain_is_refused() {
        assert!("solana".parse::<Chain>().is_err());
    }
}
