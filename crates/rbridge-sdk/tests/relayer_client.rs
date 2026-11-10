//! The relayer read client against a canned HTTP server (no relayer process needed).

#![allow(clippy::expect_used, clippy::panic, clippy::unwrap_used)]

use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread::{self, JoinHandle};

use rbridge_sdk::RelayerClient;

fn http(body: &str, status: u16) -> String {
    let reason = if status == 404 { "Not Found" } else { "OK" };
    format!(
        "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )
}

/// Serve one canned response per request, then close the listener.
fn serve(responses: Vec<(&'static str, u16)>) -> (String, JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
    let address = listener.local_addr().expect("local address");
    let handle = thread::spawn(move || {
        for (body, status) in responses {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut buffer = [0u8; 4096];
            let _ = stream.read(&mut buffer);
            stream
                .write_all(http(body, status).as_bytes())
                .expect("write");
        }
    });
    (format!("http://{address}"), handle)
}

#[tokio::test]
async fn health_is_parsed_with_optional_fields() {
    let (url, server) = serve(vec![(
        r#"{"version":"dev","chains":["ethereum"],"threshold":2,"paused":false}"#,
        200,
    )]);
    let client = RelayerClient::new(url).expect("client");
    let health = client.health().await.expect("health");
    assert_eq!(health.version, "dev");
    assert_eq!(health.chains, vec!["ethereum"]);
    assert_eq!(health.threshold, 2);
    assert_eq!(health.signers, 0);
    assert!(health.halted.is_none());
    server.join().expect("server");
}

#[tokio::test]
async fn chains_accept_objects_and_bare_names() {
    let (url, server) = serve(vec![
        (
            r#"[{"chain":"ethereum","head":12,"confirmations":3,"enabled":true}]"#,
            200,
        ),
        (r#"{"chains":["ethereum","tron"]}"#, 200),
    ]);
    let client = RelayerClient::new(url).expect("client");
    let chains = client.chains().await.expect("chains");
    assert_eq!(chains[0].chain, "ethereum");
    assert_eq!(chains[0].head, Some(12));
    assert_eq!(chains[0].confirmations, Some(3));
    assert!(chains[0].enabled);

    let chains = client.chains().await.expect("chains");
    assert_eq!(chains.len(), 2);
    assert_eq!(chains[1].chain, "tron");
    assert!(chains[1].enabled);
    server.join().expect("server");
}

#[tokio::test]
async fn a_missing_deposit_or_attestation_is_none() {
    let (url, server) = serve(vec![
        (r#"{"error":"unknown deposit"}"#, 404),
        (r#"{"error":"unknown deposit"}"#, 404),
    ]);
    let client = RelayerClient::new(url).expect("client");
    assert!(client.deposit("0xabc:0").await.expect("deposit").is_none());
    assert!(client
        .attestation("0xabc:0")
        .await
        .expect("attestation")
        .is_none());
    server.join().expect("server");
}

#[tokio::test]
async fn a_deposit_and_its_attestation_are_parsed() {
    let message = "rbridge:v1|devnet|ethereum|bridge|ethereum.usdt|deposit|0xabc:0|100|1111user|0";
    let deposit_body = r#"{"deposit_id":"0xabc:0","state":"attested","message":"rbridge:v1|devnet|ethereum|bridge|ethereum.usdt|deposit|0xabc:0|100|1111user|0","signatures":["30aa"],"threshold":2}"#;
    let attestation_body = r#"{"message":"rbridge:v1|devnet|ethereum|bridge|ethereum.usdt|deposit|0xabc:0|100|1111user|0","signatures":["30aa","30bb"]}"#;
    let (url, server) = serve(vec![(deposit_body, 200), (attestation_body, 200)]);
    let client = RelayerClient::new(url).expect("client");

    let deposit = client
        .deposit("0xabc:0")
        .await
        .expect("deposit")
        .expect("some");
    assert_eq!(deposit.state, "attested");
    assert_eq!(deposit.message.as_deref(), Some(message));
    assert_eq!(deposit.signatures, vec!["30aa"]);
    assert_eq!(deposit.threshold, Some(2));

    let attestation = client
        .attestation("0xabc:0")
        .await
        .expect("attestation")
        .expect("some");
    assert_eq!(attestation.message, message);
    assert_eq!(attestation.signatures, vec!["30aa", "30bb"]);
    server.join().expect("server");
}

#[tokio::test]
async fn withdrawals_are_parsed() {
    let (url, server) = serve(vec![(
        r#"{"withdrawal_id":"w1","state":"unlocked","native_tx":"0xdef"}"#,
        200,
    )]);
    let client = RelayerClient::new(url).expect("client");
    let withdrawal = client
        .withdrawal("w1")
        .await
        .expect("withdrawal")
        .expect("some");
    assert_eq!(withdrawal.state, "unlocked");
    assert_eq!(withdrawal.native_tx.as_deref(), Some("0xdef"));
    server.join().expect("server");
}

#[tokio::test]
async fn a_server_error_is_reported() {
    let (url, server) = serve(vec![("boom", 500)]);
    let client = RelayerClient::new(url).expect("client");
    let error = client.health().await.expect_err("error");
    assert!(error.to_string().contains("HTTP 500"), "{error}");
    server.join().expect("server");
}

#[test]
fn a_bad_url_is_refused() {
    assert!(RelayerClient::new("127.0.0.1:8099").is_err());
    assert!(RelayerClient::new("ftp://example").is_err());
}

#[tokio::test]
async fn an_id_that_changes_the_path_is_refused() {
    let client = RelayerClient::new("http://127.0.0.1:9").expect("client");
    let error = client.deposit("../health").await.expect_err("error");
    assert!(error.to_string().contains("invalid relayer id"), "{error}");
}
