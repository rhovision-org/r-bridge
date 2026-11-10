use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};

use crate::error::BridgeError;

/// The on-chain relayer set and its quorum. Public keys are 65-byte uncompressed
/// secp256k1 keys in lowercase hex (130 characters), matching what
/// `rho:rchain:deployerId` and `rho:crypto:secp256k1Verify` consume.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RelayerSet {
    pub pubkeys: Vec<String>,
    pub threshold: u16,
}

impl RelayerSet {
    pub fn new(pubkeys: Vec<String>, threshold: u16) -> Result<Self, BridgeError> {
        if pubkeys.is_empty() {
            return Err(BridgeError::BadRelayerSet("must not be empty"));
        }
        if pubkeys.len() > 15 {
            return Err(BridgeError::BadRelayerSet("at most 15 signers"));
        }
        if threshold == 0 {
            return Err(BridgeError::BadRelayerSet("threshold must be positive"));
        }
        if usize::from(threshold) > pubkeys.len() {
            return Err(BridgeError::BadRelayerSet(
                "threshold must not exceed the signer count",
            ));
        }
        let mut seen = BTreeSet::new();
        let mut normalised = Vec::with_capacity(pubkeys.len());
        for key in pubkeys {
            let key = key.to_ascii_lowercase();
            let valid = key.len() == 130 && key.chars().all(|c| c.is_ascii_hexdigit());
            if !valid {
                return Err(BridgeError::BadRelayerSet(
                    "keys must be 65-byte uncompressed secp256k1 hex",
                ));
            }
            if !seen.insert(key.clone()) {
                return Err(BridgeError::BadRelayerSet("duplicate signer key"));
            }
            normalised.push(key);
        }
        Ok(Self {
            pubkeys: normalised,
            threshold,
        })
    }

    pub fn is_quorum(&self, valid_signatures: usize) -> bool {
        valid_signatures >= usize::from(self.threshold)
    }

    pub fn threshold(&self) -> usize {
        usize::from(self.threshold)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key(byte: char) -> String {
        format!("04{}", byte.to_string().repeat(128))
    }

    #[test]
    fn a_two_of_three_set_is_valid() {
        let set = RelayerSet::new(vec![key('a'), key('b'), key('c')], 2).expect("set");
        assert_eq!(set.threshold(), 2);
        assert!(!set.is_quorum(1));
        assert!(set.is_quorum(2));
        assert!(set.is_quorum(3));
    }

    #[test]
    fn malformed_sets_are_refused() {
        assert!(RelayerSet::new(vec![], 1).is_err());
        assert!(RelayerSet::new(vec![key('a')], 2).is_err());
        assert!(RelayerSet::new(vec![key('a')], 0).is_err());
        assert!(RelayerSet::new(vec![key('a'), key('a')], 1).is_err());
        assert!(RelayerSet::new(vec!["abc".to_string()], 1).is_err());
    }
}
