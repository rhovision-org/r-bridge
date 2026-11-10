//! Connected r-bridge client surface.
//!
//! The SDK owns no wire protocol of its own: node reads, deploy encoding and signing
//! come from `rbridge-chain`, which wraps the pinned r-cash client. This crate adds the
//! bridge-shaped types shared by the CLI, the WASM facade and the web app.

#![forbid(unsafe_code)]

pub mod config;
pub mod portfolio;
pub mod relayer;

use rbridge_chain::RholoNode;

pub use config::BridgeConfig;
pub use portfolio::{AssetBalance, BalanceSource, Portfolio};
pub use relayer::{DepositAttestation, RelayerApi, RelayerHealth};

/// An error from the SDK layer.
#[derive(Debug, thiserror::Error)]
pub enum SdkError {
    #[error(transparent)]
    Chain(#[from] rbridge_chain::ChainError),
    #[error(transparent)]
    Core(#[from] rbridge_core::BridgeError),
    #[error("relayer: {0}")]
    Relayer(String),
}

/// A read-only bridge client connected to one rholo node.
pub struct BridgeClient {
    node: RholoNode,
    config: BridgeConfig,
}

impl BridgeClient {
    pub fn reader(config: BridgeConfig) -> Result<Self, SdkError> {
        let node = RholoNode::new(config.node_url.clone())?;
        Ok(Self { node, config })
    }

    pub fn config(&self) -> &BridgeConfig {
        &self.config
    }

    pub fn node(&self) -> &RholoNode {
        &self.node
    }

    /// Fetch the node's status document. This is the cheapest liveness/read check and
    /// the same route the wallet and CLI use.
    pub async fn node_status(&self) -> Result<serde_json::Value, SdkError> {
        Ok(self.node.status().await?)
    }

    pub async fn latest_block_number(&self) -> Result<i64, SdkError> {
        Ok(self.node.latest_block_number().await?)
    }
}

impl std::fmt::Debug for BridgeClient {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("BridgeClient")
            .field("node", &self.node)
            .field("network", &self.config.network)
            .finish()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_reader_is_constructed_without_network_access() {
        let config = BridgeConfig::new("devnet", "http://127.0.0.1:40403");
        let client = BridgeClient::reader(config).expect("client");
        assert_eq!(client.config().network, "devnet");
        assert_eq!(client.node().base_url(), "http://127.0.0.1:40403");
    }
}
