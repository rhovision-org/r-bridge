use async_trait::async_trait;
use rbridge_core::AttestationMessage;
use serde::{Deserialize, Serialize};

/// A deposit message plus the relayers' DER signatures over its digest.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct DepositAttestation {
    pub message: AttestationMessage,
    /// Lowercase hex of DER low-S secp256k1 signatures, one per signer.
    pub signatures: Vec<String>,
}

/// The health/registration view the node add-on exposes to the dApp. This is the
/// app-facing contract proposed in rhovision-org/rholo#563; the mock relayer implements
/// the same shape.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RelayerHealth {
    pub version: String,
    pub chains: Vec<String>,
    pub threshold: u16,
    pub signers: usize,
    #[serde(default)]
    pub paused: bool,
}

/// The relayer interface the SDK consumes. r-bridge does not implement production
/// relaying; the node add-on does. The mock in `harness/` implements this for devnets.
#[async_trait(?Send)]
pub trait RelayerApi {
    /// Fetch the attestation for a deposit id, or `None` while it is still awaiting
    /// confirmations.
    async fn deposit_attestation(
        &self,
        deposit_id: &str,
    ) -> Result<Option<DepositAttestation>, String>;

    async fn health(&self) -> Result<RelayerHealth, String>;
}

#[cfg(test)]
mod tests {
    use super::*;
    use rbridge_core::{AssetRef, Chain, Direction};

    #[test]
    fn attestations_round_trip() {
        let attestation = DepositAttestation {
            message: AttestationMessage {
                network: "devnet".to_string(),
                chain: Chain::Ethereum,
                bridge_id: "rho:id:bridge".to_string(),
                asset: AssetRef::new(Chain::Ethereum, "usdc").expect("asset"),
                direction: Direction::Deposit,
                external_tx_id: "0xabc:0".to_string(),
                amount: 1_000_000,
                recipient: "rho:id:user".to_string(),
                nonce: 1,
            },
            signatures: vec!["30aa".to_string()],
        };
        let json = serde_json::to_string(&attestation).expect("json");
        let back: DepositAttestation = serde_json::from_str(&json).expect("json");
        assert_eq!(back, attestation);
    }
}
