//! Pure r-bridge types: chains, chain-qualified assets, amount scaling, deposit and
//! withdrawal ids, the relayer set and the cross-chain attestation digest.
//!
//! Nothing here performs I/O. The digest is the contract between the rholo bridge
//! contract, the native vaults and the relayer; its golden vector is shared with the
//! Rholang and Solidity implementations.

#![forbid(unsafe_code)]

pub mod amount;
pub mod asset;
pub mod chain;
pub mod digest;
pub mod error;
pub mod ids;
pub mod relayer;

pub use amount::Amount;
pub use asset::{initial_registry, AssetId, AssetRef, AssetSpec};
pub use chain::Chain;
pub use digest::{AttestationMessage, Direction, PROTOCOL_TAG};
pub use error::BridgeError;
pub use ids::{DepositId, WithdrawalId};
pub use relayer::RelayerSet;

/// The hard client budget for one deploy term; the node cap is 64 KiB.
pub const PROJECT_TERM_BUDGET: usize = 56 * 1024;

/// Lowercase hex encoding. Kept local so the core crate has no encoding dependency.
pub fn to_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[usize::from(byte >> 4)] as char);
        out.push(HEX[usize::from(byte & 0x0f)] as char);
    }
    out
}

/// Strict lowercase/uppercase hex decoding; odd length and non-hex are refused.
pub fn from_hex(text: &str) -> Result<Vec<u8>, BridgeError> {
    if !text.len().is_multiple_of(2) || !text.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err(BridgeError::BadHex(text.to_string()));
    }
    let mut out = Vec::with_capacity(text.len() / 2);
    let bytes = text.as_bytes();
    for pair in bytes.chunks_exact(2) {
        let hi = (pair[0] as char)
            .to_digit(16)
            .ok_or_else(|| BridgeError::BadHex(text.to_string()))?;
        let lo = (pair[1] as char)
            .to_digit(16)
            .ok_or_else(|| BridgeError::BadHex(text.to_string()))?;
        out.push(((hi << 4) | lo) as u8);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_round_trips() {
        let bytes = [0x00, 0x0f, 0xa5, 0xff];
        let text = to_hex(&bytes);
        assert_eq!(text, "000fa5ff");
        assert_eq!(from_hex(&text).expect("decode"), bytes.to_vec());
    }

    #[test]
    fn bad_hex_is_refused() {
        assert!(from_hex("abc").is_err());
        assert!(from_hex("zz").is_err());
    }
}
