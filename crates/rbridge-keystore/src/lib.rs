//! Web3 Secret Storage v3 keystore for rholo keys.
//!
//! r-wallet, r-gen and geth all speak this format: scrypt (or PBKDF2) over the password,
//! AES-128-CTR over the private key, and a keccak256 MAC. The key is the same secp256k1
//! secret that addresses a rholo account and an Ethereum account, so a keystore made here
//! opens in r-wallet and vice versa.
//!
//! The JSON `address` field is the lowercase Ethereum address derived from the secret. It
//! is a checksum, not an identity: the REV address is derived separately by the node and
//! shown by the wallet.

#![forbid(unsafe_code)]

use aes::Aes128;
use ctr::cipher::{KeyIvInit, StreamCipher};
use ctr::Ctr128BE;
use k256::elliptic_curve::sec1::ToSec1Point;
use rbridge_core::{from_hex, keccak256, to_hex};
use zeroize::Zeroize;

/// r-wallet's scrypt work factor. 2^17 with r = 8 needs about 128 MiB.
pub const SCRYPT_LOG_N: u8 = 17;
pub const SCRYPT_R: u32 = 8;
pub const SCRYPT_P: u32 = 1;

/// The largest scrypt memory an import may request (128 * n * r bytes). A hostile file
/// could otherwise ask the browser to allocate gigabytes.
const MAX_SCRYPT_MEMORY: u64 = 512 * 1024 * 1024;
const MAX_PBKDF2_ROUNDS: u32 = 10_000_000;
const SECRET_LEN: usize = 32;

#[derive(Debug, thiserror::Error)]
pub enum KeystoreError {
    #[error("password must not be empty")]
    EmptyPassword,
    #[error("invalid keystore: {0}")]
    Invalid(String),
    #[error("unsupported keystore field: {0}")]
    Unsupported(String),
    #[error("wrong password")]
    WrongPassword,
    #[error("invalid private key")]
    InvalidSecret,
    #[error("secure randomness is unavailable")]
    Random,
}

/// Create a v3 keystore from a 32-byte secp256k1 secret and a non-empty password.
///
/// The salt, IV and id are drawn from the platform CSPRNG (`getrandom`, wired to
/// `crypto.getRandomValues` in the browser).
pub fn create(secret: &[u8; SECRET_LEN], password: &str) -> Result<String, KeystoreError> {
    if password.is_empty() {
        return Err(KeystoreError::EmptyPassword);
    }
    validate_secret(secret)?;

    let mut salt = [0u8; 32];
    let mut iv = [0u8; 16];
    let mut uuid = [0u8; 16];
    getrandom::fill(&mut salt).map_err(|_| KeystoreError::Random)?;
    getrandom::fill(&mut iv).map_err(|_| KeystoreError::Random)?;
    getrandom::fill(&mut uuid).map_err(|_| KeystoreError::Random)?;
    uuid[6] = (uuid[6] & 0x0f) | 0x40;
    uuid[8] = (uuid[8] & 0x3f) | 0x80;

    let mut derived = [0u8; 32];
    let params = scrypt::Params::new(SCRYPT_LOG_N, SCRYPT_R, SCRYPT_P)
        .map_err(|error| KeystoreError::Invalid(error.to_string()))?;
    scrypt::scrypt(password.as_bytes(), &salt, &params, &mut derived)
        .map_err(|error| KeystoreError::Invalid(error.to_string()))?;

    let mut ciphertext = secret.to_vec();
    let mut cipher = Ctr128BE::<Aes128>::new_from_slices(&derived[..16], &iv)
        .map_err(|error| KeystoreError::Invalid(error.to_string()))?;
    cipher.apply_keystream(&mut ciphertext);

    let mut mac_input = Vec::with_capacity(16 + ciphertext.len());
    mac_input.extend_from_slice(&derived[16..]);
    mac_input.extend_from_slice(&ciphertext);
    let mac = keccak256(&mac_input);
    derived.zeroize();

    let id = format!(
        "{}-{}-{}-{}-{}",
        to_hex(&uuid[0..4]),
        to_hex(&uuid[4..6]),
        to_hex(&uuid[6..8]),
        to_hex(&uuid[8..10]),
        to_hex(&uuid[10..16])
    );

    let json = serde_json::json!({
        "version": 3,
        "id": id,
        "address": eth_address_hex(secret)?,
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": { "iv": to_hex(&iv) },
            "ciphertext": to_hex(&ciphertext),
            "kdf": "scrypt",
            "kdfparams": {
                "dklen": 32,
                "salt": to_hex(&salt),
                "n": 1u64 << SCRYPT_LOG_N,
                "r": SCRYPT_R,
                "p": SCRYPT_P,
            },
            "mac": to_hex(&mac),
        },
    });
    serde_json::to_string(&json).map_err(|error| KeystoreError::Invalid(error.to_string()))
}

/// Decrypt a v3 keystore and return the 32-byte secret.
///
/// Both scrypt (r-wallet, geth) and PBKDF2-HMAC-SHA256 (geth `--light`) files are
/// accepted. The MAC is checked before decryption, so a wrong password and a corrupt
/// file are the same failure by design.
pub fn unlock(json: &str, password: &str) -> Result<[u8; SECRET_LEN], KeystoreError> {
    if password.is_empty() {
        return Err(KeystoreError::EmptyPassword);
    }
    let root: serde_json::Value =
        serde_json::from_str(json).map_err(|error| KeystoreError::Invalid(error.to_string()))?;
    if root.get("version").and_then(serde_json::Value::as_u64) != Some(3) {
        return Err(KeystoreError::Unsupported("version must be 3".into()));
    }
    let crypto = find_case_insensitive(&root, "crypto")
        .ok_or_else(|| KeystoreError::Invalid("missing crypto section".into()))?;

    let cipher = string_field(crypto, "cipher")?;
    if !cipher.eq_ignore_ascii_case("aes-128-ctr") {
        return Err(KeystoreError::Unsupported(cipher.to_string()));
    }

    let ciphertext = hex_field(crypto, "ciphertext")?;
    let cipherparams = find_case_insensitive(crypto, "cipherparams")
        .ok_or_else(|| KeystoreError::Invalid("missing cipherparams".into()))?;
    let iv = hex_field(cipherparams, "iv")?;
    if iv.len() != 16 {
        return Err(KeystoreError::Invalid("iv must be 16 bytes".into()));
    }
    let mac = hex_field(crypto, "mac")?;
    if mac.len() != 32 {
        return Err(KeystoreError::Invalid("mac must be 32 bytes".into()));
    }
    let kdfparams = find_case_insensitive(crypto, "kdfparams")
        .ok_or_else(|| KeystoreError::Invalid("missing kdfparams".into()))?;
    let salt = hex_field(kdfparams, "salt")?;

    let mut derived = [0u8; 32];
    match string_field(crypto, "kdf")?.to_ascii_lowercase().as_str() {
        "scrypt" => derive_scrypt(kdfparams, password, &salt, &mut derived)?,
        "pbkdf2" => derive_pbkdf2(kdfparams, password, &salt, &mut derived)?,
        other => return Err(KeystoreError::Unsupported(other.to_string())),
    }

    let mut mac_input = Vec::with_capacity(16 + ciphertext.len());
    mac_input.extend_from_slice(&derived[16..]);
    mac_input.extend_from_slice(&ciphertext);
    let expected = keccak256(&mac_input);
    if !constant_time_eq(&expected, &mac) {
        derived.zeroize();
        return Err(KeystoreError::WrongPassword);
    }

    let mut plaintext = ciphertext;
    let mut cipher = Ctr128BE::<Aes128>::new_from_slices(&derived[..16], &iv)
        .map_err(|error| KeystoreError::Invalid(error.to_string()))?;
    cipher.apply_keystream(&mut plaintext);
    derived.zeroize();

    let secret: [u8; SECRET_LEN] = plaintext
        .as_slice()
        .try_into()
        .map_err(|_| KeystoreError::InvalidSecret)?;
    plaintext.zeroize();
    validate_secret(&secret)?;
    Ok(secret)
}

/// The lowercase Ethereum address of a secret, without `0x`.
pub fn eth_address_hex(secret: &[u8; SECRET_LEN]) -> Result<String, KeystoreError> {
    let key = k256::SecretKey::from_slice(secret).map_err(|_| KeystoreError::InvalidSecret)?;
    let point = key.public_key().to_sec1_point(false);
    let hash = keccak256(&point.as_bytes()[1..]);
    Ok(to_hex(&hash[12..]))
}

fn validate_secret(secret: &[u8; SECRET_LEN]) -> Result<(), KeystoreError> {
    k256::SecretKey::from_slice(secret)
        .map(|_| ())
        .map_err(|_| KeystoreError::InvalidSecret)
}

fn derive_scrypt(
    params: &serde_json::Value,
    password: &str,
    salt: &[u8],
    out: &mut [u8; 32],
) -> Result<(), KeystoreError> {
    let dklen = uint_field(params, "dklen")?;
    if dklen != SECRET_LEN as u64 {
        return Err(KeystoreError::Unsupported("dklen must be 32".into()));
    }
    let n = uint_field(params, "n")?;
    let r = uint_field(params, "r")?;
    let p = uint_field(params, "p")?;
    if n < 2 || !n.is_power_of_two() {
        return Err(KeystoreError::Invalid(
            "scrypt n must be a power of two".into(),
        ));
    }
    let memory = 128u64
        .checked_mul(n)
        .and_then(|bytes| bytes.checked_mul(r))
        .ok_or_else(|| KeystoreError::Invalid("scrypt parameters overflow".into()))?;
    if memory > MAX_SCRYPT_MEMORY {
        return Err(KeystoreError::Unsupported(format!(
            "scrypt needs {memory} bytes; limit is {MAX_SCRYPT_MEMORY}"
        )));
    }
    if r == 0 || r > 64 || p == 0 || p > 64 {
        return Err(KeystoreError::Unsupported("scrypt r/p out of range".into()));
    }
    let log_n = u8::try_from(n.trailing_zeros())
        .map_err(|_| KeystoreError::Invalid("scrypt n is too large".into()))?;
    let params = scrypt::Params::new(log_n, r as u32, p as u32)
        .map_err(|error| KeystoreError::Invalid(error.to_string()))?;
    scrypt::scrypt(password.as_bytes(), salt, &params, out)
        .map_err(|error| KeystoreError::Invalid(error.to_string()))
}

fn derive_pbkdf2(
    params: &serde_json::Value,
    password: &str,
    salt: &[u8],
    out: &mut [u8; 32],
) -> Result<(), KeystoreError> {
    let dklen = uint_field(params, "dklen")?;
    if dklen != SECRET_LEN as u64 {
        return Err(KeystoreError::Unsupported("dklen must be 32".into()));
    }
    let rounds = uint_field(params, "c")?;
    if rounds == 0 || rounds > u64::from(MAX_PBKDF2_ROUNDS) {
        return Err(KeystoreError::Unsupported(
            "pbkdf2 round count out of range".into(),
        ));
    }
    if let Some(prf) = params.get("prf").and_then(serde_json::Value::as_str) {
        if !prf.eq_ignore_ascii_case("hmac-sha256") {
            return Err(KeystoreError::Unsupported(prf.to_string()));
        }
    }
    pbkdf2::pbkdf2_hmac::<sha2::Sha256>(password.as_bytes(), salt, rounds as u32, out);
    Ok(())
}

fn find_case_insensitive<'a>(
    value: &'a serde_json::Value,
    name: &str,
) -> Option<&'a serde_json::Value> {
    value
        .as_object()?
        .iter()
        .find(|(key, _)| key.eq_ignore_ascii_case(name))
        .map(|(_, value)| value)
}

fn string_field<'a>(value: &'a serde_json::Value, name: &str) -> Result<&'a str, KeystoreError> {
    find_case_insensitive(value, name)
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| KeystoreError::Invalid(format!("missing {name}")))
}

fn hex_field(value: &serde_json::Value, name: &str) -> Result<Vec<u8>, KeystoreError> {
    let text = string_field(value, name)?;
    from_hex(text).map_err(|error| KeystoreError::Invalid(error.to_string()))
}

fn uint_field(value: &serde_json::Value, name: &str) -> Result<u64, KeystoreError> {
    find_case_insensitive(value, name)
        .and_then(serde_json::Value::as_u64)
        .ok_or_else(|| KeystoreError::Invalid(format!("missing or invalid {name}")))
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right)
        .fold(0u8, |accumulator, (a, b)| accumulator | (a ^ b))
        == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    const SECRET: [u8; 32] = [7u8; 32];

    #[test]
    fn a_created_keystore_round_trips() {
        let json = create(&SECRET, "correct horse").expect("create");
        let value: serde_json::Value = serde_json::from_str(&json).expect("json");
        assert_eq!(value["version"], 3);
        assert_eq!(value["crypto"]["cipher"], "aes-128-ctr");
        assert_eq!(value["crypto"]["kdf"], "scrypt");
        assert_eq!(value["crypto"]["kdfparams"]["n"], 131_072);
        assert_eq!(value["crypto"]["kdfparams"]["r"], 8);
        assert_eq!(value["crypto"]["kdfparams"]["p"], 1);
        assert_eq!(value["crypto"]["kdfparams"]["dklen"], 32);
        assert_eq!(
            value["address"].as_str().expect("address"),
            eth_address_hex(&SECRET).expect("addr")
        );
        assert_eq!(value["address"].as_str().expect("address").len(), 40);
        assert_eq!(unlock(&json, "correct horse").expect("unlock"), SECRET);
    }

    #[test]
    fn a_wrong_password_is_refused() {
        let json = create(&SECRET, "right").expect("create");
        assert!(matches!(
            unlock(&json, "wrong"),
            Err(KeystoreError::WrongPassword)
        ));
    }

    #[test]
    fn an_empty_password_is_refused() {
        assert!(matches!(
            create(&SECRET, ""),
            Err(KeystoreError::EmptyPassword)
        ));
        let json = create(&SECRET, "right").expect("create");
        assert!(matches!(
            unlock(&json, ""),
            Err(KeystoreError::EmptyPassword)
        ));
    }

    #[test]
    fn a_tampered_mac_is_refused() {
        let json = create(&SECRET, "right").expect("create");
        let mut value: serde_json::Value = serde_json::from_str(&json).expect("json");
        value["crypto"]["mac"] = serde_json::Value::String("00".repeat(32));
        assert!(matches!(
            unlock(&value.to_string(), "right"),
            Err(KeystoreError::WrongPassword)
        ));
    }

    #[test]
    fn a_tampered_ciphertext_is_refused() {
        let json = create(&SECRET, "right").expect("create");
        let mut value: serde_json::Value = serde_json::from_str(&json).expect("json");
        value["crypto"]["ciphertext"] = serde_json::Value::String("00".repeat(32));
        assert!(matches!(
            unlock(&value.to_string(), "right"),
            Err(KeystoreError::WrongPassword)
        ));
    }

    #[test]
    fn oversized_scrypt_parameters_are_refused_before_allocating() {
        let json = create(&SECRET, "right").expect("create");
        let mut value: serde_json::Value = serde_json::from_str(&json).expect("json");
        value["crypto"]["kdfparams"]["n"] = serde_json::Value::from(1u64 << 40);
        assert!(matches!(
            unlock(&value.to_string(), "right"),
            Err(KeystoreError::Unsupported(_))
        ));
    }

    #[test]
    fn the_address_is_the_ethereum_address_of_the_key() {
        let expected = "2c7536e3605d9c16a7a3d7b1898e529396a65c23";
        let secret = from_hex("4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318")
            .expect("hex");
        let secret: [u8; 32] = secret.as_slice().try_into().expect("32 bytes");
        assert_eq!(eth_address_hex(&secret).expect("address"), expected);
    }
}
