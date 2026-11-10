#!/usr/bin/env python3
"""Read-API test for the dev watcher's deposit and withdrawal endpoints.

Starts its own Anvil on :8545, deploys the vault + token, runs the relayer in dry-run
mode on :9112, settles one deposit, and checks:

  GET /v1/deposits/{id}              -> the journaled state and canonical message
  GET /v1/deposits/{id}/attestation  -> 404 in dry-run (no signatures)
  GET /v1/deposits/{unknown}         -> 404
  GET /v1/withdrawals/{unknown}      -> 404
  GET /health                        -> still serving

No rholo node is needed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import reorg_demo as rd  # noqa: E402

BASE = "http://127.0.0.1:9112"
PORT = 9112


def request(path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def wait_for_deposit(state_path: Path, timeout: float = 20.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            state = json.loads(state_path.read_text())
            ids = list(state.get("deposit_blocks", {}))
            if ids:
                return ids[0]
        except Exception:  # noqa: BLE001 - file may not exist yet
            pass
        time.sleep(0.25)
    raise AssertionError("the relayer never journaled the deposit")


def check(label: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    try:
        rd.rpc("eth_chainId")
        print("port 8545 is already in use; stop the other Anvil first")
        return 2
    except Exception:  # noqa: BLE001 - expected: nothing listening
        pass

    rd.DEVNET.mkdir(exist_ok=True)
    anvil = subprocess.Popen(
        [str(rd.ANVIL), "--port", "8545", "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    relayer = None
    log = None
    failures = 0
    try:
        for _ in range(100):
            try:
                rd.rpc("eth_chainId")
                break
            except Exception:  # noqa: BLE001 - starting
                time.sleep(0.1)
        else:
            raise RuntimeError("Anvil did not start")

        vault = rd.deploy()
        print(f"vault: {vault}")

        state_path = rd.DEVNET / "api_state.json"
        state_path.unlink(missing_ok=True)
        log = (rd.DEVNET / "api_relayer.log").open("w")
        relayer = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(ROOT / "harness" / "dev_relayer.py"),
                "--dry-run",
                "--vault",
                vault,
                "--state-file",
                str(state_path),
                "--interval",
                "1",
                "--metrics-port",
                str(PORT),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for _ in range(100):
            try:
                status, _ = request("/health")
                if status == 200:
                    break
            except Exception:  # noqa: BLE001 - server starting
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("the read API never came up")

        nonce = str(time.time_ns())
        rd.cast(
            "send",
            vault,
            "lock(address,uint256,string,uint256)",
            rd.ZERO,
            str(10**17),
            "1111api",
            nonce,
            "--value",
            str(10**17),
            "--private-key",
            rd.KEY,
        )

        deposit_id = wait_for_deposit(state_path)
        status, body = request(f"/v1/deposits/{deposit_id}")
        deposit = json.loads(body) if status == 200 else {}
        failures += check("deposit view returns 200", status == 200, str(status))
        failures += check("deposit state is dry_run", deposit.get("state") == "dry_run")
        failures += check(
            "canonical message is exposed",
            str(deposit.get("message", "")).startswith("rbridge:v1|")
            and deposit_id in str(deposit.get("message")),
        )
        failures += check("dry-run has no signatures", deposit.get("signatures") == [])

        status, _ = request(f"/v1/deposits/{deposit_id}/attestation")
        failures += check("dry-run attestation is 404", status == 404, str(status))
        status, _ = request("/v1/deposits/0xdeadbeef")
        failures += check("unknown deposit is 404", status == 404, str(status))
        status, _ = request("/v1/withdrawals/0xnope")
        failures += check("unknown withdrawal is 404", status == 404, str(status))
        status, _ = request("/health")
        failures += check("health still serves", status == 200, str(status))

        print("api demo: " + ("PASS" if failures == 0 else "FAIL"))
        return 0 if failures == 0 else 1
    finally:
        if relayer is not None:
            relayer.terminate()
            try:
                relayer.wait(timeout=10)
            except subprocess.TimeoutExpired:
                relayer.kill()
        if log is not None:
            log.close()
        anvil.terminate()
        anvil.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
