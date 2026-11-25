#!/usr/bin/env python3
"""r-bridge wired to the Hyperlane Mailbox: deposit, mint, burn, dispatch.

Devnet only. Installs `11_rbridge_hyperlane.rho` (the Bridge arms plus the Mailbox,
merkle hook, ISMs and Router), deposits through an inbound Hyperlane message, burns and
checks the outbound withdrawal dispatch, and exercises the refusals and the multisig path.
Uses the funded devnet deployer key and three throwaway validator keys.

Run `make devnet-up` first, then `make hyperlane-bridge-demo`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVNET = ROOT / ".devnet"
CONFIG = ROOT / "configs" / "hyperlane" / "devnet.json"
DEVNET_CONFIG = ROOT / "configs" / "devnet.json"

sys.path.insert(0, str(ROOT / "harness"))
import render  # noqa: E402
from hyperlane_demo import (  # noqa: E402
    CHECKS,
    FUNDED_KEY,
    call,
    cli,
    decode,
    deploy,
    expect,
    oracle,
)

ASSET = "ethereum.usdt"
REMOTE_DOMAIN = 11155111
REMOTE_CHAIN = "ethereum"


def main() -> int:
    config = json.loads(CONFIG.read_text())
    devnet = json.loads(DEVNET_CONFIG.read_text())
    local_domain = int(config["localDomain"])
    tree_id = str(config["treeId"])
    threshold = int(config["validatorThreshold"])
    peer = "00" * 31 + "cc"
    sender = "00" * 31 + "dd"

    deployer = cli("key-info", "--key", FUNDED_KEY)
    trusted = oracle("processor", "--pubkey", deployer["public"])["processor"]
    validators = [cli("keygen") for _ in range(3)]

    installed = deploy(
        render.render_hyperlane_bridge(
            network="rbridge-hyperlane-devnet",
            bridge_id="rbridge:hyperlane:devnet",
            treasury=deployer["rev_address"],
            admins=[deployer["public"]],
            admin_threshold=1,
            relayers=[deployer["public"]] + [validator["public"] for validator in validators],
            relayer_threshold=2,
            assets=devnet["assets"],
            local_domain=local_domain,
            sender_id=sender,
            trusted_relayer=trusted,
            ism_mode=str(config.get("ism", "test")),
            validators=[validator["public"] for validator in validators],
            threshold=threshold,
            tree_id=tree_id,
            by_domain={str(REMOTE_DOMAIN): peer},
            routes={REMOTE_CHAIN: {"domain": REMOTE_DOMAIN, "peer": peer}},
        ),
        "install_hyperlane_bridge.rho",
    )
    bridge, mailbox, ism, hook = decode((installed.get("deploy_result") or [])[0])
    (DEVNET / "hyperlane_bridge.json").write_text(
        json.dumps(
            {
                "bridge": bridge,
                "mailbox": mailbox,
                "ism": ism,
                "hook": hook,
                "localDomain": local_domain,
                "remoteDomain": REMOTE_DOMAIN,
                "peer": peer,
                "senderId": sender,
                "treeId": tree_id,
                "threshold": threshold,
                "validators": [validator["public"] for validator in validators],
            },
            indent=2,
        )
        + "\n"
    )
    print(f"installed bridge {bridge}")

    def bridge_call(body: str, name: str):
        return call(bridge, body, name)

    def mailbox_call(body: str, name: str):
        return call(mailbox, body, name)

    def deposit_payload(external_id: str, amount: int, nonce: int) -> str:
        return (
            f"rbridge:hyperlane:v1|deposit|{ASSET}|{amount}|"
            f"{deployer['rev_address']}|{external_id}|{nonce}"
        )

    def message(origin: int, message_sender: str, payload: str, nonce: int) -> dict:
        return oracle(
            "message",
            "--nonce",
            str(nonce),
            "--origin",
            str(origin),
            "--sender",
            message_sender,
            "--destination",
            str(local_domain),
            "--recipient",
            sender,
            "--body",
            payload,
        )

    def process(msg: str, name: str, metadata: str = ""):
        return mailbox_call(
            f'C!("process", "{metadata}".hexToBytes(), "{msg}".hexToBytes(), *ret)',
            name,
        )

    def balance() -> int:
        return bridge_call(
            f'C!("balanceOf", "{ASSET}", "{deployer["rev_address"]}", *ret)', "hb_balance.rho"
        )[1]

    # 1. Install and read the wired configuration.
    bridge_config = bridge_call('C!("config", *ret)', "hb_config.rho")
    expect("bridge network", bridge_config[1]["network"], "rbridge-hyperlane-devnet")
    expect("bridge not paused", bridge_config[1]["paused"], False)
    expect("initial balance", balance(), 0)

    # 2. Inbound deposit: 1 USDT, 5 bps fee.
    payload = deposit_payload("hyper-deposit-1", 1_000_000, 0)
    deposit = message(REMOTE_DOMAIN, peer, payload, 0)
    expect("deposit accepted", process(deposit["message"], "hb_deposit.rho"), (True, deposit["id"]))
    expect("deposit credited minus fee", balance(), 999_500)
    expect(
        "deposit delivered",
        mailbox_call(f'C!("delivered", "{deposit["id"]}", *ret)', "hb_delivered.rho"),
        True,
    )

    # 3. Refusals: wrong sender and bridge-level replay.
    wrong_sender = message(REMOTE_DOMAIN, "00" * 31 + "ee", deposit_payload("hyper-bad-1", 1_000_000, 1), 1)
    expect(
        "wrong sender refused",
        process(wrong_sender["message"], "hb_wrong_sender.rho"),
        (False, "recipient"),
    )
    expect(
        "wrong sender not delivered",
        mailbox_call(f'C!("delivered", "{wrong_sender["id"]}", *ret)', "hb_wrong_delivered.rho"),
        False,
    )
    replay = message(REMOTE_DOMAIN, peer, deposit_payload("hyper-deposit-1", 1_000_000, 2), 2)
    expect("replay refused", process(replay["message"], "hb_replay.rho"), (False, "recipient"))
    unknown = message(REMOTE_DOMAIN, peer, deposit_payload("hyper-deposit-x", 1_000_000, 3).replace(ASSET, "ethereum.unknown"), 3)
    expect("unknown asset refused", process(unknown["message"], "hb_unknown.rho"), (False, "recipient"))

    # 4. Burn records the withdrawal and dispatches the canonical payload.
    burn = bridge_call(
        f'C!("burn", "ethereum", "usdt", 500000, "{REMOTE_CHAIN}", "0x000000000000000000000000000000000000beef", "hyper-withdraw-1", *ret)',
        "hb_burn.rho",
    )
    expect("burn recorded", burn, (True, "hyper-withdraw-1"))
    withdrawal = bridge_call('C!("withdrawal", "hyper-withdraw-1", *ret)', "hb_withdrawal.rho")
    expect("withdrawal pending", withdrawal[1]["status"], "pending")
    message_id = withdrawal[1].get("dispatch")
    expect("dispatch message id is present", isinstance(message_id, str) and len(message_id) == 64, True)
    dispatched = mailbox_call(f'C!("dispatched", "{message_id}", *ret)', "hb_dispatched.rho")
    expect("dispatched bytes recorded", dispatched[0], True)
    parsed = oracle("parse-message", "--message", dispatched[1])
    expect("withdraw origin", parsed["origin"], local_domain)
    expect("withdraw destination", parsed["destination"], REMOTE_DOMAIN)
    expect("withdraw sender", parsed["sender"], sender)
    expect("withdraw recipient", parsed["recipient"], peer)
    expected_body = (
        "rbridge:hyperlane:v1|withdraw|ethereum.usdt|500000|"
        "0x000000000000000000000000000000000000beef|hyper-withdraw-1|0"
    )
    expect("withdraw body", parsed["body"], expected_body.encode().hex())
    expected_message = oracle(
        "message",
        "--nonce",
        "0",
        "--origin",
        str(local_domain),
        "--sender",
        sender,
        "--destination",
        str(REMOTE_DOMAIN),
        "--recipient",
        peer,
        "--body",
        expected_body,
    )
    expect("dispatch id matches the oracle", message_id, expected_message["id"])
    expect("balance after burn", balance(), 499_500)

    # 5. A burn with insufficient balance is refused.
    expect(
        "insufficient balance refused",
        bridge_call(
            f'C!("burn", "ethereum", "usdt", 999999999, "{REMOTE_CHAIN}", "0x000000000000000000000000000000000000beef", "hyper-withdraw-2", *ret)',
            "hb_burn_large.rho",
        ),
        (False, "insufficient balance"),
    )

    # 6. Multisig deposit: an unsigned message is refused; 2-of-3 is accepted.
    expect("switch to multisig", call(ism, 'C!("setMode", "multisig", *ret)', "hb_mode_multi.rho"), True)
    payload2 = deposit_payload("hyper-deposit-2", 2_000_000, 4)
    deposit2 = message(REMOTE_DOMAIN, peer, payload2, 4)
    expect("unsigned refused", process(deposit2["message"], "hb_multi_unsigned.rho"), (False, "ism"))
    root = "22" * 32
    digest = oracle(
        "checkpoint",
        "--origin",
        str(REMOTE_DOMAIN),
        "--merkle-tree",
        tree_id,
        "--root",
        root,
        "--index",
        "0",
        "--message-id",
        deposit2["id"],
    )["digest"]
    signatures = [
        cli("sign-digest-eth", "--key", validator["secret"], "--digest", digest)["signature"]
        for validator in validators[:2]
    ]
    metadata = tree_id + root + "00000000" + signatures[0] + signatures[1]
    expect(
        "multisig deposit accepted",
        process(deposit2["message"], "hb_multi_deposit.rho", metadata),
        (True, deposit2["id"]),
    )
    expect("balance after multisig deposit", balance(), 2_498_500)
    call(ism, 'C!("setMode", "test", *ret)', "hb_mode_test.rho")

    # 7. Pause fails new deposits closed; burns remain available.
    admin_payload = "rbridge:admin:v1|setPaused|true|1"
    admin_signature = cli("sign-text", "--key", FUNDED_KEY, "--text", admin_payload)["signature"]
    expect(
        "pause",
        bridge_call(
            f'C!("admin", "setPaused", "true", 1, ["{admin_signature}".hexToBytes()], *ret)',
            "hb_pause.rho",
        ),
        (True,),
    )
    paused = message(REMOTE_DOMAIN, peer, deposit_payload("hyper-deposit-3", 1_000_000, 5), 5)
    expect("paused deposit refused", process(paused["message"], "hb_paused.rho"), (False, "recipient"))
    unpause_payload = "rbridge:admin:v1|setPaused|false|2"
    unpause_signature = cli("sign-text", "--key", FUNDED_KEY, "--text", unpause_payload)["signature"]
    expect(
        "unpause",
        bridge_call(
            f'C!("admin", "setPaused", "false", 2, ["{unpause_signature}".hexToBytes()], *ret)',
            "hb_unpause.rho",
        ),
        (True,),
    )

    # 8. Conservation: deposits = balance + fees + burned.
    fees = bridge_call(f'C!("fees", "{ASSET}", *ret)', "hb_fees.rho")[1]
    expect("bridge fees", fees, 1_500)
    expect("conservation", balance() + fees + 500_000, 3_000_000)

    passed = sum(CHECKS)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
