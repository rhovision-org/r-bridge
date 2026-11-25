#!/usr/bin/env python3
"""Rehearse the HyperlanePeer deployment path on a private Anvil.

Starts its own Anvil on :8548, deploys a local Mailbox and USDT/USDC mocks, then drives
`tools/deploy_hyperlane_peer.py` as a Sepolia operator would: a profile deploy, on-chain
read-back, a manifest, a re-verify, and the safety gates (mainnet refusal, chain mismatch,
wrong decimals, missing key, tamper detection).

No rholo node or testnet credentials are needed. Keys are the public Anvil defaults.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANVIL = Path.home() / ".foundry" / "bin" / "anvil"
FORGE = Path.home() / ".foundry" / "bin" / "forge"
TOOL = ROOT / "tools" / "deploy_hyperlane_peer.py"
EVM = ROOT / "contracts" / "evm"
PORT = 8548
RPC = f"http://127.0.0.1:{PORT}"
DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
OWNER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
RELAYER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
PASS = 0
FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}{': ' + detail if detail else ''}")


def rpc(method: str, params: list | None = None):
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    ).encode()
    request = urllib.request.Request(
        RPC, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        body = json.load(response)
    if "error" in body:
        raise RuntimeError(body["error"])
    return body.get("result")


def wait_for_anvil(deadline: float = 20.0) -> None:
    end = time.time() + deadline
    while time.time() < end:
        try:
            if int(rpc("eth_chainId"), 16) == 31337:
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Anvil did not start on :8548")


def tool(args: list[str], **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )


def deploy_mocks() -> tuple[str, str, str]:
    result = subprocess.run(
        [
            str(FORGE),
            "script",
            "script/DeployHyperlaneMocks.s.sol:DeployHyperlaneMocks",
            "--rpc-url",
            RPC,
            "--broadcast",
        ],
        cwd=EVM,
        capture_output=True,
        text=True,
        env={**os.environ, "PRIVATE_KEY": DEPLOYER_KEY, "LOCAL_DOMAIN": "31337"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"mock deploy failed:\n{result.stderr}{result.stdout}")
    artifact = EVM / "broadcast" / "DeployHyperlaneMocks.s.sol" / "31337" / "run-latest.json"
    data = json.loads(artifact.read_text())
    found: dict[str, str] = {}
    tokens: list[str] = []
    for tx in data.get("transactions", []):
        name = tx.get("contractName")
        address = tx.get("contractAddress")
        if name == "MockHyperlaneMailbox" and address:
            found["mailbox"] = address
        elif name == "MockERC20" and address:
            tokens.append(address)
    if "mailbox" not in found or len(tokens) < 2:
        raise RuntimeError("mock broadcast artifact is incomplete")
    return found["mailbox"], tokens[0], tokens[1]


def profile(tmp: Path, name: str, **overrides) -> Path:
    path = tmp / f"{name}.json"
    data = {
        "schema": "rbridge.hyperlane-peer.v1",
        "network": f"rbridge-hyperlane-{name}",
        "chainName": "ethereum",
        "chainId": 31337,
        "rpc": RPC,
        "mailbox": overrides.pop("mailbox"),
        "localDomain": 31337,
        "remoteDomain": 9999,
        "remotePeer": "0x" + "00" * 31 + "dd",
        "relayer": RELAYER,
        "owner": OWNER,
        "deployerKeyEnv": "ANVIL_KEY",
        "mainnet": False,
        "assets": overrides.pop("assets"),
    }
    data.update(overrides)
    path.write_text(json.dumps(data, indent=2))
    return path


def run_checks(tmp: Path, mailbox: str, usdt: str, usdc: str) -> int:
    assets = [
        {
            "assetKey": "ethereum.usdc",
            "token": usdc,
            "decimals": 6,
            "scale": 1,
            "maxDeposit": "10000000000",
            "maxLocked": "1000000000000",
        },
        {
            "assetKey": "ethereum.usdt",
            "token": usdt,
            "decimals": 6,
            "scale": 1,
            "maxDeposit": "10000000000",
            "maxLocked": "1000000000000",
        },
    ]
    good = profile(tmp, "good", mailbox=mailbox, assets=assets)
    manifest = tmp / "manifest.json"
    deployed = tool(
        ["deploy", "--profile", str(good), "--out", str(manifest)],
        ANVIL_KEY=DEPLOYER_KEY,
    )
    check("profile deploy succeeds", deployed.returncode == 0, deployed.stderr)
    check("manifest is written", manifest.exists())
    if manifest.exists():
        data = json.loads(manifest.read_text())
        check("manifest schema", data.get("schema") == "rbridge.hyperlane-peer.v1")
        check("manifest lists two stables", len(data.get("assets", [])) == 2)
        check("manifest records the ISM", bool(data.get("ism", {}).get("address")))
        peer = data["peer"]["address"]
        code = rpc("eth_getCode", [peer, "latest"])
        check("peer has code", code not in ("0x", "0x0"))
        verified = tool(["verify", "--manifest", str(manifest)], RBRIDGE_RPC_URL=RPC)
        check("manifest verifies", verified.returncode == 0, verified.stderr)

        tampered = json.loads(manifest.read_text())
        tampered["peer"]["address"] = "0x000000000000000000000000000000000000dEaD"
        tampered_path = tmp / "tampered.json"
        tampered_path.write_text(json.dumps(tampered))
        bad = tool(["verify", "--manifest", str(tampered_path)], RBRIDGE_RPC_URL=RPC)
        check("tampered manifest is refused", bad.returncode == 1, bad.stderr)

    mainnet = profile(
        tmp, "mainnet", mailbox=mailbox, assets=assets, chainId=1, mainnet=True
    )
    refused = tool(["deploy", "--profile", str(mainnet), "--yes"], ANVIL_KEY=DEPLOYER_KEY)
    check(
        "mainnet is refused",
        refused.returncode == 3 and "mainnet" in refused.stderr,
        refused.stderr,
    )

    mismatch = profile(tmp, "mismatch", mailbox=mailbox, assets=assets, chainId=11155111)
    wrong_chain = tool(["deploy", "--profile", str(mismatch), "--yes"], ANVIL_KEY=DEPLOYER_KEY)
    check(
        "chain id mismatch is refused",
        wrong_chain.returncode == 3 and "chain id" in wrong_chain.stderr,
        wrong_chain.stderr,
    )

    wrong_decimals = [dict(item) for item in assets]
    wrong_decimals[0]["decimals"] = 18
    bad_decimals = profile(tmp, "decimals", mailbox=mailbox, assets=wrong_decimals)
    wrong = tool(["deploy", "--profile", str(bad_decimals)], ANVIL_KEY=DEPLOYER_KEY)
    check(
        "wrong token decimals is refused",
        wrong.returncode == 2 and "decimals" in wrong.stderr,
        wrong.stderr,
    )

    stripped = {k: v for k, v in os.environ.items() if k != "ANVIL_KEY"}
    missing = subprocess.run(
        [sys.executable, str(TOOL), "deploy", "--profile", str(good)],
        capture_output=True,
        text=True,
        env=stripped,
    )
    check(
        "missing deployer key is refused",
        missing.returncode == 2 and "ANVIL_KEY" in missing.stderr,
        missing.stderr,
    )

    print()
    print(f"hyperlane peer demo: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


def main() -> int:
    if not ANVIL.exists() or not FORGE.exists():
        print(f"Foundry not found at {ANVIL.parent}; install it or set up ~/.foundry/bin")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="rbridge-hyperlane-peer-"))
    anvil = subprocess.Popen(
        [str(ANVIL), "--port", str(PORT), "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_anvil()
        mailbox, usdt, usdc = deploy_mocks()
        return run_checks(tmp, mailbox, usdt, usdc)
    finally:
        anvil.terminate()
        try:
            anvil.wait(timeout=10)
        except subprocess.TimeoutExpired:
            anvil.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
