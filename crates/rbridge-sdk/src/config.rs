use serde::{Deserialize, Serialize};

/// Where the dApp/CLI connects. A `bridge_id` is the deployed bridge root's registry URI;
/// it is absent before installation.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct BridgeConfig {
    pub network: String,
    pub node_url: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bridge_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub relayer_url: Option<String>,
}

impl BridgeConfig {
    pub fn new(network: impl Into<String>, node_url: impl Into<String>) -> Self {
        Self {
            network: network.into(),
            node_url: node_url.into(),
            bridge_id: None,
            relayer_url: None,
        }
    }

    pub fn with_bridge_id(mut self, bridge_id: impl Into<String>) -> Self {
        self.bridge_id = Some(bridge_id.into());
        self
    }

    pub fn with_relayer_url(mut self, relayer_url: impl Into<String>) -> Self {
        self.relayer_url = Some(relayer_url.into());
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn optional_fields_are_omitted_when_absent() {
        let json = serde_json::to_string(&BridgeConfig::new("devnet", "http://localhost:40403"))
            .expect("json");
        assert!(!json.contains("bridge_id"));
        assert!(!json.contains("relayer_url"));
    }

    #[test]
    fn round_trips() {
        let config = BridgeConfig::new("devnet", "http://localhost:40403")
            .with_bridge_id("rho:id:bridge")
            .with_relayer_url("http://localhost:8080");
        let json = serde_json::to_string(&config).expect("json");
        let back: BridgeConfig = serde_json::from_str(&json).expect("json");
        assert_eq!(back, config);
    }
}
