use serde::{Deserialize, Serialize};

use crate::error::BridgeError;

/// An amount in rholo base units. The node's ERTP ledger holds an `i64`, so this is the
/// range a wrapped balance can occupy.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
#[serde(transparent)]
pub struct Amount(pub i64);

impl Amount {
    pub const fn raw(value: i64) -> Self {
        Self(value)
    }

    pub const fn value(self) -> i64 {
        self.0
    }

    /// Convert a native base-unit amount into rholo base units.
    ///
    /// When the native precision is finer than the rholo precision, the input must be an
    /// exact multiple of the scale quantum. Dust is refused rather than rounded: minting
    /// less than was locked breaks conservation, and minting more is theft.
    pub fn scale_from_native(
        native: u128,
        native_decimals: u8,
        rholo_decimals: u8,
    ) -> Result<Self, BridgeError> {
        if native_decimals > 38 || rholo_decimals > 38 {
            return Err(BridgeError::AmountOutOfRange);
        }
        let scaled = if rholo_decimals <= native_decimals {
            let quantum = 10_u128
                .checked_pow(u32::from(native_decimals - rholo_decimals))
                .ok_or(BridgeError::AmountOutOfRange)?;
            if !native.is_multiple_of(quantum) {
                return Err(BridgeError::DustNotAllowed);
            }
            native / quantum
        } else {
            let factor = 10_u128
                .checked_pow(u32::from(rholo_decimals - native_decimals))
                .ok_or(BridgeError::AmountOutOfRange)?;
            native
                .checked_mul(factor)
                .ok_or(BridgeError::AmountOutOfRange)?
        };
        if scaled > i64::MAX as u128 {
            return Err(BridgeError::AmountOutOfRange);
        }
        Ok(Self(scaled as i64))
    }

    /// Convert rholo base units back to native base units.
    pub fn scale_to_native(
        self,
        native_decimals: u8,
        rholo_decimals: u8,
    ) -> Result<u128, BridgeError> {
        if self.0 < 0 {
            return Err(BridgeError::AmountOutOfRange);
        }
        let value = self.0 as u128;
        if rholo_decimals <= native_decimals {
            let factor = 10_u128
                .checked_pow(u32::from(native_decimals - rholo_decimals))
                .ok_or(BridgeError::AmountOutOfRange)?;
            value
                .checked_mul(factor)
                .ok_or(BridgeError::AmountOutOfRange)
        } else {
            let quantum = 10_u128
                .checked_pow(u32::from(rholo_decimals - native_decimals))
                .ok_or(BridgeError::AmountOutOfRange)?;
            if !value.is_multiple_of(quantum) {
                return Err(BridgeError::DustNotAllowed);
            }
            Ok(value / quantum)
        }
    }

    /// Render exactly in the given precision, trimming trailing zeros.
    pub fn to_decimal(self, decimals: u8) -> String {
        let negative = self.0 < 0;
        let magnitude = (self.0 as i128).unsigned_abs();
        let factor = 10_u128.pow(u32::from(decimals));
        let whole = magnitude / factor;
        let frac = magnitude % factor;
        let sign = if negative { "-" } else { "" };
        if frac == 0 {
            format!("{sign}{whole}")
        } else {
            let frac = format!("{frac:0width$}", width = usize::from(decimals));
            format!("{sign}{whole}.{}", frac.trim_end_matches('0'))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn eth_scales_from_wei_to_eight_decimals() {
        let one_eth = 10_u128.pow(18);
        let scaled = Amount::scale_from_native(one_eth, 18, 8).expect("scale");
        assert_eq!(scaled.value(), 100_000_000);
        assert_eq!(scaled.to_decimal(8), "1");
    }

    #[test]
    fn dust_below_the_quantum_is_refused() {
        assert_eq!(
            Amount::scale_from_native(1, 18, 8),
            Err(BridgeError::DustNotAllowed)
        );
        assert_eq!(
            Amount::scale_from_native(10_u128.pow(11), 18, 8),
            Ok(Amount(10))
        );
    }

    #[test]
    fn stablecoins_are_exact() {
        let one_usdt = 1_000_000_u128;
        let scaled = Amount::scale_from_native(one_usdt, 6, 6).expect("scale");
        assert_eq!(scaled.value(), 1_000_000);
        assert_eq!(scaled.scale_to_native(6, 6), Ok(one_usdt));
    }

    #[test]
    fn overflow_is_refused_not_wrapped() {
        let just_over = (i64::MAX as u128) + 1;
        assert_eq!(
            Amount::scale_from_native(just_over, 8, 8),
            Err(BridgeError::AmountOutOfRange)
        );
    }

    #[test]
    fn negative_amounts_cannot_leave_rholo() {
        assert_eq!(
            Amount(-1).scale_to_native(18, 8),
            Err(BridgeError::AmountOutOfRange)
        );
    }

    #[test]
    fn native_round_trip_is_exact() {
        let native = 123_456_780_000_000_000_u128; // 0.12345678 ETH in wei
        let amount = Amount::scale_from_native(native, 18, 8).expect("scale");
        assert_eq!(amount.scale_to_native(18, 8), Ok(native));
        assert_eq!(amount.to_decimal(8), "0.12345678");
    }
}
