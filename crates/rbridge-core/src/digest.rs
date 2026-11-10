use serde::{Deserialize, Serialize};
use sha3::{Digest, Keccak256};

use crate::asset::AssetRef;
use crate::chain::Chain;
use crate::error::BridgeError;
use crate::to_hex;

/// The protocol tag. Changing it is a protocol change; bump the version, never mutate it.
pub const PROTOCOL_TAG: &str = "rbridge:v1";

/// Which way value is moving across the bridge.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Direction {
    Deposit,
    Withdraw,
}

impl Direction {
    pub const fn as_str(self) -> &'static str {
        match self {
            Direction::Deposit => "deposit",
            Direction::Withdraw => "withdraw",
        }
    }
}

impl std::str::FromStr for Direction {
    type Err = BridgeError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "deposit" => Ok(Direction::Deposit),
            "withdraw" => Ok(Direction::Withdraw),
            _ => Err(BridgeError::InvalidField {
                field: "direction",
                reason: "must be deposit or withdraw",
            }),
        }
    }
}

impl std::fmt::Display for Direction {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// The exact message a relayer signs.
///
/// The canonical form is a delimiter-separated ASCII string, not an ABI encoding, because
/// the same bytes must be reproducible in Rholang (`String.toByteArray` + `keccak256Hash`)
/// and in Solidity/TVM (`keccak256(bytes)`). Every field is validated so a `|` cannot be
/// smuggled in to shift a boundary.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttestationMessage {
    pub network: String,
    pub chain: Chain,
    pub bridge_id: String,
    pub asset: AssetRef,
    pub direction: Direction,
    pub external_tx_id: String,
    /// Amount in rholo base units. Positive; direction carries the sign of the movement.
    pub amount: i64,
    pub recipient: String,
    pub nonce: u64,
}

impl AttestationMessage {
    pub fn canonical(&self) -> String {
        format!(
            "{PROTOCOL_TAG}|{}|{}|{}|{}|{}|{}|{}|{}|{}",
            self.network,
            self.chain.as_str(),
            self.bridge_id,
            self.asset.as_string(),
            self.direction.as_str(),
            self.external_tx_id,
            self.amount,
            self.recipient,
            self.nonce
        )
    }

    pub fn validate(&self) -> Result<(), BridgeError> {
        check_field("network", &self.network)?;
        check_field("bridge_id", &self.bridge_id)?;
        check_field("external_tx_id", &self.external_tx_id)?;
        check_field("recipient", &self.recipient)?;
        if self.amount <= 0 {
            return Err(BridgeError::InvalidField {
                field: "amount",
                reason: "must be positive",
            });
        }
        Ok(())
    }

    /// The 32-byte keccak256 digest the relayers sign.
    pub fn digest(&self) -> Result<[u8; 32], BridgeError> {
        self.validate()?;
        let mut hasher = Keccak256::new();
        hasher.update(self.canonical().as_bytes());
        Ok(hasher.finalize().into())
    }

    /// Lowercase hex of [`Self::digest`].
    pub fn digest_hex(&self) -> Result<String, BridgeError> {
        Ok(to_hex(&self.digest()?))
    }
}

fn check_field(field: &'static str, value: &str) -> Result<(), BridgeError> {
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::asset::AssetRef;

    fn message() -> AttestationMessage {
        AttestationMessage {
            network: "devnet".to_string(),
            chain: Chain::Ethereum,
            bridge_id: "rho:id:bridge".to_string(),
            asset: AssetRef::new(Chain::Ethereum, "usdt").expect("asset"),
            direction: Direction::Deposit,
            external_tx_id: "0xabc:0".to_string(),
            amount: 1_000_000,
            recipient: "rho:id:recipient".to_string(),
            nonce: 7,
        }
    }

    #[test]
    fn canonical_form_is_stable() {
        assert_eq!(
            message().canonical(),
            "rbridge:v1|devnet|ethereum|rho:id:bridge|ethereum.usdt|deposit|0xabc:0|1000000|rho:id:recipient|7"
        );
    }

    #[test]
    fn digest_matches_the_shared_golden_vector() {
        // Computed with js-sha3 from the canonical string above. The Rholang and Solidity
        // implementations must reproduce this exact value.
        assert_eq!(
            message().digest_hex().expect("digest"),
            "b21892a96916dfd84579a2d31b6e64db43a6e8d1e94e5e360f8dea608bbd0a22"
        );
    }

    #[test]
    fn every_field_is_bound() {
        let base = message().digest_hex().expect("digest");
        let cases = [
            AttestationMessage {
                network: "testnet".to_string(),
                ..message()
            },
            AttestationMessage {
                chain: Chain::Tron,
                ..message()
            },
            AttestationMessage {
                bridge_id: "rho:id:other".to_string(),
                ..message()
            },
            AttestationMessage {
                asset: AssetRef::new(Chain::Tron, "usdt").expect("asset"),
                ..message()
            },
            AttestationMessage {
                direction: Direction::Withdraw,
                ..message()
            },
            AttestationMessage {
                external_tx_id: "0xabc:1".to_string(),
                ..message()
            },
            AttestationMessage {
                amount: 1_000_001,
                ..message()
            },
            AttestationMessage {
                recipient: "rho:id:other".to_string(),
                ..message()
            },
            AttestationMessage {
                nonce: 8,
                ..message()
            },
        ];
        for case in cases {
            assert_ne!(case.digest_hex().expect("digest"), base);
        }
    }

    #[test]
    fn delimiter_and_empty_fields_are_refused() {
        let mut case = message();
        case.recipient = "a|b".to_string();
        assert!(case.digest().is_err());
        case.recipient = String::new();
        assert!(case.digest().is_err());
        let mut case = message();
        case.amount = 0;
        assert!(case.digest().is_err());
        let mut case = message();
        case.amount = -1;
        assert!(case.digest().is_err());
    }
}
