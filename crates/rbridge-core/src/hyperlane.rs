//! Hyperlane v3 message, checkpoint and r-bridge payload encoding.
//!
//! The on-chain format is fixed by Hyperlane's `Message.sol` and `CheckpointLib.sol`:
//! a 77-byte header followed by an opaque body, `keccak256` for the message id, and an
//! EIP-191 prefixed checkpoint digest for validators. The r-bridge payload rides in the
//! body and follows the same delimiter rules as [`crate::digest::AttestationMessage`].
//!
//! The golden vectors below are shared with the Rholang implementation and the
//! companion Solidity peer; they were computed independently with `cast keccak`.

use serde::{Deserialize, Serialize};

use crate::digest::Direction;
use crate::error::BridgeError;
use crate::{keccak256, to_hex};

/// The only message version this implementation speaks.
pub const VERSION: u8 = 3;
/// `version(1) + nonce(4) + origin(4) + sender(32) + destination(4) + recipient(32)`.
pub const HEADER_LEN: usize = 77;
/// OpenZeppelin's `ECDSA.toEthSignedMessageHash` prefix for a 32-byte digest.
pub const EIP191_PREFIX: &[u8] = b"\x19Ethereum Signed Message:\n32";
/// The Hyperlane checkpoint domain tag.
pub const CHECKPOINT_TAG: &[u8] = b"HYPERLANE";
/// The r-bridge payload tag inside a Hyperlane message body.
pub const PAYLOAD_TAG: &str = "rbridge:hyperlane:v1";
/// One Ethereum-style `r || s || v` signature.
pub const SIGNATURE_LEN: usize = 65;
/// `originMerkleTree(32) + root(32) + index(4)`; the signatures follow.
pub const METADATA_HEADER_LEN: usize = 68;
/// A payload has the tag plus six fields.
const PAYLOAD_FIELDS: usize = 7;

/// A Hyperlane v3 message.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Message {
    pub version: u8,
    pub nonce: u32,
    pub origin: u32,
    pub sender: [u8; 32],
    pub destination: u32,
    pub recipient: [u8; 32],
    pub body: Vec<u8>,
}

impl Message {
    /// Build a version-3 message. The caller supplies the origin nonce.
    pub fn new(
        nonce: u32,
        origin: u32,
        sender: [u8; 32],
        destination: u32,
        recipient: [u8; 32],
        body: Vec<u8>,
    ) -> Self {
        Self {
            version: VERSION,
            nonce,
            origin,
            sender,
            destination,
            recipient,
            body,
        }
    }

    /// The exact bytes dispatched on the origin chain.
    pub fn encode(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(HEADER_LEN + self.body.len());
        out.push(self.version);
        out.extend_from_slice(&self.nonce.to_be_bytes());
        out.extend_from_slice(&self.origin.to_be_bytes());
        out.extend_from_slice(&self.sender);
        out.extend_from_slice(&self.destination.to_be_bytes());
        out.extend_from_slice(&self.recipient);
        out.extend_from_slice(&self.body);
        out
    }

    /// `keccak256(encode())`.
    pub fn id(&self) -> [u8; 32] {
        keccak256(&self.encode())
    }

    /// Lowercase hex of [`Self::id`].
    pub fn id_hex(&self) -> String {
        to_hex(&self.id())
    }

    /// Parse a dispatched message. A wrong version is refused.
    pub fn decode(bytes: &[u8]) -> Result<Self, BridgeError> {
        if bytes.len() < HEADER_LEN {
            return Err(BridgeError::InvalidField {
                field: "hyperlane_message",
                reason: "shorter than the 77-byte header",
            });
        }
        let version = bytes[0];
        if version != VERSION {
            return Err(BridgeError::InvalidField {
                field: "hyperlane_message.version",
                reason: "unsupported message version",
            });
        }
        let nonce = u32::from_be_bytes([bytes[1], bytes[2], bytes[3], bytes[4]]);
        let origin = u32::from_be_bytes([bytes[5], bytes[6], bytes[7], bytes[8]]);
        let mut sender = [0u8; 32];
        sender.copy_from_slice(&bytes[9..41]);
        let destination = u32::from_be_bytes([bytes[41], bytes[42], bytes[43], bytes[44]]);
        let mut recipient = [0u8; 32];
        recipient.copy_from_slice(&bytes[45..77]);
        Ok(Self {
            version,
            nonce,
            origin,
            sender,
            destination,
            recipient,
            body: bytes[HEADER_LEN..].to_vec(),
        })
    }

    /// The 20-byte address encoded in the low bytes of `sender` (EVM convention).
    pub fn sender_address(&self) -> [u8; 20] {
        bytes32_to_address(self.sender)
    }

    /// The 20-byte address encoded in the low bytes of `recipient` (EVM convention).
    pub fn recipient_address(&self) -> [u8; 20] {
        bytes32_to_address(self.recipient)
    }
}

/// The checkpoint digest a Hyperlane validator signs.
///
/// `eth_sign(keccak256(keccak256(origin || merkleTree || "HYPERLANE") || root || index
/// || messageId))`, matching `CheckpointLib.digest` in the Hyperlane EVM implementation.
pub fn checkpoint_digest(
    origin: u32,
    origin_merkle_tree: [u8; 32],
    root: [u8; 32],
    index: u32,
    message_id: [u8; 32],
) -> [u8; 32] {
    let mut domain_input = Vec::with_capacity(4 + 32 + CHECKPOINT_TAG.len());
    domain_input.extend_from_slice(&origin.to_be_bytes());
    domain_input.extend_from_slice(&origin_merkle_tree);
    domain_input.extend_from_slice(CHECKPOINT_TAG);
    let domain = keccak256(&domain_input);

    let mut checkpoint_input = Vec::with_capacity(32 + 32 + 4 + 32);
    checkpoint_input.extend_from_slice(&domain);
    checkpoint_input.extend_from_slice(&root);
    checkpoint_input.extend_from_slice(&index.to_be_bytes());
    checkpoint_input.extend_from_slice(&message_id);
    eth_signed_message_hash(keccak256(&checkpoint_input))
}

/// `keccak256("\x19Ethereum Signed Message:\n32" || digest)`.
pub fn eth_signed_message_hash(digest: [u8; 32]) -> [u8; 32] {
    let mut input = Vec::with_capacity(EIP191_PREFIX.len() + 32);
    input.extend_from_slice(EIP191_PREFIX);
    input.extend_from_slice(&digest);
    keccak256(&input)
}

/// Multisig ISM metadata for a message-id checkpoint.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct IsmMetadata {
    pub origin_merkle_tree: [u8; 32],
    pub root: [u8; 32],
    pub index: u32,
    /// Ethereum-style 65-byte `r || s || v` signatures.
    pub signatures: Vec<[u8; SIGNATURE_LEN]>,
}

impl IsmMetadata {
    pub fn new(
        origin_merkle_tree: [u8; 32],
        root: [u8; 32],
        index: u32,
        signatures: Vec<[u8; SIGNATURE_LEN]>,
    ) -> Self {
        Self {
            origin_merkle_tree,
            root,
            index,
            signatures,
        }
    }

    /// `originMerkleTree || root || index || signatures`.
    pub fn encode(&self) -> Vec<u8> {
        let mut out =
            Vec::with_capacity(METADATA_HEADER_LEN + self.signatures.len() * SIGNATURE_LEN);
        out.extend_from_slice(&self.origin_merkle_tree);
        out.extend_from_slice(&self.root);
        out.extend_from_slice(&self.index.to_be_bytes());
        for signature in &self.signatures {
            out.extend_from_slice(signature);
        }
        out
    }

    /// Parse metadata; the tail must be a whole number of 65-byte signatures.
    pub fn decode(bytes: &[u8]) -> Result<Self, BridgeError> {
        if bytes.len() < METADATA_HEADER_LEN {
            return Err(BridgeError::InvalidField {
                field: "ism_metadata",
                reason: "shorter than the 68-byte header",
            });
        }
        let tail = bytes.len() - METADATA_HEADER_LEN;
        if !tail.is_multiple_of(SIGNATURE_LEN) {
            return Err(BridgeError::InvalidField {
                field: "ism_metadata",
                reason: "signature tail is not a multiple of 65 bytes",
            });
        }
        let mut origin_merkle_tree = [0u8; 32];
        origin_merkle_tree.copy_from_slice(&bytes[0..32]);
        let mut root = [0u8; 32];
        root.copy_from_slice(&bytes[32..64]);
        let index = u32::from_be_bytes([bytes[64], bytes[65], bytes[66], bytes[67]]);
        let mut signatures = Vec::with_capacity(tail / SIGNATURE_LEN);
        for chunk in bytes[METADATA_HEADER_LEN..].chunks_exact(SIGNATURE_LEN) {
            let mut signature = [0u8; SIGNATURE_LEN];
            signature.copy_from_slice(chunk);
            signatures.push(signature);
        }
        Ok(Self {
            origin_merkle_tree,
            root,
            index,
            signatures,
        })
    }

    pub fn signature_count(&self) -> usize {
        self.signatures.len()
    }
}

/// The r-bridge action carried in a Hyperlane body.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Payload {
    pub action: Direction,
    pub asset_key: String,
    /// Amount in rholo base units.
    pub amount: i64,
    /// rholo address for a deposit; native address for a withdrawal.
    pub recipient: String,
    /// Native deposit locator or rholo burn id.
    pub external_id: String,
    pub nonce: u64,
}

impl Payload {
    pub fn canonical(&self) -> String {
        format!(
            "{PAYLOAD_TAG}|{}|{}|{}|{}|{}|{}",
            self.action.as_str(),
            self.asset_key,
            self.amount,
            self.recipient,
            self.external_id,
            self.nonce
        )
    }

    pub fn validate(&self) -> Result<(), BridgeError> {
        check_payload_field("asset_key", &self.asset_key)?;
        check_payload_field("recipient", &self.recipient)?;
        check_payload_field("external_id", &self.external_id)?;
        if self.amount <= 0 {
            return Err(BridgeError::InvalidField {
                field: "amount",
                reason: "must be positive",
            });
        }
        Ok(())
    }

    /// The UTF-8 bytes carried in a Hyperlane body.
    pub fn encode(&self) -> Result<Vec<u8>, BridgeError> {
        self.validate()?;
        Ok(self.canonical().into_bytes())
    }

    /// Parse a body. Exactly seven `|`-separated fields are required, so a delimiter
    /// smuggled into a field is refused rather than shifting a boundary.
    pub fn parse(body: &[u8]) -> Result<Self, BridgeError> {
        let text = std::str::from_utf8(body).map_err(|_| BridgeError::InvalidField {
            field: "payload",
            reason: "is not valid UTF-8",
        })?;
        let fields: Vec<&str> = text.split('|').collect();
        if fields.len() != PAYLOAD_FIELDS {
            return Err(BridgeError::InvalidField {
                field: "payload",
                reason: "expected the tag and six fields",
            });
        }
        if fields[0] != PAYLOAD_TAG {
            return Err(BridgeError::InvalidField {
                field: "payload.tag",
                reason: "unknown payload tag",
            });
        }
        let action = fields[1].parse::<Direction>()?;
        let amount = fields[3]
            .parse::<i64>()
            .map_err(|_| BridgeError::InvalidField {
                field: "payload.amount",
                reason: "is not a signed integer",
            })?;
        let nonce = fields[6]
            .parse::<u64>()
            .map_err(|_| BridgeError::InvalidField {
                field: "payload.nonce",
                reason: "is not an unsigned integer",
            })?;
        let payload = Self {
            action,
            asset_key: fields[2].to_string(),
            amount,
            recipient: fields[4].to_string(),
            external_id: fields[5].to_string(),
            nonce,
        };
        payload.validate()?;
        Ok(payload)
    }
}

fn check_payload_field(field: &'static str, value: &str) -> Result<(), BridgeError> {
    if value.is_empty() {
        return Err(BridgeError::InvalidField {
            field,
            reason: "must not be empty",
        });
    }
    if value.len() > 256 {
        return Err(BridgeError::InvalidField {
            field,
            reason: "must be at most 256 bytes",
        });
    }
    if value.contains('|') {
        return Err(BridgeError::InvalidField {
            field,
            reason: "must not contain '|'",
        });
    }
    Ok(())
}

/// Left-pad an EVM address into Hyperlane's `bytes32` address type.
pub fn address_to_bytes32(address: [u8; 20]) -> [u8; 32] {
    let mut out = [0u8; 32];
    out[12..].copy_from_slice(&address);
    out
}

/// Read the low 20 bytes of a Hyperlane `bytes32` address.
pub fn bytes32_to_address(word: [u8; 32]) -> [u8; 20] {
    let mut out = [0u8; 20];
    out.copy_from_slice(&word[12..]);
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::from_hex;

    fn sample_address(last: u8) -> [u8; 20] {
        let mut address = [0u8; 20];
        address[19] = last;
        address
    }

    fn sample_payload() -> Payload {
        Payload {
            action: Direction::Deposit,
            asset_key: "ethereum.usdt".to_string(),
            amount: 1_000_000,
            recipient: "rho:id:recipient".to_string(),
            external_id: "0xabc:0".to_string(),
            nonce: 7,
        }
    }

    fn sample_message() -> Message {
        Message::new(
            7,
            11_155_111,
            address_to_bytes32(sample_address(0xaa)),
            84_532,
            address_to_bytes32(sample_address(0xbb)),
            sample_payload().encode().expect("payload"),
        )
    }

    #[test]
    fn payload_canonical_matches_spec() {
        assert_eq!(
            sample_payload().canonical(),
            "rbridge:hyperlane:v1|deposit|ethereum.usdt|1000000|rho:id:recipient|0xabc:0|7"
        );
        assert_eq!(
            crate::keccak256_hex(&sample_payload().encode().expect("payload")),
            "f1002c175ee8b36016c88541a7e5999996266b07214ab76367e11683cfe06770"
        );
    }

    #[test]
    fn payload_round_trips() {
        let payload = sample_payload();
        let encoded = payload.encode().expect("encode");
        assert_eq!(Payload::parse(&encoded).expect("parse"), payload);
    }

    #[test]
    fn payload_refuses_delimiter_injection() {
        let mut payload = sample_payload();
        payload.recipient = "rho:id:a|b".to_string();
        assert!(payload.encode().is_err());
        assert!(Payload::parse(b"rbridge:hyperlane:v1|deposit|a|1|b|c|0|extra").is_err());
        assert!(Payload::parse(b"wrong:v1|deposit|a|1|b|c|0").is_err());
        assert!(Payload::parse(b"rbridge:hyperlane:v1|deposit|a|0|b|c|0").is_err());
    }

    #[test]
    fn message_encoding_matches_golden() {
        let message = sample_message();
        let encoded = message.encode();
        assert_eq!(encoded.len(), HEADER_LEN + 77);
        let expected = concat!(
            "030000000700aa36a7",
            "00000000000000000000000000000000000000000000000000000000000000aa",
            "00014a34",
            "00000000000000000000000000000000000000000000000000000000000000bb",
            "726272696467653a68797065726c616e653a76317c6465706f7369747c657468657265756d",
            "2e757364747c313030303030307c72686f3a69643a726563697069656e747c30786162633a",
            "307c37",
        );
        assert_eq!(to_hex(&encoded), expected);
        assert_eq!(
            message.id_hex(),
            "f44504e00b9ef65496c962d2c682804f0ec047ee58f0b3cd30c6b116895e04e9"
        );
    }

    #[test]
    fn message_decode_round_trips() {
        let message = sample_message();
        let decoded = Message::decode(&message.encode()).expect("decode");
        assert_eq!(decoded, message);
        assert_eq!(decoded.sender_address(), sample_address(0xaa));
        assert_eq!(decoded.recipient_address(), sample_address(0xbb));
        assert!(Message::decode(&message.encode()[..HEADER_LEN - 1]).is_err());

        let mut wrong_version = message.encode();
        wrong_version[0] = 2;
        assert!(Message::decode(&wrong_version).is_err());
    }

    #[test]
    fn checkpoint_digest_matches_golden() {
        let message = sample_message();
        let digest = checkpoint_digest(11_155_111, [0x11; 32], [0x22; 32], 3, message.id());
        assert_eq!(
            to_hex(&digest),
            "a4411138366886244ae59b3f44587dc9f12edd373b6c0603f8909e3785e3d963"
        );
    }

    #[test]
    fn ism_metadata_round_trips() {
        let metadata = IsmMetadata::new(
            [0x11; 32],
            [0x22; 32],
            3,
            vec![[0x33; SIGNATURE_LEN], [0x44; SIGNATURE_LEN]],
        );
        let encoded = metadata.encode();
        assert_eq!(encoded.len(), METADATA_HEADER_LEN + 2 * SIGNATURE_LEN);
        assert_eq!(IsmMetadata::decode(&encoded).expect("decode"), metadata);
        assert!(IsmMetadata::decode(&encoded[..encoded.len() - 1]).is_err());
    }

    #[test]
    fn address_padding_is_lossless() {
        let address = sample_address(0xaa);
        let word = address_to_bytes32(address);
        assert_eq!(&word[..12], &[0u8; 12]);
        assert_eq!(bytes32_to_address(word), address);
        assert_eq!(from_hex(&to_hex(&word)).expect("hex"), word.to_vec());
    }
}
