#!/usr/bin/env python3
"""Metrics/health test for the dev relayer.

Starts its own Anvil on :8545, deploys the vault + token, runs the relayer in dry-run
mode with `--metrics-port 9110`, settles one deposit, then rolls it back and checks the
halted state. No rholo node is needed.

Endpoints checked: /metrics (Prometheus), /health, /v1/chains. The relayer must keep the
endpoints up while halted.
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
sys.path.insert(0, str(ROOT / "harness"))
import reorg_demo as rd  # noqa: E402

METRICS = "http://127.0.0.1:9110"
PORT = 9110


def get(path: str) -> str:
    with urllib.request.urlopen(f"{METRICS}{path}", timeout=5) as response:
        return response.read().decode()


def wait_for(path: str, needle: str, timeout: float = 20.0) -> str:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            last = get(path)
            if needle in last:
                return last
        except Exception:  # noqa: BLE001 - server starting
            pass
        time.sleep(0.25)
    raise AssertionError(f"{path} never contained {needle!r}; last body:\n{last}")


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

        state = rd.DEVNET / "metrics_state.json"
        state.unlink(missing_ok=True)
        log_path = rd.DEVNET / "metrics_relayer.log"
        log = log_path.open("w")
        relayer = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(ROOT / "harness" / "dev_relayer.py"),
                "--dry-run",
                "--vault",
                vault,
                "--state-file",
                str(state),
                "--interval",
                "1",
                "--metrics-port",
                str(PORT),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "RBRIDGE_RELAYER_DEBUG": "1"},
        )
        wait_for("/health", '"version"')

        nonce = str(time.time_ns())
        rd.cast(
            "send",
            vault,
            "lock(address,uint256,string,uint256)",
            rd.ZERO,
            str(10**17),
            "1111metrics",
            nonce,
            "--value",
            str(10**17),
            "--private-key",
            rd.KEY,
        )

        metrics = wait_for(
            "/metrics", 'rbridge_deposits_total{chain="ethereum",state="settled"} 1'
        )
        health = json.loads(get("/health"))
        chains = json.loads(get("/v1/chains"))

        failures += check("deposit is exposed as settled", health["deposits"]["settled"] == 1)
        failures += check("chain head is journaled", chains[0]["head"] >= 1, str(chains[0]["head"]))
        failures += check("not halted after settling", health["halted"] is None)
        failures += check("halted gauge is 0", "rbridge_halted 0" in metrics)
        failures += check("reorg counter is 0", "rbridge_reorgs_total 0" in metrics)
        failures += check("chain is enabled", chains[0]["enabled"] is True)

        rd.rollback(1)
        # Match the gauge line, not the help line ("rbridge_halted 1 when ...").
        halted_metrics = wait_for("/metrics", "rbridge_halted 1\n")
        health = json.loads(get("/health"))
        chains = json.loads(get("/v1/chains"))
        failures += check(
            "halted after reorging the settled deposit", health["halted"] is not None
        )
        failures += check(
            "reorg counter is 1", "rbridge_reorgs_total 1" in halted_metrics
        )
        failures += check("chain is disabled", chains[0]["enabled"] is False)
        failures += check("relayer keeps serving while halted", relayer.poll() is None)

        if failures:
            print(f"last health: {health}")
            print(f"last metrics:\n{halted_metrics}")
            relayer.terminate()
            relayer.wait(timeout=10)
            log.flush()
            print(f"relayer output:\n{log_path.read_text()}")
        print("metrics demo: " + ("PASS" if failures == 0 else "FAIL"))
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
