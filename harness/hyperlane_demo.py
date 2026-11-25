#!/usr/bin/env python3
"""Hyperlane v3 on rholo: install, dispatch, process and refuse.

Devnet only. This is Phase 2 of the Hyperlane suite: the Mailbox public surface, the
capability-gated dispatch door, the no-op hook, the switchable test ISM and a recipient
that records what it was handed. It uses the funded devnet deployer key as the relayer;
the key is throwaway and worth nothing.

Run `make demo` first so the devnet and the CLI are built, then `make hyperlane-demo`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVNET = ROOT / ".devnet"
RENDERED = DEVNET / "rendered"
CONFIG = ROOT / "configs" / "hyperlane" / "devnet.json"
NODE = "http://localhost:40403"
# The devnet's funded deployer key (throwaway; tools/devnet.sh validator 0).
FUNDED_KEY = "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76"
ASSET = "ethereum.usdt"
PAYLOAD = "rbridge:hyperlane:v1|deposit|ethereum.usdt|1000000|rho:id:recipient|0xabc:0|7"
CHECKPOINT = "a4411138366886244ae59b3f44587dc9f12edd373b6c0603f8909e3785e3d963"

sys.path.insert(0, str(ROOT / "harness"))
import render  # noqa: E402
from demo import decode  # noqa: E402

CHECKS: list[bool] = []


def cli(*args: str) -> dict:
    binary = ROOT / "target" / "debug" / "rbridge"
    if not binary.is_file():
        subprocess.run(["cargo", "build", "-p", "rbridge-cli"], cwd=ROOT, check=True)
    result = subprocess.run([str(binary), *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"rbridge {' '.join(args)} failed:\n{result.stderr}{result.stdout}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"rbridge {' '.join(args)} printed nothing")
    return json.loads(lines[-1])


def deploy(term: str, name: str) -> dict:
    RENDERED.mkdir(parents=True, exist_ok=True)
    path = RENDERED / name
    path.write_text(term)
    return cli(
        "deploy",
        "--node",
        NODE,
        "--key",
        FUNDED_KEY,
        "--term-file",
        str(path),
        "--timeout-secs",
        "120",
    )


def call(uri: str, body: str, name: str):
    term = (
        "new rl(`rho:registry:lookup`), ch, ret(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{uri}`, *ch) |\n"
        f"  for (C <- ch) {{ {body} }}\n"
        "}\n"
    )
    response = deploy(term, name)
    result = response.get("deploy_result") or []
    if not result:
        raise RuntimeError(f"{name} returned no result: {response}")
    return decode(result[0])


def oracle(*args: str) -> dict:
    return cli("hyperlane", *args)


def expect(label: str, actual, expected) -> None:
    ok = actual == expected
    CHECKS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {actual!r}")
    if not ok:
        print(f"      expected: {expected!r}")


def main() -> int:
    config = json.loads(CONFIG.read_text())
    local_domain = int(config["localDomain"])
    sender = str(config["senderId"])
    recipient = str(config["recipientId"])
    remote_domain = int(config["remoteDomain"])

    public = cli("key-info", "--key", FUNDED_KEY)["public"]
    trusted = oracle("processor", "--pubkey", public)["processor"]
    validators = [cli("keygen") for _ in range(3)]
    threshold = int(config["validatorThreshold"])
    tree_id = str(config["treeId"])

    installed = deploy(
        render.render_hyperlane(
            local_domain,
            sender,
            trusted,
            str(config.get("ism", "test")),
            validators=[validator["public"] for validator in validators],
            threshold=threshold,
            tree_id=tree_id,
        ),
        "install_hyperlane.rho",
    )
    uris = decode((installed.get("deploy_result") or [])[0])
    mailbox, door, ism, hook, mock = uris
    (DEVNET / "hyperlane.json").write_text(
        json.dumps(
            {
                "config": config,
                "mailbox": mailbox,
                "dispatchDoor": door,
                "ism": ism,
                "hook": hook,
                "recipient": mock,
                "trustedRelayer": trusted,
                "validators": [validator["public"] for validator in validators],
                "threshold": threshold,
                "treeId": tree_id,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"installed mailbox {mailbox}")

    payload = oracle(
        "payload",
        "--action",
        "deposit",
        "--asset",
        ASSET,
        "--amount",
        "1000000",
        "--recipient",
        "rho:id:recipient",
        "--external-id",
        "0xabc:0",
        "--nonce",
        "7",
    )
    expect("payload canonical", payload["canonical"], PAYLOAD)
    expect("payload keccak", payload["body"], PAYLOAD.encode().hex())

    def build(nonce: int, destination: int) -> dict:
        return oracle(
            "message",
            "--nonce",
            str(nonce),
            "--origin",
            str(local_domain),
            "--sender",
            sender,
            "--destination",
            str(destination),
            "--recipient",
            recipient,
            "--body",
            PAYLOAD,
        )

    def dispatch(destination: int, name: str):
        return call(
            door,
            f'C!("dispatch", {destination}, "{recipient}".hexToBytes(), '
            f'"{PAYLOAD}".toUtf8Bytes(), "".hexToBytes(), *ret)',
            name,
        )

    def process(message: str, name: str, metadata: str = ""):
        return call(
            mailbox,
            f'C!("process", "{metadata}".hexToBytes(), '
            f'"{message}".hexToBytes(), *ret)',
            name,
        )

    def nonce() -> int:
        return call(mailbox, 'C!("nonce", *ret)', "hl_nonce.rho")

    def recipient_state(name: str = "hl_recipient.rho"):
        return call(mock, 'C!("state", *ret)', name)

    # 1. The Mailbox starts empty.
    expect("local domain", call(mailbox, 'C!("localDomain", *ret)', "hl_domain.rho"), local_domain)
    expect("nonce starts at 0", nonce(), 0)

    # 2. Dispatch a self-addressed message; the oracle predicts its id.
    message = build(0, local_domain)
    expect("dispatch id", dispatch(local_domain, "hl_dispatch.rho"), (True, message["id"]))
    expect("nonce after dispatch", nonce(), 1)
    expect(
        "latest dispatched id",
        call(mailbox, 'C!("latestDispatchedId", *ret)', "hl_latest.rho"),
        message["id"],
    )
    expect(
        "dispatched bytes",
        call(mailbox, f'C!("dispatched", "{message["id"]}", *ret)', "hl_dispatched.rho"),
        (True, message["message"]),
    )
    expect("hook latest", call(hook, 'C!("latest", *ret)', "hl_hook.rho"), message["id"])
    expect("hook tree id", call(hook, 'C!("treeId", *ret)', "hl_tree.rho"), tree_id)
    expect("hook count", call(hook, 'C!("count", *ret)', "hl_count.rho"), 1)
    hook_root = call(hook, 'C!("root", *ret)', "hl_root.rho")
    latest_checkpoint = call(hook, 'C!("latestCheckpoint", *ret)', "hl_checkpoint.rho")
    expect("checkpoint root", latest_checkpoint[0], hook_root)
    expect("checkpoint index", latest_checkpoint[1], 0)

    # 3. Process it; the recipient records the hand-off.
    expect("process", process(message["message"], "hl_process.rho"), (True, message["id"]))
    expect(
        "delivered",
        call(mailbox, f'C!("delivered", "{message["id"]}", *ret)', "hl_delivered.rho"),
        True,
    )
    expect(
        "processor",
        call(mailbox, f'C!("processor", "{message["id"]}", *ret)', "hl_processor.rho"),
        trusted,
    )
    expect(
        "processedAt is a block number",
        call(mailbox, f'C!("processedAt", "{message["id"]}", *ret)', "hl_processed.rho") > 0,
        True,
    )
    state = recipient_state()
    expect("recipient count", state["count"], 1)
    expect("recipient origin", state["lastOrigin"], local_domain)
    expect("recipient sender", state["lastSender"], sender)
    expect("recipient body", state["lastBody"], PAYLOAD.encode().hex())
    expect("replay refused", process(message["message"], "hl_replay.rho"), (False, "already delivered"))

    # 4. A message for another domain is refused and not delivered.
    remote = build(nonce(), remote_domain)
    expect("remote dispatch", dispatch(remote_domain, "hl_dispatch_remote.rho"), (True, remote["id"]))
    expect(
        "wrong destination refused",
        process(remote["message"], "hl_process_remote.rho"),
        (False, "destination"),
    )
    expect("recipient count unchanged", recipient_state("hl_recipient2.rho")["count"], 1)

    # 5. A wrong version is refused.
    local = build(nonce(), local_domain)
    expect("local dispatch", dispatch(local_domain, "hl_dispatch_local.rho"), (True, local["id"]))
    expect(
        "wrong version refused",
        process("02" + local["message"][2:], "hl_process_version.rho"),
        (False, "version"),
    )

    # 6. An ISM refusal leaves no delivery; then the switch is restored.
    expect("ism off", call(ism, 'C!("setAccept", false, *ret)', "hl_ism_off.rho"), True)
    refused = build(nonce(), local_domain)
    expect("ism-off dispatch", dispatch(local_domain, "hl_dispatch_ism.rho"), (True, refused["id"]))
    expect("ism refused", process(refused["message"], "hl_process_ism.rho"), (False, "ism"))
    expect(
        "refused delivery not recorded",
        call(mailbox, f'C!("delivered", "{refused["id"]}", *ret)', "hl_refused.rho"),
        False,
    )
    expect("ism on", call(ism, 'C!("setAccept", true, *ret)', "hl_ism_on.rho"), True)
    expect("recipient count still 1", recipient_state("hl_recipient3.rho")["count"], 1)

    # 7. TrustedRelayerISM: the same Mailbox, a different module.
    expect(
        "switch to trusted",
        call(ism, 'C!("setMode", "trusted", *ret)', "hl_mode_trusted.rho"),
        True,
    )
    expect("module mode", call(ism, 'C!("mode", *ret)', "hl_mode_read.rho"), "trusted")
    expect(
        "module type is NULL",
        call(ism, 'C!("moduleType", *ret)', "hl_module_type.rho"),
        6,
    )
    trusted_message = build(nonce(), local_domain)
    expect(
        "trusted dispatch",
        dispatch(local_domain, "hl_dispatch_trusted.rho"),
        (True, trusted_message["id"]),
    )
    expect(
        "trusted relayer accepts",
        process(trusted_message["message"], "hl_process_trusted.rho"),
        (True, trusted_message["id"]),
    )
    expect("recipient count after trusted", recipient_state("hl_recipient_trusted.rho")["count"], 2)
    expect(
        "set wrong trusted relayer",
        call(ism, 'C!("setTrustedRelayer", "00", *ret)', "hl_trusted_wrong.rho"),
        True,
    )
    refused_message = build(nonce(), local_domain)
    expect(
        "refused dispatch",
        dispatch(local_domain, "hl_dispatch_trusted_refused.rho"),
        (True, refused_message["id"]),
    )
    expect(
        "wrong processor refused",
        process(refused_message["message"], "hl_process_trusted_refused.rho"),
        (False, "ism"),
    )
    expect(
        "recipient count unchanged",
        recipient_state("hl_recipient_trusted2.rho")["count"],
        2,
    )
    call(ism, f'C!("setTrustedRelayer", "{trusted}", *ret)', "hl_trusted_restore.rho")
    call(ism, 'C!("setMode", "test", *ret)', "hl_mode_test.rho")

    # 8. MessageIdMultisigISM: 2-of-3 validator signatures over a checkpoint.
    def sign_checkpoint(message_id: str, root: str, index: int, secret: str) -> str:
        digest = oracle(
            "checkpoint",
            "--origin",
            str(local_domain),
            "--merkle-tree",
            tree_id,
            "--root",
            root,
            "--index",
            str(index),
            "--message-id",
            message_id,
        )["digest"]
        return cli("sign-digest-eth", "--key", secret, "--digest", digest)["signature"]

    expect(
        "switch to multisig",
        call(ism, 'C!("setMode", "multisig", *ret)', "hl_mode_multisig.rho"),
        True,
    )
    expect("module type is MULTISIG", call(ism, 'C!("moduleType", *ret)', "hl_type_multi.rho"), 5)

    accepted = build(nonce(), local_domain)
    expect(
        "multisig dispatch",
        dispatch(local_domain, "hl_dispatch_multisig.rho"),
        (True, accepted["id"]),
    )
    checkpoint_a = call(hook, 'C!("latestCheckpoint", *ret)', "hl_cp_multi.rho")
    root_a, index_a = checkpoint_a[0], checkpoint_a[1]
    sig_a = [
        sign_checkpoint(accepted["id"], root_a, index_a, validator["secret"])
        for validator in validators
    ]
    metadata_a = tree_id + root_a + f"{index_a:08x}" + sig_a[0] + sig_a[1]
    expect(
        "2-of-3 accepted",
        process(accepted["message"], "hl_process_multisig.rho", metadata_a),
        (True, accepted["id"]),
    )
    expect("recipient count after multisig", recipient_state("hl_recipient_multi.rho")["count"], 3)

    refused = build(nonce(), local_domain)
    expect(
        "refusal dispatch",
        dispatch(local_domain, "hl_dispatch_multisig_refused.rho"),
        (True, refused["id"]),
    )
    checkpoint_b = call(hook, 'C!("latestCheckpoint", *ret)', "hl_cp_multi_refused.rho")
    root_b, index_b = checkpoint_b[0], checkpoint_b[1]
    sig_b = [
        sign_checkpoint(refused["id"], root_b, index_b, validator["secret"])
        for validator in validators
    ]
    base_b = tree_id + root_b + f"{index_b:08x}"
    expect(
        "below threshold refused",
        process(refused["message"], "hl_multisig_below.rho", base_b + sig_b[0]),
        (False, "ism"),
    )
    expect(
        "duplicate signer refused",
        process(refused["message"], "hl_multisig_duplicate.rho", base_b + sig_b[0] + sig_b[0]),
        (False, "ism"),
    )
    expect(
        "wrong root refused",
        process(
            refused["message"],
            "hl_multisig_root.rho",
            tree_id + ("00" * 32) + f"{index_b:08x}" + sig_b[0] + sig_b[1],
        ),
        (False, "ism"),
    )
    expect(
        "truncated metadata refused",
        process(refused["message"], "hl_multisig_truncated.rho", base_b + sig_b[0] + "00"),
        (False, "ism"),
    )
    expect(
        "valid metadata after refusals",
        process(refused["message"], "hl_multisig_valid.rho", base_b + sig_b[0] + sig_b[1]),
        (True, refused["id"]),
    )
    expect("recipient count after multisig", recipient_state("hl_recipient_multi2.rho")["count"], 4)
    call(ism, 'C!("setMode", "test", *ret)', "hl_mode_test2.rho")

    # 9. The Rust oracle pins the Hyperlane checkpoint digest.
    checkpoint = oracle(
        "checkpoint",
        "--origin",
        "11155111",
        "--merkle-tree",
        "11" * 32,
        "--root",
        "22" * 32,
        "--index",
        "3",
        "--message-id",
        "f44504e00b9ef65496c962d2c682804f0ec047ee58f0b3cd30c6b116895e04e9",
    )
    expect("checkpoint golden", checkpoint["digest"], CHECKPOINT)

    parsed = oracle("parse-message", "--message", message["message"])
    expect("parsed origin", parsed["origin"], local_domain)
    expect("parsed body", parsed["body"], PAYLOAD.encode().hex())
    metadata = ("11" * 32) + ("22" * 32) + "00000003" + ("33" * 65) + ("44" * 65)
    parsed_metadata = oracle("parse-metadata", "--metadata", metadata)
    expect("metadata signature count", parsed_metadata["signature_count"], 2)

    passed = sum(CHECKS)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
