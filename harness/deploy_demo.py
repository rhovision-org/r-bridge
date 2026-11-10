#!/usr/bin/env python3
"""Rehearse the native-vault deployment path on a private Anvil.

Starts its own Anvil on :8547, then drives `tools/deploy_evm.py` exactly as a testnet
operator would: a profile-driven deploy, an on-chain read-back, a manifest, a re-verify,
and an ERC-20 asset deployment. It also proves the safety gates: mainnet refusal, local-
only without --yes, chain-id mismatch, missing token code, wrong decimals, missing
environment variables, and tamper detection on verify.

No rholo node or testnet credentials are needed. Keys are the public Anvil defaults and
are worth nothing.
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
CAST = Path.home() / ".foundry" / "bin" / "cast"
TOOL = ROOT / "tools" / "deploy_evm.py"
PORT = 8547
RPC = f"http://127.0.0.1:{PORT}"
KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
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
    raise RuntimeError("Anvil did not start on :8547")


def tool(args: list[str], **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )


def deploy_mock_token() -> str:
    result = subprocess.run(
        [
            str(FORGE),
            "create",
            "src/MockERC20.sol:MockERC20",
            "--rpc-url",
            RPC,
            "--private-key",
            KEY,
            "--broadcast",
            "--json",
            "--constructor-args",
            "Test USDT",
            "USDT",
            "6",
        ],
        cwd=ROOT / "contracts" / "evm",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"forge create failed:\n{result.stderr}{result.stdout}")
    return json.loads(result.stdout)["deployedTo"]


def anvil_profile(tmp: Path, **overrides) -> Path:
    profile = json.loads((ROOT / "configs" / "networks" / "anvil.json").read_text())
    profile["rpc"] = RPC
    profile.update(overrides)
    path = tmp / f"profile-{len(list(tmp.glob('profile-*.json')))}.json"
    path.write_text(json.dumps(profile, indent=2))
    return path


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> int:
    if not ANVIL.exists() or not FORGE.exists():
        print(f"Foundry not found at {ANVIL.parent}; install it or set up ~/.foundry/bin")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="rbridge-deploy-"))
    anvil = subprocess.Popen(
        [str(ANVIL), "--port", str(PORT), "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_anvil()
        return run_checks(tmp)
    finally:
        anvil.terminate()
        try:
            anvil.wait(timeout=10)
        except subprocess.TimeoutExpired:
            anvil.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def run_checks(tmp: Path) -> int:
    base = anvil_profile(tmp)
    manifest = tmp / "manifest-eth.json"

    # 1. A profile-driven deployment of the shipped Anvil profile.
    result = tool(
        ["deploy", "--profile", str(base), "--out", str(manifest)], DEPLOYER_KEY=KEY
    )
    check("deploy exits 0", result.returncode == 0, result.stderr.strip())
    if result.returncode == 0:
        data = read_manifest(manifest)
        address = data["contract"]["address"]
        code = rpc("eth_getCode", [address, "latest"])
        check("manifest records chain 31337", data["chainId"] == 31337)
        check("vault has code on chain", code not in ("0x", "0x0"))
        check("deploy block recorded", isinstance(data["contract"]["deployBlock"], int))
        check(
            "runtime code hash matches",
            data["contract"]["runtimeCodeKeccak"]
            == subprocess.run(
                [str(CAST), "keccak", code], capture_output=True, text=True
            ).stdout.strip(),
        )
        check(
            "admin set round-trips",
            data["admins"]
            == [item.lower() for item in json.loads(base.read_text())["admins"]],
        )
        check(
            "asset scale is 1e10",
            data["assets"][0]["scale"] == "10000000000",
        )
        check(
            "no private key in manifest",
            KEY not in manifest.read_text() and "PRIVATE_KEY" not in manifest.read_text(),
        )

        # 2. Re-verify the manifest against the chain.
        verified = tool(["verify", "--manifest", str(manifest), "--rpc", RPC])
        check("verify passes", verified.returncode == 0, verified.stderr.strip())
        tampered = tmp / "tampered.json"
        bad = read_manifest(manifest)
        bad["treasury"] = "0x0000000000000000000000000000000000000001"
        tampered.write_text(json.dumps(bad))
        detected = tool(["verify", "--manifest", str(tampered), "--rpc", RPC])
        check(
            "tampered manifest is detected",
            detected.returncode == 1 and "treasury" in detected.stdout,
            detected.stdout + detected.stderr,
        )

    # 3. ERC-20 asset: token code and decimals are checked, scale is 1.
    token = deploy_mock_token()
    profile = json.loads(base.read_text())
    profile["bridgeId"] = "rbridge:anvil:bridge-usdt"
    profile["assets"].append(
        {
            "assetKey": "ethereum.usdt",
            "token": token,
            "nativeDecimals": 6,
            "rholoDecimals": 6,
            "maxDeposit": "1000000000000",
            "maxLocked": "1000000000000000",
            "withdrawFeeBps": 5,
        }
    )
    token_profile = tmp / "profile-usdt.json"
    token_profile.write_text(json.dumps(profile))
    token_manifest = tmp / "manifest-usdt.json"
    result = tool(
        ["deploy", "--profile", str(token_profile), "--out", str(token_manifest)],
        DEPLOYER_KEY=KEY,
    )
    check("ERC-20 deploy exits 0", result.returncode == 0, result.stderr.strip())
    if result.returncode == 0:
        data = read_manifest(token_manifest)
        usdt = next(item for item in data["assets"] if item["assetKey"] == "ethereum.usdt")
        check("ERC-20 asset recorded", usdt["token"] == token.lower())
        check("ERC-20 scale is 1", usdt["scale"] == "1")
        check(
            "ERC-20 manifest verifies",
            tool(["verify", "--manifest", str(token_manifest), "--rpc", RPC]).returncode == 0,
        )
        env_out = tool(["print-env", "--manifest", str(token_manifest)])
        check(
            "print-env emits the web settings",
            f"VITE_RBRIDGE_VAULT={data['contract']['address']}" in env_out.stdout
            and f"VITE_RBRIDGE_USDT={token.lower()}" in env_out.stdout,
            env_out.stdout,
        )

    # 4. Safety gates.
    mainnet = anvil_profile(tmp, chainId=1, bridgeId="rbridge:mainnet:bridge")
    refused = tool(["deploy", "--profile", str(mainnet), "--out", str(tmp / "x.json")],
                   DEPLOYER_KEY=KEY)
    check(
        "mainnet is refused",
        refused.returncode == 3 and "mainnet" in refused.stderr,
        refused.stderr,
    )

    remote = anvil_profile(tmp, chainId=11155111, bridgeId="rbridge:sepolia:probe")
    not_local = tool(
        ["deploy", "--profile", str(remote), "--out", str(tmp / "x.json")], DEPLOYER_KEY=KEY
    )
    check(
        "non-local chain needs --yes",
        not_local.returncode == 3 and "not local" in not_local.stderr,
        not_local.stderr,
    )
    mismatch = tool(
        ["deploy", "--profile", str(remote), "--out", str(tmp / "x.json"), "--yes"],
        DEPLOYER_KEY=KEY,
    )
    check(
        "chain-id mismatch is refused",
        mismatch.returncode == 3 and "chain id" in mismatch.stderr,
        mismatch.stderr,
    )

    missing_key = tool(
        ["deploy", "--profile", str(base), "--out", str(tmp / "x.json")],
        DEPLOYER_KEY="",
    )
    check(
        "deploy needs a key",
        missing_key.returncode == 2 and "DEPLOYER_KEY" in missing_key.stderr,
        missing_key.stderr,
    )

    no_code = anvil_profile(tmp, bridgeId="rbridge:anvil:nocode")
    no_code_data = json.loads(no_code.read_text())
    no_code_data["assets"].append(
        {
            "assetKey": "ethereum.usdt",
            "token": "0x1111111111111111111111111111111111111111",
            "nativeDecimals": 6,
            "rholoDecimals": 6,
            "maxDeposit": "1",
            "maxLocked": "1",
            "withdrawFeeBps": 5,
        }
    )
    no_code.write_text(json.dumps(no_code_data))
    empty = tool(
        ["deploy", "--profile", str(no_code), "--out", str(tmp / "x.json")],
        DEPLOYER_KEY=KEY,
    )
    check(
        "token without code is refused",
        empty.returncode == 2 and "no ERC-20 code" in empty.stderr,
        empty.stderr,
    )

    wrong_decimals = anvil_profile(tmp, bridgeId="rbridge:anvil:wrongdec")
    wrong_data = json.loads(wrong_decimals.read_text())
    if token:
        wrong_data["assets"].append(
            {
                "assetKey": "ethereum.usdt",
                "token": token,
                "nativeDecimals": 8,
                "rholoDecimals": 8,
                "maxDeposit": "1",
                "maxLocked": "1",
                "withdrawFeeBps": 5,
            }
        )
        wrong_decimals.write_text(json.dumps(wrong_data))
        wrong = tool(
            ["deploy", "--profile", str(wrong_decimals), "--out", str(tmp / "x.json")],
            DEPLOYER_KEY=KEY,
        )
        check(
            "wrong token decimals is refused",
            wrong.returncode == 2 and "decimals" in wrong.stderr,
            wrong.stderr,
        )

    sepolia = ROOT / "configs" / "networks" / "ethereum-sepolia.json"
    stripped = {name: value for name, value in os.environ.items() if not name.startswith("SEPOLIA_")}
    missing = subprocess.run(
        [sys.executable, str(TOOL), "deploy", "--profile", str(sepolia), "--dry-run"],
        capture_output=True,
        text=True,
        env=stripped,
    )
    check(
        "missing profile env is reported",
        missing.returncode == 2 and "SEPOLIA_RPC_URL" in missing.stderr,
        missing.stderr,
    )
    sepolia_env = {
        "SEPOLIA_RPC_URL": RPC,
        "SEPOLIA_ADMIN_1": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "SEPOLIA_ADMIN_2": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        "SEPOLIA_ADMIN_3": "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
        "SEPOLIA_RELAYER_1": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
        "SEPOLIA_RELAYER_2": "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
        "SEPOLIA_RELAYER_3": "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
        "SEPOLIA_TREASURY": "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955",
        "SEPOLIA_USDC": token,
    }
    plan = subprocess.run(
        [sys.executable, str(TOOL), "deploy", "--profile", str(sepolia), "--dry-run"],
        capture_output=True,
        text=True,
        env={**stripped, **sepolia_env},
    )
    check(
        "Sepolia plan builds without a key",
        plan.returncode == 0 and "no transaction sent" in plan.stdout,
        plan.stdout + plan.stderr,
    )

    print()
    print(f"deploy demo: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
