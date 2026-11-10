#!/usr/bin/env python3
"""Dev relayer loop: watch Anvil deposits and rholo withdrawals, then settle.

This is the rail-agnostic demo of what a production relayer must do. It is NOT the
production add-on: fixed dev keys, no reorg handling, no bond/slashing, no metrics.
The point is to make the watcher/attester/submitter contract concrete while the rail
(standalone bridge node vs rholo plugin/sidecar) is still undecided.

  Anvil Deposit  -> sign 2-of-3 deposit digest -> Bridge.mint on rholo
  rholo pending  -> sign 2-of-3 withdrawal digest (65-byte) -> vault.unlock -> complete

Start it before locking; it only scans new Anvil blocks.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVNET = ROOT / ".devnet"
KEYS_FILE = DEVNET / "demo-keys.json"
BRIDGE_FILE = DEVNET / "bridge.json"
EVM_FILE = DEVNET / "evm.json"
STATE_FILE = DEVNET / "relayer_state.json"
ANVIL_RPC = "http://127.0.0.1:8545"
ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ZERO = "0x0000000000000000000000000000000000000000"
CAST = Path.home() / ".foundry" / "bin" / "cast"

sys.path.insert(0, str(ROOT / "harness"))
import demo  # noqa: E402


def cast(*args: str) -> str:
    result = subprocess.run([str(CAST), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cast {' '.join(args)} failed:\n{result.stderr}{result.stdout}")
    return result.stdout.strip()


def cast_json(*args: str) -> dict:
    return json.loads(cast(*args, "--json"))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def deposit_topic() -> str:
    return cast("keccak", "Deposit(bytes32,address,address,uint256,string,uint256)")


def asset_config(vault: str, token: str) -> dict:
    out = cast(
        "call",
        vault,
        "assets(address)(bool,uint256,uint256,uint256,uint256,string)",
        token,
        "--rpc-url",
        ANVIL_RPC,
    )
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return {
        "enabled": lines[0] == "true",
        "max_deposit": int(lines[1].split()[0]),
        "max_locked": int(lines[2].split()[0]),
        "scale": int(lines[3].split()[0]),
        "fee_bps": int(lines[4].split()[0]),
        "asset_key": lines[5].strip('"'),
    }


def decode_deposit(log: dict) -> dict:
    data = bytes.fromhex(log["data"][2:])
    amount = int.from_bytes(data[0:32], "big")
    offset = int.from_bytes(data[32:64], "big")
    nonce = int.from_bytes(data[64:96], "big")
    length = int.from_bytes(data[offset : offset + 32], "big")
    recipient = data[offset + 32 : offset + 32 + length].decode()
    return {
        "deposit_id": log["topics"][1],
        "token": "0x" + log["topics"][2][-40:],
        "sender": "0x" + log["topics"][3][-40:],
        "amount_native": amount,
        "recipient": recipient,
        "nonce": nonce,
        "block": int(log["blockNumber"], 16),
        "tx": log["transactionHash"],
    }


class Relayer:
    def __init__(self, keys: dict, bridge: dict, vault: str, interval: float, from_block: int | None):
        self.keys = keys
        self.bridge = bridge
        self.vault = vault
        self.interval = interval
        self.deployer = keys["deployer"]
        self.relayer_secrets = [self.deployer["secret"], keys["relayers"][0]["secret"]]
        demo.DEPLOY_SECRET = self.deployer["secret"]
        self.topic = deposit_topic()
        if STATE_FILE.exists():
            self.state = load_json(STATE_FILE)
        else:
            latest = int(cast("block-number", "--rpc-url", ANVIL_RPC))
            self.state = {"last_block": latest, "deposits": [], "withdrawals": []}
            save_state(self.state)
        if from_block is not None:
            self.state["last_block"] = from_block
        # Only settle withdrawals created after this watcher starts. Historical pending
        # records (for example from an earlier Anvil instance) are not ours to release.
        self.ignored_withdrawals: set[str] = set()
        try:
            pending = demo.call_read(
                self.bridge["uri"], 'Bridge!("pendingWithdrawals", *ret)', "relayer_snapshot.rho"
            )
            if pending and pending[0] is True:
                self.ignored_withdrawals = set(pending[1])
        except Exception as error:  # noqa: BLE001 - dev loop
            print(f"snapshot warning: {error}")
        # The bridge was installed with these assets; read the config per token lazily.
        self.assets: dict[str, dict] = {}

    def scan_deposits(self) -> None:
        latest = int(cast("block-number", "--rpc-url", ANVIL_RPC))
        start = self.state["last_block"] + 1
        if latest < start:
            return
        out = cast(
            "logs",
            "--address",
            self.vault,
            "--from-block",
            str(start),
            "--to-block",
            str(latest),
            "--json",
            "--rpc-url",
            ANVIL_RPC,
        )
        logs = json.loads(out) if out else []
        for log in logs:
            if log.get("topics", [""])[0] != self.topic:
                continue
            deposit = decode_deposit(log)
            if deposit["deposit_id"] in self.state["deposits"]:
                continue
            self.settle_deposit(deposit)
        self.state["last_block"] = latest
        save_state(self.state)

    def settle_deposit(self, deposit: dict) -> None:
        token = deposit["token"]
        if token not in self.assets:
            self.assets[token] = asset_config(self.vault, token)
        config = self.assets[token]
        scale = config["scale"]
        amount_native = deposit["amount_native"]
        if amount_native % scale != 0:
            print(f"skip deposit {deposit['deposit_id']}: not a scale multiple")
            self.state["deposits"].append(deposit["deposit_id"])
            save_state(self.state)
            return
        amount_rholo = amount_native // scale
        chain, asset_id = config["asset_key"].split(".", 1)
        message = (
            f"rbridge:v1|{self.bridge['network']}|{chain}|{self.bridge['bridge_id']}|"
            f"{config['asset_key']}|deposit|{deposit['deposit_id']}|{amount_rholo}|"
            f"{deposit['recipient']}|{deposit['nonce']}"
        )
        signatures = [demo.sign_text(secret, message)["signature"] for secret in self.relayer_secrets]
        result = demo.call_write(
            self.bridge["uri"],
            f'Bridge!("mint", "{chain}", "{asset_id}", "{deposit["deposit_id"]}", {amount_rholo}, '
            f'"{deposit["recipient"]}", {deposit["nonce"]}, '
            f'[{demo.signature_literals(signatures)}], *ret)',
            self.deployer["secret"],
            "relayer_mint.rho",
        )
        print(f"deposit {deposit['deposit_id']} -> mint {result!r}")
        if result and result[0] is True:
            self.state["deposits"].append(deposit["deposit_id"])
            save_state(self.state)
        elif result == (False, "replay"):
            self.state["deposits"].append(deposit["deposit_id"])
            save_state(self.state)

    def scan_withdrawals(self) -> None:
        pending = demo.call_read(
            self.bridge["uri"], 'Bridge!("pendingWithdrawals", *ret)', "relayer_pending.rho"
        )
        if not (pending and pending[0] is True):
            return
        for withdrawal_id in pending[1]:
            if withdrawal_id in self.state["withdrawals"] or withdrawal_id in self.ignored_withdrawals:
                continue
            record = demo.call_read(
                self.bridge["uri"],
                f'Bridge!("withdrawal", "{withdrawal_id}", *ret)',
                "relayer_withdrawal.rho",
            )
            if not (record and record[0] is True):
                continue
            withdrawal = record[1]
            asset_key = f"{withdrawal.get('chain')}.{withdrawal.get('assetId')}"
            recipient = str(withdrawal.get("destAddress", "")).lower()
            if (
                withdrawal.get("status") != "pending"
                or withdrawal.get("destChain") != "ethereum"
                or asset_key != "ethereum.eth"
                or not re.fullmatch(r"0x[0-9a-f]{40}", recipient)
            ):
                # The dev watcher only settles the Anvil ETH asset and well-formed
                # 20-byte destinations; other pending records are left to their rail.
                self.state["withdrawals"].append(withdrawal_id)
                save_state(self.state)
                continue
            self.settle_withdrawal(withdrawal_id, withdrawal)

    def settle_withdrawal(self, withdrawal_id: str, withdrawal: dict) -> None:
        asset_key = f"{withdrawal['chain']}.{withdrawal['assetId']}"
        amount = int(withdrawal["amount"])
        recipient = withdrawal["destAddress"].lower()
        message = (
            f"rbridge:v1|{self.bridge['network']}|ethereum|{self.bridge['bridge_id']}|"
            f"{asset_key}|withdraw|{withdrawal_id}|{amount}|{recipient}|0"
        )
        signatures = [
            demo.cli("sign-text-eth", "--key", secret, "--text", message)["signature"]
            for secret in self.relayer_secrets
        ]
        sig_array = "[" + ",".join("0x" + sig for sig in signatures) + "]"
        try:
            tx = cast_json(
                "send",
                self.vault,
                "unlock(address,address,uint256,string,uint256,bytes[])",
                ZERO,
                recipient,
                str(amount),
                withdrawal_id,
                "0",
                sig_array,
                "--private-key",
                ANVIL_KEY,
                "--rpc-url",
                ANVIL_RPC,
            )
        except RuntimeError as error:
            print(f"withdrawal {withdrawal_id}: unlock failed: {error}")
            return
        native_tx = tx["transactionHash"]
        complete = demo.call_write(
            self.bridge["uri"],
            f'Bridge!("completeWithdrawal", "{withdrawal_id}", "{native_tx}", *ret)',
            self.deployer["secret"],
            "relayer_complete.rho",
        )
        print(f"withdrawal {withdrawal_id} -> unlock {native_tx} complete {complete!r}")
        if complete and complete[0] is True:
            self.state["withdrawals"].append(withdrawal_id)
            save_state(self.state)

    def run(self) -> None:
        print(f"dev relayer: vault={self.vault} bridge={self.bridge['uri']}")
        print(f"             start block={self.state['last_block']} interval={self.interval}s")
        while True:
            try:
                self.scan_deposits()
                self.scan_withdrawals()
            except Exception as error:  # noqa: BLE001 - keep the dev loop alive
                print(f"relayer error: {error}")
            time.sleep(self.interval)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--from-block", type=int, default=None)
    args = ap.parse_args()

    for path in (KEYS_FILE, BRIDGE_FILE, EVM_FILE):
        if not path.exists():
            print(f"missing {path}; run `make devnet-up && make demo && make e2e-evm` first")
            return 2
    keys = load_json(KEYS_FILE)
    bridge = load_json(BRIDGE_FILE)
    vault = load_json(EVM_FILE)["vault"]
    Relayer(keys, bridge, vault, args.interval, args.from_block).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
