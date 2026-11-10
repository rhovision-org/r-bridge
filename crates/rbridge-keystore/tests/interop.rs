//! Interop fixtures produced by `@ethereumjs/wallet` (the library r-wallet uses).
//!
//! The reverse direction — a keystore made here opening in `@ethereumjs/wallet` — is
//! verified once against the wallet package during development; these fixtures keep the
//! import direction covered in CI.

use rbridge_core::to_hex;
use rbridge_keystore::unlock;

const SECRET_HEX: &str = "4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318";

#[test]
fn an_rwallet_scrypt_keystore_unlocks() {
    let json = include_str!("fixtures/rwallet-scrypt.json");
    let secret = unlock(json, "interop-password").expect("unlock");
    assert_eq!(to_hex(&secret), SECRET_HEX);
}

#[test]
fn a_geth_pbkdf2_keystore_unlocks() {
    let json = include_str!("fixtures/geth-pbkdf2.json");
    let secret = unlock(json, "interop-password").expect("unlock");
    assert_eq!(to_hex(&secret), SECRET_HEX);
}

#[test]
fn interop_fixtures_refuse_the_wrong_password() {
    let json = include_str!("fixtures/rwallet-scrypt.json");
    assert!(unlock(json, "not-the-password").is_err());
}
