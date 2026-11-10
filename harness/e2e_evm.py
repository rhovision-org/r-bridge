#!/usr/bin/env python3
"""Cross-chain demo: Ethereum (Anvil) lock -> rholo mint -> rholo burn -> EVM unlock.

Prereqs:
  - Anvil on 127.0.0.1:8545
  - local rholo devnet on :40403 with a bridge installed by `make demo`
  - the demo keys in .devnet/demo-keys.json

This is a devnet harness, not the production relayer. It shows exactly what the chosen
relayer rail must do: watch a deposit, attest the canonical digest, submit a rholo mint,
and broadcast a native unlock on a rholo burn.

Devnet only. Keys are throwaway.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVNET = ROOT / ".devnet"
KEYS_FILE = DEVNET / "demo-keys.json"
BRIDGE_FILE = DEVNET / "bridge.json"
EVM_FILE = DEVNET / "evm.json"
ANVIL_RPC = "http://127.0.0.1:8545"
ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ANVIL_TO = "0x15d34aaf54267db7d7c367839aaf71a00a2c6a65"  # Anvil account 9
ANVIL_TREASURY = "0x90f79bf6eb2c4f870365e785982e1f101e93b906"  # Anvil account 8
ZERO = "0x0000000000000000000000000000000000000000"
CAST = Path.home() / ".foundry" / "bin" / "cast"
FORGE = Path.home() / ".foundry" / "bin" / "forge"

sys.path.insert(0, str(ROOT / "harness"))
import demo  # noqa: E402


def cast(*args: str) -> str:
    result = subprocess.run([str(CAST), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cast {' '.join(args)} failed:\n{result.stderr}{result.stdout}")
    return result.stdout.strip()


def cast_json(*args: str) -> dict:
    return json.loads(cast(*args, "--json"))


def key_eth(secret: str) -> str:
    return "0x" + demo.keyinfo(secret)["eth_address"]


def deploy_vault(keys: dict, bridge: dict) -> str:
    env = {
        "PRIVATE_KEY": ANVIL_KEY,
        "ADMIN1": key_eth(keys["admins"][0]["secret"]),
        "ADMIN2": key_eth(keys["admins"][1]["secret"]),
        "ADMIN3": key_eth(keys["admins"][2]["secret"]),
        "RELAYER1": key_eth(keys["deployer"]["secret"]),
        "RELAYER2": key_eth(keys["relayers"][0]["secret"]),
        "RELAYER3": key_eth(keys["relayers"][1]["secret"]),
        "TREASURY": ANVIL_TREASURY,
    }
    result = subprocess.run(
        [
            str(FORGE),
            "script",
            "script/DeployAnvil.s.sol:DeployAnvil",
            "--rpc-url",
            ANVIL_RPC,
            "--broadcast",
            "-vv",
        ],
        cwd=ROOT / "contracts" / "evm",
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"forge script failed:\n{result.stderr}{result.stdout}")
    broadcast = ROOT / "contracts" / "evm" / "broadcast" / "DeployAnvil.s.sol" / "31337" / "run-latest.json"
    data = json.loads(broadcast.read_text())
    for tx in data.get("transactions", []):
        if tx.get("contractName") == "BridgeVault" and tx.get("contractAddress"):
            vault = tx["contractAddress"]
            EVM_FILE.write_text(
                json.dumps({"vault": vault, "bridge_id": bridge["bridge_id"]}, indent=2)
            )
            return vault
    raise RuntimeError("deploy produced no BridgeVault address")


def main() -> int:
    if not KEYS_FILE.exists() or not BRIDGE_FILE.exists():
        print("missing .devnet keys/bridge; run `make devnet-up && make demo` first")
        return 2
    keys = json.loads(KEYS_FILE.read_text())
    bridge = json.loads(BRIDGE_FILE.read_text())
    deployer = keys["deployer"]
    demo.DEPLOY_SECRET = deployer["secret"]

    if EVM_FILE.exists():
        vault = json.loads(EVM_FILE.read_text())["vault"]
    else:
        vault = deploy_vault(keys, bridge)
    print(f"vault:  {vault}")
    print(f"bridge: {bridge['uri']}")
    locked_before = int(cast("call", vault, "locked(address)(uint256)", ZERO, "--rpc-url", ANVIL_RPC).split()[0], 0)
    fees_before = int(cast("call", vault, "fees(address)(uint256)", ZERO, "--rpc-url", ANVIL_RPC).split()[0], 0)

    # 1. Lock 0.1 ETH on Anvil and bind it to the deployer's rholo address.
    run_id = str(time.time_ns())
    lock_nonce = int(run_id)
    amount_wei = 100_000_000_000_000_000  # 0.1 ETH
    rholo_amount = 10_000_000  # 0.1 ETH at 8 decimals
    lock = cast_json(
        "send",
        vault,
        "lock(address,uint256,string,uint256)",
        ZERO,
        str(amount_wei),
        deployer["rev_address"],
        str(lock_nonce),
        "--value",
        str(amount_wei),
        "--private-key",
        ANVIL_KEY,
        "--rpc-url",
        ANVIL_RPC,
    )
    tx_hash = lock["transactionHash"]
    print(f"lock:   {tx_hash}")

    # 2. Attest the deposit and mint on rholo with 2-of-3 relayer signatures.
    deposit_message = (
        f"rbridge:v1|{bridge['network']}|ethereum|{bridge['bridge_id']}|"
        f"ethereum.eth|deposit|{tx_hash}|{rholo_amount}|{deployer['rev_address']}|0"
    )
    deposit_sigs = [
        demo.sign_text(secret, deposit_message)["signature"]
        for secret in [deployer["secret"], keys["relayers"][0]["secret"]]
    ]
    minted = demo.call_write(
        bridge["uri"],
        f'Bridge!("mint", "ethereum", "eth", "{tx_hash}", {rholo_amount}, '
        f'"{deployer["rev_address"]}", 0, [{demo.signature_literals(deposit_sigs)}], *ret)',
        deployer["secret"],
        "evm_mint.rho",
    )
    fee = rholo_amount * 5 // 10_000
    expected = (True, rholo_amount - fee)
    print(f"{'PASS' if minted == expected else 'FAIL'}  rholo mint: {minted!r}")
    if minted != expected:
        return 1

    # 3. Burn half on rholo, bound to an Anvil address.
    gross = 5_000_000  # 0.05 ETH at 8 decimals
    withdrawal_id = f"evm-withdrawal-{run_id}"
    burn = demo.call_write(
        bridge["uri"],
        f'Bridge!("burn", "ethereum", "eth", {gross}, "ethereum", "{ANVIL_TO}", '
        f'"{withdrawal_id}", *ret)',
        deployer["secret"],
        "evm_burn.rho",
    )
    print(f"{'PASS' if burn == (True, withdrawal_id) else 'FAIL'}  rholo burn: {burn!r}")
    if burn != (True, withdrawal_id):
        return 1

    # 4. Sign the withdrawal digest with 2-of-3 in the 65-byte EVM form and unlock.
    withdrawal_message = (
        f"rbridge:v1|{bridge['network']}|ethereum|{bridge['bridge_id']}|"
        f"ethereum.eth|withdraw|{withdrawal_id}|{gross}|{ANVIL_TO}|0"
    )
    eth_sigs = [
        demo.cli("sign-text-eth", "--key", secret, "--text", withdrawal_message)["signature"]
        for secret in [deployer["secret"], keys["relayers"][0]["secret"]]
    ]
    before = int(cast("balance", ANVIL_TO, "--rpc-url", ANVIL_RPC))
    signatures = "[" + ",".join("0x" + sig for sig in eth_sigs) + "]"
    unlock_tx = cast_json(
        "send",
        vault,
        "unlock(address,address,uint256,string,uint256,bytes[])",
        ZERO,
        ANVIL_TO,
        str(gross),
        withdrawal_id,
        "0",
        signatures,
        "--private-key",
        ANVIL_KEY,
        "--rpc-url",
        ANVIL_RPC,
    )
    after = int(cast("balance", ANVIL_TO, "--rpc-url", ANVIL_RPC))
    completed = demo.call_write(
        bridge["uri"],
        f'Bridge!("completeWithdrawal", "{withdrawal_id}", "{unlock_tx["transactionHash"]}", *ret)',
        deployer["secret"],
        "evm_complete.rho",
    )
    print(f"{'PASS' if completed == (True,) else 'FAIL'}  rholo withdrawal complete: {completed!r}")

    native_gross = gross * 10_000_000_000  # 1e10 wei per rholo unit
    native_fee = native_gross * 5 // 10_000
    expected_net = native_gross - native_fee
    got = after - before
    print(f"{'PASS' if got == expected_net else 'FAIL'}  EVM unlock net: {got} (expected {expected_net})")
    print(f"       unlock tx: {unlock_tx['transactionHash']}")
    locked = int(cast("call", vault, "locked(address)(uint256)", ZERO, "--rpc-url", ANVIL_RPC).split()[0], 0)
    fees = int(cast("call", vault, "fees(address)(uint256)", ZERO, "--rpc-url", ANVIL_RPC).split()[0], 0)
    expected_locked = locked_before + amount_wei - native_gross
    expected_fees = fees_before + native_fee
    print(f"{'PASS' if locked == expected_locked else 'FAIL'}  vault locked: {locked} (expected {expected_locked})")
    print(f"{'PASS' if fees == expected_fees else 'FAIL'}  vault fees: {fees} (expected {expected_fees})")

    ok = got == expected_net and locked == expected_locked and fees == expected_fees and completed == (True,)
    print()
    print("e2e evm<->rholo:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
