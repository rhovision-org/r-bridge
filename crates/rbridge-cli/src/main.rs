//! r-bridge reference CLI.
//!
//! This is a thin shell over the shared SDK: it reads a node, prints the canonical asset
//! registry and computes the exact attestation digest relayers sign. It deliberately
//! does not manage native-chain keys; those belong to MetaMask, TronLink and Keplr.

#![forbid(unsafe_code)]

use clap::{Parser, Subcommand};
use rbridge_core::{initial_registry, Amount, AssetRef, AttestationMessage, Chain, Direction};
use rbridge_sdk::{BridgeClient, BridgeConfig};

#[derive(Parser)]
#[command(
    name = "rbridge",
    version,
    about = "r-bridge CLI: node reads, asset registry and attestation digests"
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
    }
    Ok(())
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
