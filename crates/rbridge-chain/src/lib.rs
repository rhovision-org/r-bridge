//! The rholo node seam.
//!
//! Deploy encoding, secp256k1 signing, REV addresses, the node HTTP transport and
//! finality polling come from the pinned `rcash-chain` crate. This module adds only the
//! operations r-bridge needs, so the web app (wasm) and the CLI (native) share one path.

#![forbid(unsafe_code)]

pub use rcash_chain::error::ChainError;
pub use rcash_chain::node::{BlockInfo, DeployStatus, ExploreResponse, NodeClient};
pub use rcash_chain::{eth_address_from_public_key, DeployOptions, KeyPair, SignedDeploy};

/// The 20-byte Ethereum address (lowercase hex, no `0x`) of a key. The same key addresses
/// both Ethereum and rholo; the vault and the rholo ledger use different representations.
pub fn eth_address(key: &KeyPair) -> Result<String, ChainError> {
    eth_address_from_public_key(key.public_bytes())
}

/// Sign a 32-byte digest in the 65-byte `r || s || v` form the EVM/TVM vault recovers.
/// This is the counterpart of [`KeyPair::sign_prehash`], which produces DER for rholo.
pub fn sign_eth_prehash(key: &KeyPair, digest: &[u8]) -> Result<[u8; 65], ChainError> {
    use k256::ecdsa::SigningKey;
    if digest.len() != 32 {
        return Err(ChainError::Crypto(format!(
            "prehash is {} bytes, expected 32",
            digest.len()
        )));
    }
    let signing = SigningKey::from_slice(key.secret_bytes())
        .map_err(|e| ChainError::Crypto(e.to_string()))?;
    let (signature, recovery) = signing.sign_prehash_recoverable(digest);
    let mut out = [0u8; 65];
    out[..64].copy_from_slice(&signature.to_bytes());
    out[64] = recovery.to_byte() + 27;
    Ok(out)
}

/// A connected rholo node. The inner client is the pinned r-cash implementation; this
/// wrapper exists so r-bridge's SDK and WASM facade do not depend on r-cash directly.
pub struct RholoNode {
    client: NodeClient,
}

impl RholoNode {
    pub fn new(url: impl Into<String>) -> Result<Self, ChainError> {
        Ok(Self {
            client: NodeClient::new(url)?,
        })
    }

    pub fn client(&self) -> &NodeClient {
        &self.client
    }

    pub fn base_url(&self) -> &str {
        self.client.base_url()
    }

    pub async fn status(&self) -> Result<serde_json::Value, ChainError> {
        self.client.status().await
    }

    pub async fn latest_block_number(&self) -> Result<i64, ChainError> {
        self.client.latest_block_number().await
    }

    pub async fn is_finalized(&self, block_hash: &str) -> Result<bool, ChainError> {
        self.client.is_finalized(block_hash).await
    }

    pub async fn deploy(&self, signed: &SignedDeploy) -> Result<String, ChainError> {
        self.client.deploy(signed).await
    }

    pub async fn deploy_status(&self, deploy_id: &str) -> Result<DeployStatus, ChainError> {
        self.client.deploy_status(deploy_id).await
    }

    pub async fn explore(&self, term: &str) -> Result<ExploreResponse, ChainError> {
        self.client.explore(term).await
    }

    pub async fn last_finalized_block(&self) -> Result<BlockInfo, ChainError> {
        self.client.last_finalized_block().await
    }
}

impl std::fmt::Debug for RholoNode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("RholoNode")
            .field("base_url", &self.client.base_url())
            .finish()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_node_can_be_constructed_without_network_access() {
        let node = RholoNode::new("http://127.0.0.1:40403").expect("node");
        assert_eq!(node.base_url(), "http://127.0.0.1:40403");
    }

    #[test]
    fn signing_a_prehash_produces_a_verifying_der_signature() {
        let key = KeyPair::from_secret_hex(
            "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76",
        )
        .expect("key");
        let digest = [7_u8; 32];
        let sig = key.sign_prehash(&digest).expect("sign");
        assert!(key.verify_prehash(&digest, &sig));
        assert_ne!(key.public_hex().len(), 0);
        assert!(key.rev_address().is_ok());
    }

    #[test]
    fn eth_signature_recovers_to_the_eth_address() {
        use k256::ecdsa::{RecoveryId, Signature, VerifyingKey};

        let key = KeyPair::from_secret_hex(
            "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76",
        )
        .expect("key");
        let digest = [9_u8; 32];
        let sig = sign_eth_prehash(&key, &digest).expect("sign");
        assert!(sig[64] == 27 || sig[64] == 28);
        let signature = Signature::from_slice(&sig[..64]).expect("r||s");
        let recovery = RecoveryId::from_byte(sig[64] - 27).expect("recovery");
        let recovered =
            VerifyingKey::recover_from_prehash(&digest, &signature, recovery).expect("recover");
        let expected = eth_address(&key).expect("address");
        let actual = eth_address_from_public_key(recovered.to_sec1_point(false).as_bytes())
            .expect("address");
        assert_eq!(actual, expected);
    }
}
