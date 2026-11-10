#!/usr/bin/env python3
"""Admin refund for deposits the dev relayer journaled as failed.

A deposit that locked native funds but could not mint on rholo (for example because it
was below the rholo minimum) is recorded in .devnet/relayer_state.json under
`failed_deposits`. This script signs the vault's 2-of-3 admin refund payload with the
demo admin keys and returns the locked native funds to the depositor.

Devnet only. In production the admin set would be a governed multisig and the refund
would be an operator runbook, not a fixed-key script.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVNET = ROOT / ".devnet"
KEYS_FILE = DEVNET / "demo-keys.json"
EVM_FILE = DEVNET / "evm.json"
STATE_FILE = DEVNET / "relayer_state.json"

sys.path.insert(0, str(ROOT / "harness"))
import demo  # noqa: E402
from e2e_evm import ANVIL_KEY, ANVIL_RPC, cast_json  # noqa: E402


def main() -> int:
    for path in (KEYS_FILE, EVM_FILE, STATE_FILE):
        if not path.exists():
            print(f"missing {path}; run the demo/e2e first")
            return 2
    keys = json.loads(KEYS_FILE.read_text())
    vault = json.loads(EVM_FILE.read_text())["vault"]
    state = json.loads(STATE_FILE.read_text())
    failed = state.get("failed_deposits", {})
    if not failed:
        print("no failed deposits")
        return 0

    admin_secrets = [admin["secret"] for admin in keys["admins"][:2]]
    refunded = 0
    for deposit_id, record in failed.items():
        if record.get("refunded"):
            continue
        token = record.get("token")
        sender = record.get("sender")
        amount = record.get("amount_native")
        if not token or not sender or not amount:
            print(f"skip {deposit_id}: record has no token/sender (older journal entry)")
            continue
        nonce = time.time_ns()
        message = (
            f"rbridge:admin:v1|refund|{token.lower()}|{sender.lower()}|{amount}|"
            f"{deposit_id}|{nonce}"
        )
        signatures = [
            demo.cli("sign-text-eth", "--key", secret, "--text", message)["signature"]
            for secret in admin_secrets
        ]
        tx = cast_json(
            "send",
            vault,
            "refund(address,address,uint256,string,uint256,bytes[])",
            token,
            sender,
            str(amount),
            deposit_id,
            str(nonce),
            "[" + ",".join("0x" + sig for sig in signatures) + "]",
            "--private-key",
            ANVIL_KEY,
            "--rpc-url",
            ANVIL_RPC,
        )
        record["refunded"] = tx["transactionHash"]
        STATE_FILE.write_text(json.dumps(state, indent=2))
        refunded += 1
        print(f"refunded {deposit_id}: {amount} of {token} to {sender} ({tx['transactionHash']})")

    print(f"refund-failed: {refunded} refund(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
