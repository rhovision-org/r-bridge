use thiserror::Error;

/// A refusal from the pure r-bridge layer. Every variant is a fact about the input, not
/// about the network; callers decide whether to retry, abort or surface it.
#[derive(Clone, Debug, Error, PartialEq, Eq)]
pub enum BridgeError {
    #[error("invalid chain: {0}")]
    BadChain(String),
    #[error("invalid asset id: {0}")]
    BadAssetId(String),
    #[error("invalid field {field}: {reason}")]
    InvalidField {
        field: &'static str,
        reason: &'static str,
    },
    #[error("invalid relayer set: {0}")]
    BadRelayerSet(&'static str),
    #[error("invalid hex: {0}")]
    BadHex(String),
    #[error("amount is out of the rholo i64 range")]
    AmountOutOfRange,
    #[error("amount has dust below the rholo scale quantum")]
    DustNotAllowed,
    #[error("unknown asset: {0}")]
    UnknownAsset(String),
    #[error("invalid asset specification: {0}")]
    BadAssetSpec(&'static str),
}
