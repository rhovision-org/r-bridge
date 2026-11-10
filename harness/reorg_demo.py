#!/usr/bin/env python3
"""Reorg and confirmation-gate test for the dev relayer.

Runs its own Anvil on :8545, deploys the vault + mock token, and drives the relayer in
dry-run mode (scan and journal, no rholo calls). Two scenarios:

  A. a reorg that only touches unprocessed blocks -> the cursor rolls back;
  B. a reorg that removes a deposit the relayer already settled -> it halts.

No rholo node is needed. The relayer state files are separate from
.devnet/relayer_state.json so a developer's demo state is untouched.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVNET = ROOT / ".devnet"
ANVIL = Path.home() / ".foundry" / "bin" / "anvil"
CAST = Path.home() / ".foundry" / "bin" / "cast"
FORGE = Path.home() / ".foundry" / "bin" / "forge"
RPC = "http://127.0.0.1:8545"
KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ZERO = "0x0000000000000000000000000000000000000000"
ENV = {
    "ADMIN1": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "ADMIN2": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
    "ADMIN3": "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
    "RELAYER1": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
    "RELAYER2": "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
    "RELAYER3": "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
    "TREASURY": "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955",
}


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed:\n{result.stderr}{result.stdout}")
    return result


def cast(*args: str) -> str:
    return run([str(CAST), *args, "--rpc-url", RPC]).stdout.strip()


def rpc(method: str, params: list | None = None):
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    ).encode()
    request = urllib.request.Request(
        RPC, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.load(response)
    if "error" in body:
        raise RuntimeError(body["error"])
    return body.get("result")


def mine(count: int) -> None:
    cast("rpc", "anvil_mine", str(count))


def rollback(depth: int) -> None:
    """Roll the chain back by `depth` blocks (Anvil's reorg simulation)."""
    cast("rpc", "anvil_rollback", str(depth))


def deploy() -> str:
    env = {**os.environ, "PRIVATE_KEY": KEY, **ENV}
    run(
        [
            str(FORGE),
            "script",
            "script/DeployAnvil.s.sol:DeployAnvil",
            "--rpc-url",
            RPC,
            "--broadcast",
        ],
        cwd=ROOT / "contracts" / "evm",
        env=env,
    )
    broadcast = json.loads(
        (ROOT / "contracts/evm/broadcast/DeployAnvil.s.sol/31337/run-latest.json").read_text()
    )
    for tx in broadcast.get("transactions", []):
        if tx.get("contractName") == "BridgeVault" and tx.get("contractAddress"):
            return tx["contractAddress"]
    raise RuntimeError("deployment produced no BridgeVault address")


def relayer(state: Path, *extra: str) -> dict:
    result = run(
        [
            sys.executable,
            str(ROOT / "harness" / "dev_relayer.py"),
            "--dry-run",
            "--once",
            "--vault",
            vault,
            "--state-file",
            str(state),
            "--confirmations",
            "1",
            *extra,
        ]
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    return json.loads(state.read_text())


def check(label: str, condition: bool, detail: str) -> bool:
    print(f"{'PASS' if condition else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    return condition


def main() -> int:
    global vault
    try:
        rpc("eth_chainId")
        print(f"port 8545 is already in use; stop the other Anvil first")
        return 2
    except Exception:  # noqa: BLE001 - expected: nothing listening
        pass

    DEVNET.mkdir(exist_ok=True)
    anvil = subprocess.Popen(
        [str(ANVIL), "--port", "8545", "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    failures = 0
    try:
        for _ in range(100):
            try:
                rpc("eth_chainId")
                break
            except Exception:  # noqa: BLE001 - starting
                time.sleep(0.1)
        else:
            raise RuntimeError("Anvil did not start")

        vault = deploy()
        print(f"vault: {vault}")

        # A: a reorg that does not touch a settled deposit rolls the cursor back.
        state_a = DEVNET / "reorg_state_a.json"
        state_a.unlink(missing_ok=True)
        relayer(state_a)
        mine(4)
        state = relayer(state_a)
        tip = state["last_block"]
        rollback(2)
        state = relayer(state_a)
        failures += not check(
            "shallow reorg is recorded", bool(state["reorgs"]), f"{len(state['reorgs'])}"
        )
        failures += not check(
            "shallow reorg rolls the cursor back",
            state["last_block"] == tip - 1,
            f"{tip} -> {state['last_block']}",
        )
        failures += not check("shallow reorg does not halt", state["halted"] is None, "")

        # B: a reorg that removes a settled deposit halts for reconciliation.
        state_b = DEVNET / "reorg_state_b.json"
        state_b.unlink(missing_ok=True)
        relayer(state_b)
        nonce = str(time.time_ns())
        cast(
            "send",
            vault,
            "lock(address,uint256,string,uint256)",
            ZERO,
            str(10**17),
            "1111reorgtest",
            nonce,
            "--value",
            str(10**17),
            "--private-key",
            KEY,
        )
        mine(2)
        state = relayer(state_b)
        processed = list(state["deposit_blocks"])
        failures += not check("deposit is settled once confirmed", len(processed) == 1, f"{processed}")
        rollback(3)
        state = relayer(state_b)
        halted = state["halted"] or {}
        failures += not check(
            "reorged settled deposit halts the relayer",
            bool(halted) and processed and processed[0] in halted.get("deposits", []),
            str(halted),
        )

        print("reorg demo: " + ("PASS" if failures == 0 else "FAIL"))
        return 0 if failures == 0 else 1
    finally:
        anvil.terminate()
        anvil.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
