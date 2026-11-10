//! Browser facade.
//!
//! MetaMask, TronLink and Keplr own the native-chain accounts. This crate owns only the
//! one thing they cannot do: the rholo account and the node's deploy/attestation
//! signature format. Amounts cross the boundary as strings so no JavaScript number
//! ever truncates a base-unit value.

#![forbid(unsafe_code)]

use wasm_bindgen::prelude::*;

use rbridge_chain::KeyPair;
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_is_reported() {
        assert!(!version().is_empty());
    }
}
