/**
 * Display mirror of the canonical registry in `crates/rbridge-core/src/asset.rs`.
 * The Rust registry is authoritative; a mismatch is a bug. Amounts are shown with the
 * native chain's precision until the wrapped token exists.
 */
export type Chain = "ethereum" | "tron" | "agoric";

export interface AssetSpec {
  chain: Chain;
  id: string;
  symbol: string;
  wrappedSymbol: string;
  nativeDecimals: number;
  rholoDecimals: number;
  enabled: boolean;
}

export const ASSETS: AssetSpec[] = [
  { chain: "ethereum", id: "eth", symbol: "ETH", wrappedSymbol: "wETH", nativeDecimals: 18, rholoDecimals: 8, enabled: true },
  { chain: "ethereum", id: "usdt", symbol: "USDT", wrappedSymbol: "wUSDT.eth", nativeDecimals: 6, rholoDecimals: 6, enabled: true },
  { chain: "ethereum", id: "usdc", symbol: "USDC", wrappedSymbol: "wUSDC.eth", nativeDecimals: 6, rholoDecimals: 6, enabled: true },
  { chain: "ethereum", id: "dai", symbol: "DAI", wrappedSymbol: "wDAI", nativeDecimals: 18, rholoDecimals: 8, enabled: true },
  { chain: "tron", id: "trx", symbol: "TRX", wrappedSymbol: "wTRX", nativeDecimals: 6, rholoDecimals: 6, enabled: true },
  { chain: "tron", id: "usdt", symbol: "USDT", wrappedSymbol: "wUSDT.trx", nativeDecimals: 6, rholoDecimals: 6, enabled: true },
  { chain: "tron", id: "usdc", symbol: "USDC", wrappedSymbol: "wUSDC.trx", nativeDecimals: 6, rholoDecimals: 6, enabled: true },
  { chain: "agoric", id: "atom", symbol: "ATOM", wrappedSymbol: "wATOM", nativeDecimals: 6, rholoDecimals: 6, enabled: true },
  { chain: "agoric", id: "ist", symbol: "IST", wrappedSymbol: "wIST", nativeDecimals: 6, rholoDecimals: 6, enabled: true },
  { chain: "agoric", id: "usdc", symbol: "USDC", wrappedSymbol: "wUSDC.noble", nativeDecimals: 6, rholoDecimals: 6, enabled: true },
  { chain: "agoric", id: "usdt", symbol: "USDT", wrappedSymbol: "wUSDT.cosmos", nativeDecimals: 6, rholoDecimals: 6, enabled: false },
];

export const CHAIN_LABEL: Record<Chain, string> = {
  ethereum: "Ethereum",
  tron: "Tron",
  agoric: "Cosmos / Agoric",
};

export const CHAIN_WALLET: Record<Chain, string> = {
  ethereum: "MetaMask",
  tron: "TronLink",
  agoric: "Keplr",
};
