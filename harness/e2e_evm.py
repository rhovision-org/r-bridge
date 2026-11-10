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
ANVIL_SENDER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"  # Anvil account 0
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


def deploy_vault(keys: dict, bridge: dict) -> tuple[str, str]:
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
    vault = None
    token = None
    for tx in data.get("transactions", []):
        if tx.get("contractName") == "BridgeVault" and tx.get("contractAddress"):
            vault = tx["contractAddress"]
        if tx.get("contractName") == "MockERC20" and tx.get("contractAddress"):
            token = tx["contractAddress"]
    if vault and token:
        EVM_FILE.write_text(
            json.dumps(
                {
                    "vault": vault,
                    "token": token,
                    "bridge_id": bridge["bridge_id"],
                    "asset_keys": {"ethereum.eth": ZERO, "ethereum.usdt": token},
                },
                indent=2,
            )
        )
        return vault, token
    raise RuntimeError("deploy produced no BridgeVault/MockERC20 address")


def main() -> int:
    if not KEYS_FILE.exists() or not BRIDGE_FILE.exists():
        print("missing .devnet keys/bridge; run `make devnet-up && make demo` first")
        return 2
    keys = json.loads(KEYS_FILE.read_text())
    bridge = json.loads(BRIDGE_FILE.read_text())
    deployer = keys["deployer"]
    demo.DEPLOY_SECRET = deployer["secret"]

    if EVM_FILE.exists():
        evm = json.loads(EVM_FILE.read_text())
        vault = evm.get("vault")
        token = evm.get("token")
        if not vault or not token:
            vault, token = deploy_vault(keys, bridge)
    else:
        vault, token = deploy_vault(keys, bridge)
    print(f"vault:  {vault}")
    print(f"token:  {token}")
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


    # 6. ERC-20 (mock USDT) lock -> mint -> burn -> unlock.
    token_amount = 1_000_000  # 1 USDT at 6 decimals
    token_gross = 400_000
    token_fee = 200
    token_nonce = int(time.time_ns())
    usdt_locked_before = int(cast("call", vault, "locked(address)(uint256)", token, "--rpc-url", ANVIL_RPC).split()[0], 0)
    usdt_fees_before = int(cast("call", vault, "fees(address)(uint256)", token, "--rpc-url", ANVIL_RPC).split()[0], 0)
    usdt_bal_before = int(cast("call", token, "balanceOf(address)(uint256)", ANVIL_TO, "--rpc-url", ANVIL_RPC).split()[0], 0)
    cast_json("send", token, "mint(address,uint256)", ANVIL_SENDER, str(token_amount), "--private-key", ANVIL_KEY, "--rpc-url", ANVIL_RPC)
    cast_json("send", token, "approve(address,uint256)", vault, str(token_amount), "--private-key", ANVIL_KEY, "--rpc-url", ANVIL_RPC)
    lock_usdt = cast_json(
        "send", vault, "lock(address,uint256,string,uint256)", token, str(token_amount),
        deployer["rev_address"], str(token_nonce), "--private-key", ANVIL_KEY, "--rpc-url", ANVIL_RPC,
    )
    usdt_tx = lock_usdt["transactionHash"]
    usdt_deposit = (
        f"rbridge:v1|{bridge['network']}|ethereum|{bridge['bridge_id']}|"
        f"ethereum.usdt|deposit|{usdt_tx}|{token_amount}|{deployer['rev_address']}|0"
    )
    usdt_sigs = [
        demo.sign_text(secret, usdt_deposit)["signature"]
        for secret in [deployer["secret"], keys["relayers"][0]["secret"]]
    ]
    usdt_minted = demo.call_write(
        bridge["uri"],
        f'Bridge!("mint", "ethereum", "usdt", "{usdt_tx}", {token_amount}, '
        f'"{deployer["rev_address"]}", 0, [{demo.signature_literals(usdt_sigs)}], *ret)',
        deployer["secret"],
        "evm_usdt_mint.rho",
    )
    usdt_expected = (True, token_amount - token_amount * 5 // 10_000)
    print(f"{'PASS' if usdt_minted == usdt_expected else 'FAIL'}  rholo USDT mint: {usdt_minted!r}")

    usdt_withdrawal_id = f"evm-usdt-withdrawal-{token_nonce}"
    usdt_burn = demo.call_write(
        bridge["uri"],
        f'Bridge!("burn", "ethereum", "usdt", {token_gross}, "ethereum", "{ANVIL_TO}", '
        f'"{usdt_withdrawal_id}", *ret)',
        deployer["secret"],
        "evm_usdt_burn.rho",
    )
    print(f"{'PASS' if usdt_burn == (True, usdt_withdrawal_id) else 'FAIL'}  rholo USDT burn: {usdt_burn!r}")

    usdt_message = (
        f"rbridge:v1|{bridge['network']}|ethereum|{bridge['bridge_id']}|"
        f"ethereum.usdt|withdraw|{usdt_withdrawal_id}|{token_gross}|{ANVIL_TO}|0"
    )
    usdt_eth_sigs = [
        demo.cli("sign-text-eth", "--key", secret, "--text", usdt_message)["signature"]
        for secret in [deployer["secret"], keys["relayers"][0]["secret"]]
    ]
    usdt_unlock = cast_json(
        "send", vault, "unlock(address,address,uint256,string,uint256,bytes[])", token,
        ANVIL_TO, str(token_gross), usdt_withdrawal_id, "0",
        "[" + ",".join("0x" + sig for sig in usdt_eth_sigs) + "]",
        "--private-key", ANVIL_KEY, "--rpc-url", ANVIL_RPC,
    )
    usdt_complete = demo.call_write(
        bridge["uri"],
        f'Bridge!("completeWithdrawal", "{usdt_withdrawal_id}", "{usdt_unlock["transactionHash"]}", *ret)',
        deployer["secret"],
        "evm_usdt_complete.rho",
    )
    usdt_after = int(cast("call", token, "balanceOf(address)(uint256)", ANVIL_TO, "--rpc-url", ANVIL_RPC).split()[0], 0)
    usdt_locked = int(cast("call", vault, "locked(address)(uint256)", token, "--rpc-url", ANVIL_RPC).split()[0], 0)
    usdt_fees = int(cast("call", vault, "fees(address)(uint256)", token, "--rpc-url", ANVIL_RPC).split()[0], 0)
    usdt_net = usdt_after - usdt_bal_before
    usdt_ok = (
        usdt_minted == usdt_expected
        and usdt_burn == (True, usdt_withdrawal_id)
        and usdt_complete == (True,)
        and usdt_net == token_gross - token_fee
        and usdt_locked == usdt_locked_before + token_amount - token_gross
        and usdt_fees == usdt_fees_before + token_fee
    )
    print(f"{'PASS' if usdt_net == token_gross - token_fee else 'FAIL'}  USDT unlock net: {usdt_net} (expected {token_gross - token_fee})")
    print(f"{'PASS' if usdt_locked == usdt_locked_before + token_amount - token_gross else 'FAIL'}  USDT vault locked: {usdt_locked}")
    print(f"{'PASS' if usdt_fees == usdt_fees_before + token_fee else 'FAIL'}  USDT vault fees: {usdt_fees}")
    print(f"       USDT unlock tx: {usdt_unlock['transactionHash']}")

    ok = got == expected_net and locked == expected_locked and fees == expected_fees and completed == (True,) and usdt_ok
    print()
    print("e2e evm<->rholo:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
