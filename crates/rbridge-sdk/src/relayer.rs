use async_trait::async_trait;
use rbridge_core::AttestationMessage;
use serde::{Deserialize, Serialize};

#[cfg(feature = "native")]
use crate::SdkError;

/// A deposit message plus the relayers' DER signatures over its digest.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct DepositAttestation {
    pub message: AttestationMessage,
    /// Lowercase hex of DER low-S secp256k1 signatures, one per signer.
    pub signatures: Vec<String>,
}

/// The health/registration view the node add-on exposes to the dApp. This is the
/// app-facing contract proposed in rhovision-org/rholo#563; the mock relayer implements
/// the same shape.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RelayerHealth {
    pub version: String,
    pub chains: Vec<String>,
    pub threshold: u16,
    #[serde(default)]
    pub signers: usize,
    #[serde(default)]
    pub paused: bool,
    /// Set by the dev watcher when it refuses to settle (reorg reconciliation).
    #[serde(default)]
    pub halted: Option<serde_json::Value>,
    #[serde(default)]
    pub last_block: Option<i64>,
}

/// One chain as reported by `/v1/chains`. The mock relayer returns bare names; the dev
/// watcher returns the full object.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChainStatus {
    pub chain: String,
    #[serde(default)]
    pub head: Option<i64>,
    #[serde(default)]
    pub confirmations: Option<u64>,
    #[serde(default)]
    pub finalized: Option<bool>,
    #[serde(default = "default_true")]
    pub enabled: bool,
}

impl Default for ChainStatus {
    fn default() -> Self {
        Self {
            chain: String::new(),
            head: None,
            confirmations: None,
            finalized: None,
            enabled: true,
        }
    }
}

fn default_true() -> bool {
    true
}

/// The `/v1/deposits/{id}` view.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct DepositStatus {
    #[serde(default)]
    pub deposit_id: Option<String>,
    pub state: String,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default)]
    pub signatures: Vec<String>,
    #[serde(default)]
    pub threshold: Option<u16>,
    #[serde(default)]
    pub signers: Option<usize>,
}

/// The `/v1/withdrawals/{id}` view.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct WithdrawalStatus {
    #[serde(default)]
    pub withdrawal_id: Option<String>,
    pub state: String,
    #[serde(default)]
    pub native_tx: Option<String>,
}

/// The raw attestation the read API returns: the canonical message string plus
/// signatures. The structured form is [`DepositAttestation`].
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttestationResponse {
    pub message: String,
    pub signatures: Vec<String>,
}

/// The relayer interface the SDK consumes. r-bridge does not implement production
/// relaying; the node add-on does. The mock in `harness/` implements this for devnets.
#[async_trait(?Send)]
pub trait RelayerApi {
    /// Fetch the attestation for a deposit id, or `None` while it is still awaiting
    /// confirmations.
    async fn deposit_attestation(
        &self,
        deposit_id: &str,
    ) -> Result<Option<DepositAttestation>, String>;

    async fn health(&self) -> Result<RelayerHealth, String>;
}

/// HTTP client for the rail-agnostic relayer read API.
///
/// Works against both the mock relayer and the dev watcher. The client only reads; it
/// never asks a relayer to sign. Native-only because the browser talks to the same API
/// through `fetch` in the dApp.
#[cfg(feature = "native")]
#[derive(Clone, Debug)]
pub struct RelayerClient {
    base_url: String,
    http: reqwest::Client,
}

#[cfg(feature = "native")]
impl RelayerClient {
    pub fn new(base_url: impl Into<String>) -> Result<Self, SdkError> {
        let raw = base_url.into();
        let base_url = raw.trim_end_matches('/').to_string();
        if !(base_url.starts_with("http://") || base_url.starts_with("https://")) {
            return Err(SdkError::Relayer(format!(
                "relayer URL must start with http:// or https://: {raw}"
            )));
        }
        let http = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(10))
            .build()
            .map_err(|error| SdkError::Relayer(error.to_string()))?;
        Ok(Self { base_url, http })
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    async fn get_json(&self, path: &str) -> Result<Option<serde_json::Value>, SdkError> {
        let response = self
            .http
            .get(format!("{}{}", self.base_url, path))
            .send()
            .await
            .map_err(|error| SdkError::Relayer(format!("{path}: {error}")))?;
        let status = response.status();
        if status == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }
        let body = response
            .text()
            .await
            .map_err(|error| SdkError::Relayer(format!("{path}: {error}")))?;
        if !status.is_success() {
            let snippet: String = body.chars().take(200).collect();
            return Err(SdkError::Relayer(format!(
                "{path}: HTTP {status}: {snippet}"
            )));
        }
        serde_json::from_str(&body)
            .map(Some)
            .map_err(|error| SdkError::Relayer(format!("{path}: {error}")))
    }

    pub async fn health(&self) -> Result<RelayerHealth, SdkError> {
        let value = self
            .get_json("/health")
            .await?
            .ok_or_else(|| SdkError::Relayer("/health returned 404".to_string()))?;
        serde_json::from_value(value)
            .map_err(|error| SdkError::Relayer(format!("/health: {error}")))
    }

    pub async fn chains(&self) -> Result<Vec<ChainStatus>, SdkError> {
        let value = self
            .get_json("/v1/chains")
            .await?
            .ok_or_else(|| SdkError::Relayer("/v1/chains returned 404".to_string()))?;
        let items = match &value {
            serde_json::Value::Array(items) => items.clone(),
            serde_json::Value::Object(map) => map
                .get("chains")
                .and_then(serde_json::Value::as_array)
                .cloned()
                .ok_or_else(|| {
                    SdkError::Relayer("/v1/chains: object has no chains array".to_string())
                })?,
            _ => {
                return Err(SdkError::Relayer(
                    "/v1/chains: expected an array".to_string(),
                ))
            }
        };
        items
            .into_iter()
            .map(|item| match item {
                serde_json::Value::String(chain) => Ok(ChainStatus {
                    chain,
                    ..ChainStatus::default()
                }),
                other => serde_json::from_value(other)
                    .map_err(|error| SdkError::Relayer(format!("/v1/chains: {error}"))),
            })
            .collect()
    }

    pub async fn deposit(&self, deposit_id: &str) -> Result<Option<DepositStatus>, SdkError> {
        let Some(value) = self
            .get_json(&format!("/v1/deposits/{}", check_id(deposit_id)?))
            .await?
        else {
            return Ok(None);
        };
        serde_json::from_value(value)
            .map(Some)
            .map_err(|error| SdkError::Relayer(format!("/v1/deposits: {error}")))
    }

    pub async fn attestation(
        &self,
        deposit_id: &str,
    ) -> Result<Option<AttestationResponse>, SdkError> {
        let Some(value) = self
            .get_json(&format!(
                "/v1/deposits/{}/attestation",
                check_id(deposit_id)?
            ))
            .await?
        else {
            return Ok(None);
        };
        serde_json::from_value(value)
            .map(Some)
            .map_err(|error| SdkError::Relayer(format!("/v1/attestation: {error}")))
    }

    pub async fn withdrawal(
        &self,
        withdrawal_id: &str,
    ) -> Result<Option<WithdrawalStatus>, SdkError> {
        let Some(value) = self
            .get_json(&format!("/v1/withdrawals/{}", check_id(withdrawal_id)?))
            .await?
        else {
            return Ok(None);
        };
        serde_json::from_value(value)
            .map(Some)
            .map_err(|error| SdkError::Relayer(format!("/v1/withdrawals: {error}")))
    }
}

/// Ids are hex tx hashes or `tx:logIndex` strings; refuse anything that changes the path.
#[cfg(feature = "native")]
fn check_id(id: &str) -> Result<&str, SdkError> {
    let valid = !id.is_empty()
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, ':' | '-' | '_' | '.'));
    if valid {
        Ok(id)
    } else {
        Err(SdkError::Relayer(format!("invalid relayer id: {id}")))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rbridge_core::{AssetRef, Chain, Direction};

    #[test]
    fn attestations_round_trip() {
        let attestation = DepositAttestation {
            message: AttestationMessage {
                network: "devnet".to_string(),
                chain: Chain::Ethereum,
                bridge_id: "rho:id:bridge".to_string(),
                asset: AssetRef::new(Chain::Ethereum, "usdc").expect("asset"),
                direction: Direction::Deposit,
                external_tx_id: "0xabc:0".to_string(),
                amount: 1_000_000,
                recipient: "rho:id:user".to_string(),
                nonce: 1,
            },
            signatures: vec!["30aa".to_string()],
        };
        let json = serde_json::to_string(&attestation).expect("json");
        let back: DepositAttestation = serde_json::from_str(&json).expect("json");
        assert_eq!(back, attestation);
    }
}
