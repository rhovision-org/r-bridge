#!/usr/bin/env python3
"""Dev relayer loop: watch Anvil deposits and rholo withdrawals, then settle.

This is the rail-agnostic demo of what a production relayer must do. It is NOT the
production add-on: fixed dev keys, no bond/slashing, no metrics. It does implement the
safety shape: a finality/confirmation gate, a reorg-aware journal and a fail-closed halt
when a settled deposit is reorged out.

  Anvil Deposit  -> wait for the safe head -> sign 2-of-3 digest -> Bridge.mint on rholo
  rholo pending  -> sign 2-of-3 withdrawal digest (65-byte) -> vault.unlock -> complete

Options: `--confirmations N` (default 0 for the dev loop), `--finalized` to follow the
chain's finalized tag, `--dry-run` to scan/journal without rholo calls, `--once` for a
single scan, `--state-file` for an isolated journal.

Start it before locking; it only scans new Anvil blocks.
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def rpc(method: str, params: list | None = None):
    """Raw JSON-RPC against Anvil, for block hashes and finality."""
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    ).encode()
    request = urllib.request.Request(
        ANVIL_RPC, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.load(response)
    if "error" in body:
        raise RuntimeError(body["error"])
    return body.get("result")


def block_at(number: int) -> dict | None:
    return rpc("eth_getBlockByNumber", [hex(number), False])


def cast(*args: str) -> str:
    result = subprocess.run([str(CAST), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cast {' '.join(args)} failed:\n{result.stderr}{result.stdout}")
    return result.stdout.strip()


def cast_json(*args: str) -> dict:
    return json.loads(cast(*args, "--json"))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


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
        "block_hash": log.get("blockHash", ""),
        "tx": log["transactionHash"],
    }


class Relayer:
    def __init__(
        self,
        keys: dict,
        bridge: dict,
        vault: str,
        interval: float,
        from_block: int | None,
        state_path: Path = STATE_FILE,
        dry_run: bool = False,
        confirmations: int = 0,
        finalized: bool = False,
        reorg_window: int = 128,
    ):
        self.keys = keys
        self.bridge = bridge
        self.vault = vault
        self.interval = interval
        self.state_path = state_path
        self.dry_run = dry_run
        self.confirmations = max(0, confirmations)
        self.finalized = finalized
        self.reorg_window = max(1, reorg_window)
        self.deployer = keys["deployer"]
        self.relayer_secrets = [self.deployer["secret"], keys["relayers"][0]["secret"]]
        demo.DEPLOY_SECRET = self.deployer["secret"]
        evm = load_json(EVM_FILE) if EVM_FILE.exists() else {}
        self.token_for = evm.get("asset_keys", {"ethereum.eth": ZERO})
        self.topic = deposit_topic()
        if state_path.exists():
            self.state = load_json(state_path)
        else:
            self.state = {}
        if from_block is not None:
            self.state["last_block"] = from_block
        self.state.setdefault(
            "last_block", int(cast("block-number", "--rpc-url", ANVIL_RPC))
        )
        self.state.setdefault("deposits", [])
        self.state.setdefault("withdrawals", [])
        self.state.setdefault("withdrawals_detail", {})
        self.state.setdefault("deposit_blocks", {})
        self.state.setdefault("block_hashes", {})
        self.state.setdefault("reorgs", [])
        self.state.setdefault("failed_deposits", {})
        self.state.setdefault("halted", None)
        self.save()
        # Only settle withdrawals created after this watcher starts. Historical pending
        # records (for example from an earlier Anvil instance) are not ours to release.
        self.ignored_withdrawals: set[str] = set()
        if not self.dry_run:
            try:
                pending = demo.call_read(
                    self.bridge["uri"],
                    'Bridge!("pendingWithdrawals", *ret)',
                    "relayer_snapshot.rho",
                )
                if pending and pending[0] is True:
                    self.ignored_withdrawals = set(pending[1])
            except Exception as error:  # noqa: BLE001 - dev loop
                print(f"snapshot warning: {error}")
        # The bridge was installed with these assets; read the config per token lazily.
        self.assets: dict[str, dict] = {}
        self.rholo_assets: dict[str, dict] = {}
        self.http_server: ThreadingHTTPServer | None = None
        self._halted_reported = False

    def metrics_text(self) -> str:
        """Prometheus exposition for the rail-agnostic metric names in the spec."""
        settled = len(self.state["deposits"])
        failed = len(self.state["failed_deposits"])
        withdrawals = len(self.state["withdrawals"])
        reorgs = len(self.state["reorgs"])
        halted = 1 if self.state["halted"] else 0
        return "\n".join(
            [
                "# HELP rbridge_chain_head Last processed deposit block.",
                "# TYPE rbridge_chain_head gauge",
                f'rbridge_chain_head{{chain="ethereum"}} {self.state["last_block"]}',
                "# HELP rbridge_deposits_total Deposits by settlement state.",
                "# TYPE rbridge_deposits_total counter",
                f'rbridge_deposits_total{{chain="ethereum",state="settled"}} {settled}',
                f'rbridge_deposits_total{{chain="ethereum",state="failed"}} {failed}',
                "# HELP rbridge_withdrawals_total Settled native withdrawals.",
                "# TYPE rbridge_withdrawals_total counter",
                f'rbridge_withdrawals_total{{chain="ethereum",state="settled"}} {withdrawals}',
                "# HELP rbridge_reorgs_total Reorgs detected at or below the tip.",
                "# TYPE rbridge_reorgs_total counter",
                f"rbridge_reorgs_total {reorgs}",
                "# HELP rbridge_errors_total Refusals and safety events.",
                "# TYPE rbridge_errors_total counter",
                f'rbridge_errors_total{{chain="ethereum",kind="failed_deposit"}} {failed}',
                f'rbridge_errors_total{{chain="ethereum",kind="reorg"}} {reorgs}',
                "# HELP rbridge_halted 1 when the relayer stopped settling.",
                "# TYPE rbridge_halted gauge",
                f"rbridge_halted {halted}",
                "",
            ]
        )

    def health(self) -> dict:
        return {
            "version": "dev",
            "chains": ["ethereum"],
            "threshold": 2,
            "paused": False,
            "halted": self.state["halted"],
            "last_block": self.state["last_block"],
            "deposits": {
                "settled": len(self.state["deposits"]),
                "failed": len(self.state["failed_deposits"]),
            },
            "withdrawals": len(self.state["withdrawals"]),
            "reorgs": len(self.state["reorgs"]),
            "dry_run": self.dry_run,
            "confirmations": self.confirmations,
            "finalized": self.finalized,
        }

    def chains(self) -> list[dict]:
        return [
            {
                "chain": "ethereum",
                "head": self.state["last_block"],
                "confirmations": self.confirmations,
                "finalized": self.finalized,
                "enabled": self.state["halted"] is None,
            }
        ]

    def deposit_view(self, deposit_id: str) -> dict | None:
        record = self.state["deposit_blocks"].get(deposit_id)
        if record:
            return {
                "deposit_id": deposit_id,
                "state": record.get("state", "settled"),
                "message": record.get("message"),
                "signatures": record.get("signatures", []),
                "block": record.get("block"),
                "tx": record.get("tx"),
                "dry_run": record.get("dry_run", False),
            }
        failed = self.state["failed_deposits"].get(deposit_id)
        if failed:
            return {
                "deposit_id": deposit_id,
                "state": "failed",
                "error": failed.get("reason"),
                "block": failed.get("block"),
                "tx": failed.get("tx"),
            }
        return None

    def attestation_view(self, deposit_id: str) -> dict | None:
        record = self.state["deposit_blocks"].get(deposit_id)
        if record and record.get("signatures"):
            return {
                "message": record.get("message"),
                "signatures": record.get("signatures"),
            }
        return None

    def start_http(self, port: int, bind: str) -> None:
        relayer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server API
                parts = self.path.strip("/").split("/")
                if self.path == "/metrics":
                    body = relayer.metrics_text().encode()
                    content_type = "text/plain; version=0.0.4"
                elif self.path == "/health":
                    body = json.dumps(relayer.health()).encode()
                    content_type = "application/json"
                elif self.path == "/v1/chains":
                    body = json.dumps(relayer.chains()).encode()
                    content_type = "application/json"
                elif len(parts) == 3 and parts[:2] == ["v1", "deposits"]:
                    view = relayer.deposit_view(parts[2])
                    if view is None:
                        self.send_error(404)
                        return
                    body = json.dumps(view).encode()
                    content_type = "application/json"
                elif (
                    len(parts) == 4
                    and parts[:2] == ["v1", "deposits"]
                    and parts[3] == "attestation"
                ):
                    view = relayer.attestation_view(parts[2])
                    if view is None:
                        self.send_error(404)
                        return
                    body = json.dumps(view).encode()
                    content_type = "application/json"
                elif len(parts) == 3 and parts[:2] == ["v1", "withdrawals"]:
                    view = relayer.state["withdrawals_detail"].get(parts[2])
                    if view is None:
                        self.send_error(404)
                        return
                    body = json.dumps(view).encode()
                    content_type = "application/json"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:  # noqa: ANN002 - silence access logs
                pass

        self.http_server = ThreadingHTTPServer((bind, port), Handler)
        thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
        thread.start()

    def save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2))

    def safe_head(self) -> int:
        """The highest block whose effects may be settled.

        `--finalized` follows the chain's finalized tag (the production rule);
        otherwise the dev default is `latest - confirmations`.
        """
        if os.environ.get("RBRIDGE_RELAYER_DEBUG"):
            print("safe_head: querying latest")
        latest = int(cast("block-number", "--rpc-url", ANVIL_RPC))
        if os.environ.get("RBRIDGE_RELAYER_DEBUG"):
            print(f"safe_head: latest={latest}")
        if self.finalized:
            block = rpc("eth_getBlockByNumber", ["finalized", False])
            if block:
                return int(block["number"], 16)
            print("finalized block unavailable; falling back to confirmations")
        return max(0, latest - self.confirmations)

    def stale_deposits(self) -> list[str]:
        """Settled deposits whose block hash no longer matches the canonical chain.

        This does not depend on the tip hash being journaled, so it also catches a
        deposit reorged out in the same scan that settled it.
        """
        stale = []
        floor = self.state["last_block"] - self.reorg_window
        for deposit_id, record in self.state["deposit_blocks"].items():
            number = int(record.get("block", 0))
            if number <= floor:
                continue
            block = block_at(number)
            if block is None or block["hash"] != record.get("block_hash"):
                stale.append(deposit_id)
        return sorted(stale)

    def halt_for_reorg(self, deposits: list[str], detail: dict) -> bool:
        self.state["reorgs"].append(detail)
        self.state["halted"] = {
            "reason": "processed deposits were reorged out; reconcile before continuing",
            "at": int(time.time()),
            "deposits": deposits,
        }
        self.save()
        print(f"REORG: processed deposits {deposits} reorged out; HALTED")
        return False

    def check_reorg(self) -> bool:
        """Detect a reorg at or below the processed tip.

        Returns False when a processed deposit moved; the caller halts. Otherwise the
        cursor rolls back to the common ancestor and the unprocessed range is rescanned.
        """
        last = self.state["last_block"]
        if last <= 0:
            return True

        stale = self.stale_deposits()
        if stale:
            return self.halt_for_reorg(
                stale,
                {
                    "detected_at": int(time.time()),
                    "previous_tip": last,
                    "reason": "settled deposit block hash changed",
                    "deposits": stale,
                },
            )

        stored = self.state["block_hashes"].get(str(last))
        if not stored:
            block = block_at(last)
            if block:
                self.state["block_hashes"][str(last)] = block["hash"]
                self.save()
            return True
        current = block_at(last)
        if current and current["hash"] == stored:
            return True
        print(
            f"REORG: processed tip {last} changed "
            f"(stored {stored[:10]}…, now "
            f"{current['hash'][:10] + '…' if current else 'missing'})"
        )

        ancestor = None
        floor = max(1, last - self.reorg_window)
        for number in range(last - 1, floor - 1, -1):
            known = self.state["block_hashes"].get(str(number))
            if not known:
                continue
            candidate = block_at(number)
            if candidate and candidate["hash"] == known:
                ancestor = number
                break
        if ancestor is None:
            ancestor = max(0, last - self.reorg_window)

        affected = sorted(
            deposit_id
            for deposit_id, record in self.state["deposit_blocks"].items()
            if int(record.get("block", 0)) > ancestor
        )
        dropped_failures = sorted(
            deposit_id
            for deposit_id, record in self.state["failed_deposits"].items()
            if int(record.get("block", 0)) > ancestor
        )
        detail = {
            "detected_at": int(time.time()),
            "previous_tip": last,
            "ancestor": ancestor,
            "deposits": affected,
            "failed_deposits": dropped_failures,
        }
        if affected:
            return self.halt_for_reorg(affected, detail)
        self.state["reorgs"].append(detail)

        for deposit_id in dropped_failures:
            self.state["failed_deposits"].pop(deposit_id, None)
        self.state["last_block"] = ancestor
        self.state["block_hashes"] = {
            key: value
            for key, value in self.state["block_hashes"].items()
            if int(key) <= ancestor
        }
        self.save()
        print(f"REORG: rolled back to block {ancestor}; the range will be rescanned")
        return True

    def scan_deposits(self) -> None:
        if self.state["halted"]:
            return
        safe = self.safe_head()
        if os.environ.get("RBRIDGE_RELAYER_DEBUG"):
            print(f"scan: last={self.state['last_block']} safe={safe}")
        if safe <= 0:
            return
        if not self.check_reorg():
            return
        start = self.state["last_block"] + 1
        if start > safe:
            return
        out = cast(
            "logs",
            "--address",
            self.vault,
            "--from-block",
            str(start),
            "--to-block",
            str(safe),
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
        recorded_to = self.state["last_block"]
        for number in range(max(start, safe - self.reorg_window + 1), safe + 1):
            block = block_at(number)
            if block is None:
                print(f"scan: block {number} vanished mid-scan; stopping at {recorded_to}")
                break
            self.state["block_hashes"][str(number)] = block["hash"]
            recorded_to = number
        self.state["last_block"] = recorded_to if recorded_to < safe else safe
        floor = safe - self.reorg_window
        self.state["block_hashes"] = {
            key: value
            for key, value in self.state["block_hashes"].items()
            if int(key) > floor
        }
        self.save()

    def settle_deposit(self, deposit: dict) -> None:
        token = deposit["token"]
        if token not in self.assets:
            self.assets[token] = asset_config(self.vault, token)
        config = self.assets[token]
        scale = config["scale"]
        amount_native = deposit["amount_native"]
        if amount_native % scale != 0:
            print(f"skip deposit {deposit['deposit_id']}: not a scale multiple")
            self.mark_deposit(deposit, "skipped")
            return
        amount_rholo = amount_native // scale
        chain, asset_id = config["asset_key"].split(".", 1)
        message = (
            f"rbridge:v1|{self.bridge['network']}|{chain}|{self.bridge['bridge_id']}|"
            f"{config['asset_key']}|deposit|{deposit['deposit_id']}|{amount_rholo}|"
            f"{deposit['recipient']}|{deposit['nonce']}"
        )
        if self.dry_run:
            print(
                f"dry-run: would mint {amount_rholo} {config['asset_key']} "
                f"for deposit {deposit['deposit_id']} (block {deposit['block']})"
            )
            self.mark_deposit(deposit, "dry_run", message=message)
            return
        if config["asset_key"] not in self.rholo_assets:
            record = demo.call_read(
                self.bridge["uri"],
                f'Bridge!("asset", "{config["asset_key"]}", *ret)',
                "relayer_asset.rho",
            )
            if record and record[0] is True:
                self.rholo_assets[config["asset_key"]] = record[1]
        asset = self.rholo_assets.get(config["asset_key"])
        if asset and (
            amount_rholo < asset.get("minDeposit", 0)
            or amount_rholo > asset.get("maxDeposit", amount_rholo)
        ):
            self.record_failure(
                deposit,
                f"rholo amount {amount_rholo} outside "
                f"[{asset.get('minDeposit')}, {asset.get('maxDeposit')}]",
            )
            return
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
            self.mark_deposit(deposit, "minted", message=message, signatures=signatures)
        elif result == (False, "replay"):
            self.mark_deposit(deposit, "minted", message=message, signatures=signatures)
        else:
            self.record_failure(deposit, repr(result))

    def mark_deposit(
        self,
        deposit: dict,
        state: str,
        message: str | None = None,
        signatures: list[str] | None = None,
    ) -> None:
        """Record a settled deposit with its block, so a later reorg can be detected."""
        deposit_id = deposit["deposit_id"]
        if deposit_id not in self.state["deposits"]:
            self.state["deposits"].append(deposit_id)
        self.state["deposit_blocks"][deposit_id] = {
            "block": deposit["block"],
            "block_hash": deposit.get("block_hash", ""),
            "tx": deposit["tx"],
            "amount_native": deposit.get("amount_native"),
            "token": deposit.get("token"),
            "state": state,
            "message": message,
            "signatures": signatures or [],
            "dry_run": self.dry_run,
        }
        self.save()

    def record_failure(self, deposit: dict, reason: str) -> None:
        failed = self.state.setdefault("failed_deposits", {})
        failed[deposit["deposit_id"]] = {
            "reason": reason,
            "amount_native": deposit["amount_native"],
            "token": deposit["token"],
            "sender": deposit["sender"],
            "tx": deposit["tx"],
            "block": deposit["block"],
            "block_hash": deposit.get("block_hash", ""),
            "recorded_at": int(time.time()),
        }
        self.save()
        print(
            f"FAILED deposit {deposit['deposit_id']}: {reason}; "
            "native funds are locked and need a refund path"
        )

    def scan_withdrawals(self) -> None:
        if self.state["halted"] or self.dry_run:
            return
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
                or asset_key not in self.token_for
                or not re.fullmatch(r"0x[0-9a-f]{40}", recipient)
            ):
                # The dev watcher only settles the Anvil ETH asset and well-formed
                # 20-byte destinations; other pending records are left to their rail.
                self.state["withdrawals"].append(withdrawal_id)
                self.state["withdrawals_detail"][withdrawal_id] = {
                    "withdrawal_id": withdrawal_id,
                    "state": "ignored",
                    "reason": "unsupported destination for the dev watcher",
                }
                self.save()
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
        token = self.token_for[asset_key]
        sig_array = "[" + ",".join("0x" + sig for sig in signatures) + "]"
        try:
            tx = cast_json(
                "send",
                self.vault,
                "unlock(address,address,uint256,string,uint256,bytes[])",
                token,
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
            self.state["withdrawals_detail"][withdrawal_id] = {
                "withdrawal_id": withdrawal_id,
                "state": "failed",
                "error": str(error),
            }
            self.save()
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
            self.state["withdrawals_detail"][withdrawal_id] = {
                "withdrawal_id": withdrawal_id,
                "state": "unlocked",
                "native_tx": native_tx,
            }
            self.save()

    def halted_reason(self) -> str | None:
        halted = self.state.get("halted")
        return halted.get("reason") if halted else None

    def run(self) -> None:
        print(f"dev relayer: vault={self.vault} bridge={self.bridge['uri'] or '(dry-run)'}")
        print(
            f"             start block={self.state['last_block']} interval={self.interval}s "
            f"confirmations={self.confirmations} finalized={self.finalized} "
            f"dry-run={self.dry_run}"
        )
        debug = bool(os.environ.get("RBRIDGE_RELAYER_DEBUG"))
        while True:
            if debug:
                print("loop top")
            reason = self.halted_reason()
            if reason:
                if not self._halted_reported:
                    print(f"relayer halted: {reason}")
                    print("reconcile, then rerun with --reset-state after fixing the cause")
                    self._halted_reported = True
                if self.http_server is None:
                    return
                # Keep /health and /metrics scrapeable while halted.
                time.sleep(self.interval)
                continue
            self._halted_reported = False
            try:
                self.scan_deposits()
                if debug:
                    print("deposits scanned")
                self.scan_withdrawals()
                if debug:
                    print("withdrawals scanned")
            except Exception as error:  # noqa: BLE001 - keep the dev loop alive
                print(f"relayer error: {error}")
            time.sleep(self.interval)
            if debug:
                print("woke")


def main() -> int:
    faulthandler.register(signal.SIGUSR1)
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--from-block", type=int, default=None)
    ap.add_argument("--state-file", type=Path, default=STATE_FILE)
    ap.add_argument("--vault", help="vault address (defaults to .devnet/evm.json)")
    ap.add_argument("--confirmations", type=int, default=0)
    ap.add_argument("--finalized", action="store_true")
    ap.add_argument("--reorg-window", type=int, default=128)
    ap.add_argument("--dry-run", action="store_true", help="scan and journal, do not mint/unlock")
    ap.add_argument("--once", action="store_true", help="scan once and exit")
    ap.add_argument("--reset-state", action="store_true")
    ap.add_argument("--metrics-port", type=int, default=None)
    ap.add_argument("--metrics-bind", default="127.0.0.1")
    args = ap.parse_args()

    if args.reset_state and args.state_file.exists():
        args.state_file.unlink()
        print(f"removed {args.state_file}")

    if args.dry_run:
        keys = {"deployer": {"secret": "00" * 32}, "relayers": [{"secret": "00" * 32}]}
        bridge = {"network": "dry-run", "bridge_id": "dry-run", "uri": ""}
        vault = args.vault
        if not vault:
            print("--dry-run needs --vault")
            return 2
    else:
        for path in (KEYS_FILE, BRIDGE_FILE, EVM_FILE):
            if not path.exists():
                print(f"missing {path}; run `make devnet-up && make demo && make e2e-evm` first")
                return 2
        keys = load_json(KEYS_FILE)
        bridge = load_json(BRIDGE_FILE)
        vault = args.vault or load_json(EVM_FILE)["vault"]

    relayer = Relayer(
        keys,
        bridge,
        vault,
        args.interval,
        args.from_block,
        state_path=args.state_file,
        dry_run=args.dry_run,
        confirmations=args.confirmations,
        finalized=args.finalized,
        reorg_window=args.reorg_window,
    )
    if args.once:
        relayer.scan_deposits()
        relayer.scan_withdrawals()
        reason = relayer.halted_reason()
        if reason:
            print(f"relayer halted: {reason}")
        return 0
    if args.metrics_port:
        relayer.start_http(args.metrics_port, args.metrics_bind)
        print(
            f"metrics: http://{args.metrics_bind}:{args.metrics_port}/metrics "
            f"(health on /health, chains on /v1/chains)"
        )
    relayer.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
