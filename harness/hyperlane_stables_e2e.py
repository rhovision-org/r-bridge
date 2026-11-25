#!/usr/bin/env python3
"""Ethereum stablecoin loop: USDT lock on Anvil -> rholo mint -> burn -> release on Anvil.

Starts its own Anvil on :8549, deploys the mock Mailbox + USDT/USDC + the HyperlanePeer
through `tools/deploy_hyperlane_peer.py`, installs the wired rholo Bridge, then plays the
relayer by copying the dispatched messages in both directions. This is the same message
and payload path a Sepolia deployment uses; only the Mailbox and tokens are local mocks.

Requires a running rholo devnet (`make devnet-up`). Uses the funded devnet key as the
rholo relayer and the public Anvil accounts for the EVM side.
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
TOOL = ROOT / "tools" / "deploy_hyperlane_peer.py"
EVM = ROOT / "contracts" / "evm"
CONFIG = ROOT / "configs" / "hyperlane" / "devnet.json"
DEVNET_CONFIG = ROOT / "configs" / "devnet.json"
PORT = 8549
RPC = f"http://127.0.0.1:{PORT}"
DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
OWNER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
RELAYER_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
RELAYER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
USER_KEY = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"
USER = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
RHOLO_SENDER = "00" * 31 + "dd"
REMOTE_DOMAIN = 31337

sys.path.insert(0, str(ROOT / "harness"))
import render  # noqa: E402
from hyperlane_demo import CHECKS, FUNDED_KEY, call, cli, decode, deploy, expect, oracle  # noqa: E402


def rpc(method: str, params: list | None = None):
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    ).encode()
    request = urllib.request.Request(
        RPC, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response).get("result")


def wait_for_anvil(deadline: float = 20.0) -> None:
    end = time.time() + deadline
    while time.time() < end:
        try:
            if int(rpc("eth_chainId"), 16) == REMOTE_DOMAIN:
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Anvil did not start on :8549")


def cast(*args: str, key: str | None = None) -> str:
    command = [str(CAST), *args, "--rpc-url", RPC]
    if key:
        command += ["--private-key", key]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cast {' '.join(args)} failed:\n{result.stderr}{result.stdout}")
    return result.stdout.strip()


def cast_uint(*args: str) -> int:
    return int(cast("call", *args).split()[0])


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
        env={**os.environ, "PRIVATE_KEY": DEPLOYER_KEY, "LOCAL_DOMAIN": str(REMOTE_DOMAIN)},
    )
    if result.returncode != 0:
        raise RuntimeError(f"mock deploy failed:\n{result.stderr}{result.stdout}")
    artifact = EVM / "broadcast" / "DeployHyperlaneMocks.s.sol" / str(REMOTE_DOMAIN) / "run-latest.json"
    data = json.loads(artifact.read_text())
    mailbox = None
    tokens = []
    for tx in data.get("transactions", []):
        if tx.get("contractName") == "MockHyperlaneMailbox":
            mailbox = tx.get("contractAddress")
        elif tx.get("contractName") == "MockERC20":
            tokens.append(tx.get("contractAddress"))
    if not mailbox or len(tokens) < 2:
        raise RuntimeError("mock broadcast artifact is incomplete")
    return mailbox, tokens[0], tokens[1]


def main() -> int:
    config = json.loads(CONFIG.read_text())
    devnet = json.loads(DEVNET_CONFIG.read_text())
    local_domain = int(config["localDomain"])
    tree_id = str(config["treeId"])
    threshold = int(config["validatorThreshold"])

    tmp = Path(tempfile.mkdtemp(prefix="rbridge-stables-"))
    anvil = subprocess.Popen(
        [str(ANVIL), "--port", str(PORT), "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_anvil()
        mailbox, usdt, usdc = deploy_mocks()

        # The peer is deployed first so the rholo Router can enrol its address.
        peer_word = None
        profile = {
            "schema": "rbridge.hyperlane-peer.v1",
            "network": "rbridge-hyperlane-e2e",
            "chainName": "ethereum",
            "chainId": REMOTE_DOMAIN,
            "rpc": RPC,
            "mailbox": mailbox,
            "localDomain": REMOTE_DOMAIN,
            "remoteDomain": local_domain,
            "remotePeer": "0x" + RHOLO_SENDER,
            "relayer": RELAYER,
            "owner": OWNER,
            "deployerKeyEnv": "ANVIL_KEY",
            "mainnet": False,
            "assets": [
                {"assetKey": "ethereum.usdt", "token": usdt, "decimals": 6, "scale": 1,
                 "maxDeposit": "10000000000", "maxLocked": "1000000000000"},
                {"assetKey": "ethereum.usdc", "token": usdc, "decimals": 6, "scale": 1,
                 "maxDeposit": "10000000000", "maxLocked": "1000000000000"},
            ],
        }
        profile_path = tmp / "peer.json"
        profile_path.write_text(json.dumps(profile, indent=2))
        manifest_path = tmp / "peer-manifest.json"
        deployed = subprocess.run(
            [sys.executable, str(TOOL), "deploy", "--profile", str(profile_path), "--out", str(manifest_path)],
            capture_output=True,
            text=True,
            env={**os.environ, "ANVIL_KEY": DEPLOYER_KEY},
        )
        if deployed.returncode != 0:
            raise RuntimeError(f"peer deploy failed:\n{deployed.stderr}{deployed.stdout}")
        manifest = json.loads(manifest_path.read_text())
        peer = manifest["peer"]["address"]
        peer_word = "00" * 12 + peer[2:].lower()
        expect("peer deployed", len(peer) == 42, True)

        # Install the wired rholo Bridge with the peer as the EVM domain sender.
        public = cli("key-info", "--key", FUNDED_KEY)["public"]
        trusted = oracle("processor", "--pubkey", public)["processor"]
        validators = [cli("keygen") for _ in range(3)]
        installed = deploy(
            render.render_hyperlane_bridge(
                network="rbridge-hyperlane-e2e",
                bridge_id="rbridge:hyperlane:e2e",
                treasury=cli("key-info", "--key", FUNDED_KEY)["rev_address"],
                admins=[public],
                admin_threshold=1,
                relayers=[public] + [validator["public"] for validator in validators],
                relayer_threshold=2,
                assets=devnet["assets"],
                local_domain=local_domain,
                sender_id=RHOLO_SENDER,
                trusted_relayer=trusted,
                ism_mode="trusted",
                validators=[validator["public"] for validator in validators],
                threshold=threshold,
                tree_id=tree_id,
                by_domain={str(REMOTE_DOMAIN): peer_word},
                routes={"ethereum": {"domain": REMOTE_DOMAIN, "peer": peer_word}},
            ),
            "install_stables_bridge.rho",
        )
        bridge, mailbox_uri, _, _ = decode((installed.get("deploy_result") or [])[0])
        rev = cli("key-info", "--key", FUNDED_KEY)["rev_address"]
        expect("bridge installed", bridge.startswith("rho:id:"), True)

        def bridge_call(body: str, name: str):
            return call(bridge, body, name)

        def mailbox_call(body: str, name: str):
            return call(mailbox_uri, body, name)

        # 1. User locks 1 USDT; the peer dispatches a message.
        cast("send", usdt, "mint(address,uint256)", USER, "10000000", key=DEPLOYER_KEY)
        cast("send", usdt, "approve(address,uint256)", peer, "10000000", key=USER_KEY)
        cast("send", peer, "lock(address,uint256,string)", usdt, "1000000", rev, key=USER_KEY)
        dispatch_id = cast("call", mailbox, "latestDispatchedId()(bytes32)")
        message = cast("call", mailbox, "dispatched(bytes32)(bytes)", dispatch_id)
        message_hex = message[2:] if message.startswith("0x") else message
        parsed = oracle("parse-message", "--message", message_hex)
        expect("deposit origin", parsed["origin"], REMOTE_DOMAIN)
        expect("deposit destination", parsed["destination"], local_domain)
        expect("deposit sender", parsed["sender"], peer_word)
        expect("deposit recipient", parsed["recipient"], RHOLO_SENDER)
        body_text = bytes.fromhex(parsed["body"]).decode()
        body_fields = body_text.split("|")
        expect(
            "deposit prefix",
            body_text.startswith(f"rbridge:hyperlane:v1|deposit|ethereum.usdt|1000000|{rev}|"),
            True,
        )
        expect("deposit field count", len(body_fields), 7)
        expect("deposit external id length", len(body_fields[5]) if len(body_fields) == 7 else 0, 64)
        expect("deposit nonce", body_fields[6] if len(body_fields) == 7 else "", "0")

        # 2. Relayer copies the EVM message to the rholo Mailbox; the Bridge mints.
        dispatch_hex = dispatch_id[2:] if dispatch_id.startswith("0x") else dispatch_id
        processed = mailbox_call(
            f'C!("process", "".hexToBytes(), "{message_hex}".hexToBytes(), *ret)',
            "e2e_process_deposit.rho",
        )
        expect("rholo process", processed, (True, dispatch_hex))
        expect("rholo credited", bridge_call(f'C!("balanceOf", "ethereum.usdt", "{rev}", *ret)', "e2e_balance.rho")[1], 999_500)

        # 2b. The same loop for USDC: lock, relay, mint.
        cast("send", usdc, "mint(address,uint256)", USER, "10000000", key=DEPLOYER_KEY)
        cast("send", usdc, "approve(address,uint256)", peer, "10000000", key=USER_KEY)
        cast("send", peer, "lock(address,uint256,string)", usdc, "2000000", rev, key=USER_KEY)
        usdc_message = cast("call", mailbox, "dispatched(bytes32)(bytes)", cast("call", mailbox, "latestDispatchedId()(bytes32)"))
        usdc_hex = usdc_message[2:] if usdc_message.startswith("0x") else usdc_message
        expect(
            "usdc rholo process",
            mailbox_call(f'C!("process", "".hexToBytes(), "{usdc_hex}".hexToBytes(), *ret)', "e2e_process_usdc.rho")[0],
            True,
        )
        expect(
            "usdc rholo credited",
            bridge_call(f'C!("balanceOf", "ethereum.usdc", "{rev}", *ret)', "e2e_usdc_balance.rho")[1],
            1_999_000,
        )

        # 3. Burn 0.5 USDT on rholo; the Bridge dispatches the withdrawal.
        burn = bridge_call(
            f'C!("burn", "ethereum", "usdt", 500000, "ethereum", "{USER.lower()}", "e2e-withdraw-1", *ret)',
            "e2e_burn.rho",
        )
        expect("rholo burn", burn, (True, "e2e-withdraw-1"))
        withdrawal = bridge_call('C!("withdrawal", "e2e-withdraw-1", *ret)', "e2e_withdrawal.rho")
        outbound_id = withdrawal[1].get("dispatch")
        outbound = mailbox_call(f'C!("dispatched", "{outbound_id}", *ret)', "e2e_outbound.rho")
        expect("outbound recorded", outbound[0], True)
        outbound_hex = outbound[1]
        outbound_parsed = oracle("parse-message", "--message", outbound_hex)
        expect("withdraw origin", outbound_parsed["origin"], local_domain)
        expect("withdraw destination", outbound_parsed["destination"], REMOTE_DOMAIN)
        expect("withdraw recipient", outbound_parsed["recipient"], peer_word)

        # 4. Relayer copies the rholo message to the EVM Mailbox; the peer releases.
        cast("send", mailbox, "process(bytes,bytes)", "0x", "0x" + outbound_hex, key=RELAYER_KEY)
        expect(
            "evm released to user",
            cast_uint(usdt, "balanceOf(address)(uint256)", USER),
            9_500_000,
        )
        expect("peer still locked", cast_uint(peer, "locked(address)(uint256)", usdt), 500_000)
        expect(
            "rholo balance after burn",
            bridge_call(f'C!("balanceOf", "ethereum.usdt", "{rev}", *ret)', "e2e_balance2.rho")[1],
            499_500,
        )

        passed = sum(CHECKS)
        print(f"\nhyperlane stables e2e: {passed}/{len(CHECKS)} checks passed")
        return 0 if passed == len(CHECKS) else 1
    finally:
        anvil.terminate()
        try:
            anvil.wait(timeout=10)
        except subprocess.TimeoutExpired:
            anvil.kill()
        shutil.rmtree(tmp, ignore_errors=True)



if __name__ == "__main__":
    raise SystemExit(main())
