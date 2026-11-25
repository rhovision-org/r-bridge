//! r-bridge reference CLI.
//!
//! This is a thin shell over the shared SDK: it reads a node, prints the canonical asset
//! registry, computes the exact attestation digest relayers sign, and provides the
//! signing/deploy/explore primitives the devnet harness uses. It deliberately does not
//! manage native-chain keys; those belong to MetaMask, TronLink and Keplr.

#![forbid(unsafe_code)]

use std::path::PathBuf;
use std::time::{Duration, Instant};

use clap::{Parser, Subcommand};
use rbridge_chain::{DeployOptions, DeployStatus, KeyPair, RholoNode};
use rbridge_core::{
    from_hex, hyperlane, initial_registry, keccak256, to_hex, Amount, AssetRef, AttestationMessage,
    Chain, Direction,
};
use rbridge_sdk::{BridgeClient, BridgeConfig};
use serde_json::json;

#[derive(Parser)]
#[command(
    name = "rbridge",
    version,
    about = "r-bridge CLI: node reads, assets, attestation digests, signing and deploys"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Read the connected rholo node's status.
    Status {
        #[arg(long, env = "RBRIDGE_NODE", default_value = "http://localhost:40403")]
        node: String,
    },
    /// Print the canonical asset registry.
    Assets,
    /// Print the canonical attestation message and its keccak256 digest.
    Digest {
        #[arg(long)]
        network: String,
        #[arg(long)]
        chain: Chain,
        #[arg(long)]
        bridge: String,
        #[arg(long)]
        asset_chain: Chain,
        #[arg(long)]
        asset_id: String,
        #[arg(long)]
        direction: Direction,
        #[arg(long)]
        tx: String,
        /// Amount in rholo base units.
        #[arg(long)]
        amount: i64,
        #[arg(long)]
        recipient: String,
        #[arg(long, default_value_t = 0)]
        nonce: u64,
    },
    /// Generate a devnet key and print its secret, public key and REV address.
    Keygen,
    /// Print the public key and REV address for an existing secret.
    KeyInfo {
        #[arg(long, env = "RBRIDGE_KEY")]
        key: String,
    },
    /// keccak256 a UTF-8 text and sign the digest. Prints JSON.
    SignText {
        #[arg(long, env = "RBRIDGE_KEY")]
        key: String,
        #[arg(long)]
        text: String,
    },
    /// Sign a 32-byte digest (hex). Prints JSON.
    SignDigest {
        #[arg(long, env = "RBRIDGE_KEY")]
        key: String,
        #[arg(long)]
        digest: String,
    },
    /// keccak256 a UTF-8 text and sign it in 65-byte r||s||v form for the EVM/TVM vault.
    SignTextEth {
        #[arg(long, env = "RBRIDGE_KEY")]
        key: String,
        #[arg(long)]
        text: String,
    },
    /// Sign a 32-byte digest (hex) in 65-byte r||s||v form for the EVM/TVM vault.
    SignDigestEth {
        #[arg(long, env = "RBRIDGE_KEY")]
        key: String,
        #[arg(long)]
        digest: String,
    },
    /// Sign and submit a deploy from a term file, then poll to finality.
    Deploy {
        #[arg(long, env = "RBRIDGE_NODE", default_value = "http://localhost:40403")]
        node: String,
        #[arg(long, env = "RBRIDGE_KEY")]
        key: String,
        #[arg(long)]
        term_file: PathBuf,
        #[arg(long, default_value = "/root")]
        shard: String,
        #[arg(long, default_value_t = 8_000_000)]
        phlo_limit: i64,
        #[arg(long, default_value_t = 1)]
        phlo_price: i64,
        #[arg(long)]
        no_wait: bool,
        #[arg(long, default_value_t = 120)]
        timeout_secs: u64,
    },
    /// Explore-deploy a term file (read-only) and print the result.
    Explore {
        #[arg(long, env = "RBRIDGE_NODE", default_value = "http://localhost:40403")]
        node: String,
        #[arg(long)]
        term_file: PathBuf,
    },
    /// Read the rail-agnostic relayer HTTP interface.
    Relayer {
        #[command(subcommand)]
        command: RelayerCommand,
    },
    /// Hyperlane v3 message, checkpoint and r-bridge payload encoders.
    Hyperlane {
        #[command(subcommand)]
        command: HyperlaneCommand,
    },
}

#[derive(Subcommand)]
enum HyperlaneCommand {
    /// Encode a v3 message and print its id.
    Message {
        #[arg(long)]
        nonce: u32,
        #[arg(long)]
        origin: u32,
        #[arg(long)]
        sender: String,
        #[arg(long)]
        destination: u32,
        #[arg(long)]
        recipient: String,
        /// UTF-8 body.
        #[arg(long)]
        body: String,
    },
    /// Print the checkpoint digest validators sign.
    Checkpoint {
        #[arg(long)]
        origin: u32,
        #[arg(long)]
        merkle_tree: String,
        #[arg(long)]
        root: String,
        #[arg(long)]
        index: u32,
        #[arg(long)]
        message_id: String,
    },
    /// Encode the r-bridge payload carried in a Hyperlane body.
    Payload {
        #[arg(long)]
        action: Direction,
        #[arg(long)]
        asset: String,
        /// Amount in rholo base units.
        #[arg(long)]
        amount: i64,
        #[arg(long)]
        recipient: String,
        #[arg(long)]
        external_id: String,
        #[arg(long, default_value_t = 0)]
        nonce: u64,
    },
    /// Decode a dispatched message.
    ParseMessage {
        #[arg(long)]
        message: String,
    },
    /// Decode multisig ISM metadata.
    ParseMetadata {
        #[arg(long)]
        metadata: String,
    },
    /// Derive the Mailbox processor id (keccak256 of a 65-byte public key).
    Processor {
        #[arg(long)]
        pubkey: String,
    },
}

#[derive(Subcommand)]
enum RelayerCommand {
    /// Print the relayer health document.
    Health {
        #[arg(long, env = "RBRIDGE_RELAYER", default_value = "http://127.0.0.1:8099")]
        url: String,
    },
    /// Print per-chain status.
    Chains {
        #[arg(long, env = "RBRIDGE_RELAYER", default_value = "http://127.0.0.1:8099")]
        url: String,
    },
    /// Print a deposit's state (null if the relayer does not know it).
    Deposit {
        #[arg(long, env = "RBRIDGE_RELAYER", default_value = "http://127.0.0.1:8099")]
        url: String,
        #[arg(long)]
        id: String,
    },
    /// Print a withdrawal's state (null if the relayer does not know it).
    Withdrawal {
        #[arg(long, env = "RBRIDGE_RELAYER", default_value = "http://127.0.0.1:8099")]
        url: String,
        #[arg(long)]
        id: String,
    },
    /// Print a deposit's attestation, or null while it is not ready.
    Attestation {
        #[arg(long, env = "RBRIDGE_RELAYER", default_value = "http://127.0.0.1:8099")]
        url: String,
        #[arg(long)]
        id: String,
    },
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    match Cli::parse().command {
        Command::Status { node } => {
            let client = BridgeClient::reader(BridgeConfig::new("cli", node))?;
            let status = client.node_status().await?;
            println!("{}", serde_json::to_string_pretty(&status)?);
        }
        Command::Assets => print_assets(),
        Command::Digest {
            network,
            chain,
            bridge,
            asset_chain,
            asset_id,
            direction,
            tx,
            amount,
            recipient,
            nonce,
        } => {
            let message = AttestationMessage {
                network,
                chain,
                bridge_id: bridge,
                asset: AssetRef::new(asset_chain, asset_id)?,
                direction,
                external_tx_id: tx,
                amount,
                recipient,
                nonce,
            };
            println!("canonical: {}", message.canonical());
            println!("digest:    {}", message.digest_hex()?);
        }
        Command::Keygen => {
            let key = KeyPair::generate()?;
            eprintln!("warning: keygen prints the secret; devnet use only");
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "secret": key.secret_hex(),
                    "public": key.public_hex(),
                    "rev_address": key.rev_address()?,
                    "eth_address": rbridge_chain::eth_address(&key)?,
                }))?
            );
        }
        Command::KeyInfo { key } => {
            let key = KeyPair::from_secret_hex(&key)?;
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "public": key.public_hex(),
                    "rev_address": key.rev_address()?,
                    "eth_address": rbridge_chain::eth_address(&key)?,
                }))?
            );
        }
        Command::SignText { key, text } => {
            let key = KeyPair::from_secret_hex(&key)?;
            let digest = keccak256(text.as_bytes());
            let signature = key.sign_prehash(&digest)?;
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "digest": to_hex(&digest),
                    "signature": to_hex(&signature),
                    "public": key.public_hex(),
                }))?
            );
        }
        Command::SignDigest { key, digest } => {
            let key = KeyPair::from_secret_hex(&key)?;
            let digest = from_hex(&digest)?;
            if digest.len() != 32 {
                return Err("digest must be 32 bytes".into());
            }
            let signature = key.sign_prehash(&digest)?;
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "signature": to_hex(&signature),
                    "public": key.public_hex(),
                }))?
            );
        }
        Command::SignTextEth { key, text } => {
            let key = KeyPair::from_secret_hex(&key)?;
            let digest = keccak256(text.as_bytes());
            let signature = rbridge_chain::sign_eth_prehash(&key, &digest)?;
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "digest": to_hex(&digest),
                    "signature": to_hex(&signature),
                    "address": rbridge_chain::eth_address(&key)?,
                }))?
            );
        }
        Command::SignDigestEth { key, digest } => {
            let key = KeyPair::from_secret_hex(&key)?;
            let digest = from_hex(&digest)?;
            if digest.len() != 32 {
                return Err("digest must be 32 bytes".into());
            }
            let signature = rbridge_chain::sign_eth_prehash(&key, &digest)?;
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "signature": to_hex(&signature),
                    "address": rbridge_chain::eth_address(&key)?,
                }))?
            );
        }
        Command::Deploy {
            node,
            key,
            term_file,
            shard,
            phlo_limit,
            phlo_price,
            no_wait,
            timeout_secs,
        } => {
            deploy(
                &node,
                &key,
                &term_file,
                &shard,
                phlo_limit,
                phlo_price,
                no_wait,
                timeout_secs,
            )
            .await?;
        }
        Command::Explore { node, term_file } => {
            let term = std::fs::read_to_string(&term_file)?;
            let node = RholoNode::new(node)?;
            let response = node.explore(&term).await?;
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "expr": response.expr,
                    "reply_source": response.reply_source,
                    "block": block_json(&response.block),
                }))?
            );
        }
        Command::Relayer { command } => relayer_command(command).await?,
        Command::Hyperlane { command } => hyperlane_command(command)?,
    }
    Ok(())
}

fn hyperlane_command(command: HyperlaneCommand) -> Result<(), Box<dyn std::error::Error>> {
    match command {
        HyperlaneCommand::Message {
            nonce,
            origin,
            sender,
            destination,
            recipient,
            body,
        } => {
            let message = hyperlane::Message::new(
                nonce,
                origin,
                word32(&sender)?,
                destination,
                word32(&recipient)?,
                body.into_bytes(),
            );
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "message": to_hex(&message.encode()),
                    "id": message.id_hex(),
                }))?
            );
        }
        HyperlaneCommand::Checkpoint {
            origin,
            merkle_tree,
            root,
            index,
            message_id,
        } => {
            let digest = hyperlane::checkpoint_digest(
                origin,
                word32(&merkle_tree)?,
                word32(&root)?,
                index,
                word32(&message_id)?,
            );
            println!(
                "{}",
                serde_json::to_string(&json!({"digest": to_hex(&digest)}))?
            );
        }
        HyperlaneCommand::Payload {
            action,
            asset,
            amount,
            recipient,
            external_id,
            nonce,
        } => {
            let payload = hyperlane::Payload {
                action,
                asset_key: asset,
                amount,
                recipient,
                external_id,
                nonce,
            };
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "canonical": payload.canonical(),
                    "body": to_hex(&payload.encode()?),
                }))?
            );
        }
        HyperlaneCommand::ParseMessage { message } => {
            let bytes = from_hex(message.trim_start_matches("0x"))?;
            let message = hyperlane::Message::decode(&bytes)?;
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "version": message.version,
                    "nonce": message.nonce,
                    "origin": message.origin,
                    "sender": to_hex(&message.sender),
                    "destination": message.destination,
                    "recipient": to_hex(&message.recipient),
                    "body": to_hex(&message.body),
                    "id": to_hex(&message.id()),
                }))?
            );
        }
        HyperlaneCommand::ParseMetadata { metadata } => {
            let bytes = from_hex(metadata.trim_start_matches("0x"))?;
            let metadata = hyperlane::IsmMetadata::decode(&bytes)?;
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "origin_merkle_tree": to_hex(&metadata.origin_merkle_tree),
                    "root": to_hex(&metadata.root),
                    "index": metadata.index,
                    "signature_count": metadata.signature_count(),
                }))?
            );
        }
        HyperlaneCommand::Processor { pubkey } => {
            let bytes = from_hex(pubkey.trim_start_matches("0x"))?;
            println!(
                "{}",
                serde_json::to_string(&json!({"processor": to_hex(&keccak256(&bytes))}))?
            );
        }
    }
    Ok(())
}

fn word32(text: &str) -> Result<[u8; 32], Box<dyn std::error::Error>> {
    let bytes = from_hex(text.trim_start_matches("0x"))?;
    if bytes.len() != 32 {
        return Err(format!("expected a 32-byte value, got {} bytes", bytes.len()).into());
    }
    let mut out = [0u8; 32];
    out.copy_from_slice(&bytes);
    Ok(out)
}

async fn relayer_command(command: RelayerCommand) -> Result<(), Box<dyn std::error::Error>> {
    use rbridge_sdk::RelayerClient;

    match command {
        RelayerCommand::Health { url } => {
            let client = RelayerClient::new(url)?;
            println!("{}", serde_json::to_string_pretty(&client.health().await?)?);
        }
        RelayerCommand::Chains { url } => {
            let client = RelayerClient::new(url)?;
            println!("{}", serde_json::to_string_pretty(&client.chains().await?)?);
        }
        RelayerCommand::Deposit { url, id } => {
            let client = RelayerClient::new(url)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&client.deposit(&id).await?)?
            );
        }
        RelayerCommand::Withdrawal { url, id } => {
            let client = RelayerClient::new(url)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&client.withdrawal(&id).await?)?
            );
        }
        RelayerCommand::Attestation { url, id } => {
            let client = RelayerClient::new(url)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&client.attestation(&id).await?)?
            );
        }
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
async fn deploy(
    node_url: &str,
    key_hex: &str,
    term_file: &PathBuf,
    shard: &str,
    phlo_limit: i64,
    phlo_price: i64,
    no_wait: bool,
    timeout_secs: u64,
) -> Result<(), Box<dyn std::error::Error>> {
    let term = std::fs::read_to_string(term_file)?;
    let node = RholoNode::new(node_url)?;
    let height = node.latest_block_number().await?;
    let data = DeployOptions::new(term)
        .phlo(phlo_limit, phlo_price)
        .shard_id(shard)
        .valid_after_block_number(height)
        .build()?;
    let key = KeyPair::from_secret_hex(key_hex)?;
    let signed = key.sign_deploy(data)?;
    let deploy_id = node.deploy(&signed).await?;

    if no_wait {
        println!(
            "{}",
            serde_json::to_string(&json!({
                "deploy_id": deploy_id,
                "status": "submitted",
            }))?
        );
        return Ok(());
    }

    let started = Instant::now();
    loop {
        match node.deploy_status(&deploy_id).await? {
            DeployStatus::ProcessedWithSuccess {
                deploy_result,
                block,
            } => {
                let finalized = node.is_finalized(&block.block_hash).await.unwrap_or(false);
                println!(
                    "{}",
                    serde_json::to_string(&json!({
                        "deploy_id": deploy_id,
                        "status": "processedWithSuccess",
                        "deploy_result": deploy_result,
                        "block": block_json(&block),
                        "finalized": finalized,
                    }))?
                );
                return Ok(());
            }
            DeployStatus::ProcessedWithError {
                deploy_error,
                block,
            } => {
                println!(
                    "{}",
                    serde_json::to_string(&json!({
                        "deploy_id": deploy_id,
                        "status": "processedWithError",
                        "deploy_error": deploy_error,
                        "block": block_json(&block),
                        "finalized": false,
                    }))?
                );
                return Err(format!("deploy {deploy_id} failed: {deploy_error}").into());
            }
            DeployStatus::NotProcessed { status } => {
                if started.elapsed() >= Duration::from_secs(timeout_secs) {
                    println!(
                        "{}",
                        serde_json::to_string(&json!({
                            "deploy_id": deploy_id,
                            "status": "timeout",
                            "last_status": status,
                        }))?
                    );
                    return Err(format!(
                        "deploy {deploy_id} not processed within {timeout_secs}s (last: {status})"
                    )
                    .into());
                }
                tokio::time::sleep(Duration::from_secs(1)).await;
            }
        }
    }
}

fn block_json(block: &rbridge_chain::BlockInfo) -> serde_json::Value {
    json!({
        "block_hash": block.block_hash,
        "block_number": block.block_number,
        "shard_id": block.shard_id,
        "timestamp": block.timestamp,
    })
}

fn print_assets() {
    println!(
        "{:<10} {:<8} {:<14} {:>6} {:>6} {:>14} {:>16} {:>8} {:>8}",
        "CHAIN", "ASSET", "WRAPPED", "NATIVE", "RHOLO", "MIN", "MAX", "FEES", "ENABLED"
    );
    let registry = match initial_registry() {
        Ok(registry) => registry,
        Err(error) => {
            eprintln!("registry error: {error}");
            return;
        }
    };
    for spec in registry {
        let min = Amount::raw(spec.min_deposit).to_decimal(spec.rholo_decimals);
        let max = Amount::raw(spec.max_deposit).to_decimal(spec.rholo_decimals);
        println!(
            "{:<10} {:<8} {:<14} {:>6} {:>6} {:>14} {:>16} {:>8} {:>8}",
            spec.asset.chain.as_str(),
            spec.asset.id.as_str(),
            spec.wrapped_symbol,
            spec.native_decimals,
            spec.rholo_decimals,
            min,
            max,
            format!("{}/{}", spec.fee_bps_deposit, spec.fee_bps_withdraw),
            spec.enabled
        );
    }
}
