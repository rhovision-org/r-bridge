//! Browser facade.
//!
//! MetaMask, TronLink and Keplr own the native-chain accounts. This crate owns only the
//! one thing they cannot do: the rholo account and the node's deploy/attestation
//! signature format. Amounts cross the boundary as strings so no JavaScript number
//! ever truncates a base-unit value.

#![forbid(unsafe_code)]

use wasm_bindgen::prelude::*;

use rbridge_chain::{DeployOptions, DeployStatus, KeyPair, RholoNode};
use rbridge_core::{
    from_hex, initial_registry, to_hex, Amount, AssetRef, AttestationMessage, Chain, Direction,
};

fn js_error(error: impl std::fmt::Display) -> JsValue {
    JsValue::from_str(&error.to_string())
}

#[wasm_bindgen]
pub fn version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

/// The canonical asset registry as JSON.
#[wasm_bindgen]
pub fn assets_json() -> Result<String, JsValue> {
    let registry = initial_registry().map_err(js_error)?;
    serde_json::to_string(&registry).map_err(js_error)
}

/// Compute the digest relayers sign. Every argument is a string on the wire; the amount
/// is parsed as an i64 in rholo base units.
#[wasm_bindgen]
#[allow(clippy::too_many_arguments)]
pub fn attestation_digest_hex(
    network: String,
    chain: String,
    bridge_id: String,
    asset_chain: String,
    asset_id: String,
    direction: String,
    external_tx_id: String,
    amount: String,
    recipient: String,
    nonce: u32,
) -> Result<String, JsValue> {
    let chain: Chain = chain.parse().map_err(js_error)?;
    let asset_chain: Chain = asset_chain.parse().map_err(js_error)?;
    let direction: Direction = direction.parse().map_err(js_error)?;
    let amount: i64 = amount.parse().map_err(js_error)?;
    let message = AttestationMessage {
        network,
        chain,
        bridge_id,
        asset: AssetRef::new(asset_chain, asset_id).map_err(js_error)?,
        direction,
        external_tx_id,
        amount,
        recipient,
        nonce: u64::from(nonce),
    };
    message.digest_hex().map_err(js_error)
}

/// Convert a native base-unit amount (decimal string) into rholo base units.
#[wasm_bindgen]
pub fn scale_native_to_rholo(
    native: String,
    native_decimals: u8,
    rholo_decimals: u8,
) -> Result<String, JsValue> {
    let native: u128 = native.parse().map_err(js_error)?;
    let amount =
        Amount::scale_from_native(native, native_decimals, rholo_decimals).map_err(js_error)?;
    Ok(amount.value().to_string())
}

/// Encrypt a 32-byte secret into a Web3 v3 keystore (r-wallet compatible).
#[wasm_bindgen]
pub fn keystore_create(secret_hex: &str, password: &str) -> Result<String, JsValue> {
    let hex = secret_hex.trim();
    let hex = hex
        .strip_prefix("0x")
        .or_else(|| hex.strip_prefix("0X"))
        .unwrap_or(hex);
    let bytes = from_hex(hex).map_err(js_error)?;
    let secret: [u8; 32] = bytes
        .as_slice()
        .try_into()
        .map_err(|_| js_error("secret must be 32 bytes"))?;
    rbridge_keystore::create(&secret, password).map_err(js_error)
}

/// Decrypt a Web3 v3 keystore and return the secret as lowercase hex. The caller keeps
/// it in memory only; it is never written anywhere by this crate.
#[wasm_bindgen]
pub fn keystore_unlock(json: &str, password: &str) -> Result<String, JsValue> {
    let secret = rbridge_keystore::unlock(json, password).map_err(js_error)?;
    Ok(to_hex(&secret))
}

/// The rholo key. The secret never leaves this object; the JS side gets the public key,
/// the REV address and signatures only.
#[wasm_bindgen]
pub struct RholoKey {
    key: KeyPair,
}

#[wasm_bindgen]
impl RholoKey {
    #[wasm_bindgen(constructor)]
    pub fn new(secret_hex: &str) -> Result<RholoKey, JsValue> {
        Ok(Self {
            key: KeyPair::from_secret_hex(secret_hex).map_err(js_error)?,
        })
    }

    pub fn generate() -> Result<RholoKey, JsValue> {
        Ok(Self {
            key: KeyPair::generate().map_err(js_error)?,
        })
    }

    pub fn public_hex(&self) -> String {
        self.key.public_hex()
    }

    pub fn rev_address(&self) -> Result<String, JsValue> {
        self.key.rev_address().map_err(js_error)
    }

    /// Sign a 32-byte digest and return the DER low-S signature as lowercase hex. This is
    /// the shape `rho:crypto:secp256k1Verify` verifies.
    pub fn sign_digest_hex(&self, digest_hex: &str) -> Result<String, JsValue> {
        let digest = from_hex(digest_hex).map_err(js_error)?;
        if digest.len() != 32 {
            return Err(js_error("digest must be 32 bytes"));
        }
        let signature = self.key.sign_prehash(&digest).map_err(js_error)?;
        Ok(to_hex(&signature))
    }
}

/// A browser-side rholo client. Reads and signed deploys use the pinned r-cash client
/// over the wasm HTTP transport; the secret never leaves the browser except as a
/// signature.
#[wasm_bindgen]
pub struct RholoClient {
    node: RholoNode,
}

#[wasm_bindgen]
impl RholoClient {
    #[wasm_bindgen(constructor)]
    pub fn new(node_url: String) -> Result<RholoClient, JsValue> {
        Ok(Self {
            node: RholoNode::new(node_url).map_err(js_error)?,
        })
    }

    pub async fn status(&self) -> Result<String, JsValue> {
        let status = self.node.status().await.map_err(js_error)?;
        serde_json::to_string(&status).map_err(js_error)
    }

    pub async fn explore(&self, term: String) -> Result<String, JsValue> {
        let response = self.node.explore(&term).await.map_err(js_error)?;
        serde_json::to_string(&serde_json::json!({
            "expr": response.expr,
            "reply_source": response.reply_source,
            "block": block_json(&response.block),
        }))
        .map_err(js_error)
    }

    /// Sign and submit a deploy. The shard id, anchor height and minimum phlo price are
    /// read from the node, matching the r-wallet behaviour.
    pub async fn deploy(
        &self,
        term: String,
        secret_hex: String,
        phlo_limit: i64,
    ) -> Result<String, JsValue> {
        let status = self.node.status().await.map_err(js_error)?;
        let shard = status
            .get("shardId")
            .and_then(|value| value.as_str())
            .unwrap_or("/root")
            .to_string();
        let height = status
            .get("latestBlockNumber")
            .and_then(|value| value.as_i64())
            .unwrap_or(0);
        let price = status
            .get("minPhloPrice")
            .and_then(|value| value.as_i64())
            .unwrap_or(1)
            .max(1);
        let key = KeyPair::from_secret_hex(&secret_hex).map_err(js_error)?;
        let data = DeployOptions::new(term)
            .phlo(phlo_limit, price)
            .shard_id(shard)
            .valid_after_block_number(height)
            .build()
            .map_err(js_error)?;
        let signed = key.sign_deploy(data).map_err(js_error)?;
        self.node.deploy(&signed).await.map_err(js_error)
    }

    pub async fn deploy_status(&self, deploy_id: String) -> Result<String, JsValue> {
        let status = self
            .node
            .deploy_status(&deploy_id)
            .await
            .map_err(js_error)?;
        let value = match status {
            DeployStatus::ProcessedWithSuccess {
                deploy_result,
                block,
            } => serde_json::json!({
                "state": "processedWithSuccess",
                "deploy_result": deploy_result,
                "block": block_json(&block),
            }),
            DeployStatus::ProcessedWithError {
                deploy_error,
                block,
            } => serde_json::json!({
                "state": "processedWithError",
                "deploy_error": deploy_error,
                "block": block_json(&block),
            }),
            DeployStatus::NotProcessed { status } => serde_json::json!({
                "state": "notProcessed",
                "status": status,
            }),
        };
        serde_json::to_string(&value).map_err(js_error)
    }

    pub async fn is_finalized(&self, block_hash: String) -> Result<bool, JsValue> {
        self.node.is_finalized(&block_hash).await.map_err(js_error)
    }
}

fn block_json(block: &rbridge_chain::BlockInfo) -> serde_json::Value {
    serde_json::json!({
        "block_hash": block.block_hash,
        "block_number": block.block_number,
        "shard_id": block.shard_id,
        "timestamp": block.timestamp,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_is_reported() {
        assert!(!version().is_empty());
    }
}
