#!/usr/bin/env python3
"""End-to-end r-bridge demo on a local rholo devnet.

This is the rail-agnostic demo: it installs the bridge suite, signs attestations with a
mock 2-of-3 relayer set, mints/burns/transfers, and exercises replay, threshold, pause
and conservation. It uses the Rust CLI for signing and deploys; no native-chain RPC is
involved yet.

Devnet only. The keys are generated into .devnet/demo-keys.json (gitignored) and are
worth nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVNET = ROOT / ".devnet"
RENDERED = DEVNET / "rendered"
KEYS_FILE = DEVNET / "demo-keys.json"
NODE = "http://localhost:40403"
# The devnet's funded deployer key (throwaway; tools/devnet.sh validator 0).
FUNDED_KEY = "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76"
NETWORK = "rbridge-devnet"
BRIDGE_ID = "rbridge:devnet:bridge"
ASSET_KEY = "ethereum.usdt"
CHAIN = "ethereum"
ASSET_ID = "usdt"

sys.path.insert(0, str(ROOT / "harness"))
import render  # noqa: E402


def cli(*args: str) -> dict:
    binary = ROOT / "target" / "debug" / "rbridge"
    if not binary.is_file():
        subprocess.run(["cargo", "build", "-p", "rbridge-cli"], cwd=ROOT, check=True)
    result = subprocess.run(
        [str(binary), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rbridge {' '.join(args)} failed:\n{result.stderr}{result.stdout}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"rbridge {' '.join(args)} printed nothing")
    return json.loads(lines[-1])


def keygen() -> dict:
    return cli("keygen")


def keyinfo(secret: str) -> dict:
    return cli("key-info", "--key", secret)


def sign_text(secret: str, text: str) -> dict:
    return cli("sign-text", "--key", secret, "--text", text)


def decode(value):
    if isinstance(value, dict):
        if "ExprInt" in value:
            return value["ExprInt"]["data"]
        if "ExprString" in value:
            return value["ExprString"]["data"]
        if "ExprUri" in value:
            return value["ExprUri"]["data"]
        if "ExprBool" in value:
            return value["ExprBool"]["data"]
        if "ExprNil" in value:
            return None
        if "ExprList" in value:
            return [decode(item) for item in value["ExprList"]["data"]]
        if "ExprTuple" in value:
            return tuple(decode(item) for item in value["ExprTuple"]["data"])
        if "ExprMap" in value:
            data = value["ExprMap"]["data"]
            if isinstance(data, dict):
                return {key: decode(item) for key, item in data.items()}
            return {decode(key): decode(item) for key, item in data}
        if "ExprBytes" in value:
            return bytes.fromhex(value["ExprBytes"]["data"])
        return value
    return value


def write_term(name: str, term: str) -> Path:
    RENDERED.mkdir(parents=True, exist_ok=True)
    path = RENDERED / name
    path.write_text(term)
    return path


def deploy(term: str, secret: str, name: str) -> dict:
    path = write_term(name, term)
    return cli(
        "deploy",
        "--node",
        NODE,
        "--key",
        secret,
        "--term-file",
        str(path),
        "--timeout-secs",
        "90",
    )


def explore(term: str, name: str):
    path = write_term(name, term)
    return cli("explore", "--node", NODE, "--term-file", str(path))


def lookup(uri: str, body: str, reply_on_deploy_id: bool) -> str:
    ret = "ret(`rho:rchain:deployId`)" if reply_on_deploy_id else "ret"
    return (
        "new rl(`rho:registry:lookup`), ch, " + ret + " in {\n"
        f"  rl!(`{uri}`, *ch) |\n"
        "  for (Bridge <- ch) {\n"
        f"    {body}\n"
        "  }\n"
        "}\n"
    )


DEPLOY_SECRET = ""


def call_read(uri: str, body: str, name: str):
    # Reads are deploys: the reply is returned on `rho:rchain:deployId`. Explore-deploy
    # reports the first private name, which is the registry lookup channel, not the reply.
    response = deploy(lookup(uri, body, True), DEPLOY_SECRET, name)
    result = response.get("deploy_result") or []
    if not result:
        raise RuntimeError(f"read {name} returned no result: {response}")
    return decode(result[0])


def call_write(uri: str, body: str, secret: str, name: str):
    response = deploy(lookup(uri, body, True), secret, name)
    result = response.get("deploy_result") or []
    if not result:
        raise RuntimeError(f"write {name} returned no result: {response}")
    return decode(result[0])


def signature_literals(signatures: list[str]) -> str:
    return ", ".join(f'"{sig}".hexToBytes()' for sig in signatures)


def canonical(tx: str, amount: int, recipient: str, nonce: int) -> str:
    return (
        f"rbridge:v1|{NETWORK}|{CHAIN}|{BRIDGE_ID}|{ASSET_KEY}|deposit|"
        f"{tx}|{amount}|{recipient}|{nonce}"
    )


def expect(label: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {actual!r}")
    if not ok:
        print(f"      expected: {expected!r}")
    return ok


def main() -> int:
    global DEPLOY_SECRET
    DEVNET.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / "configs" / "devnet.json").read_text())

    if KEYS_FILE.exists():
        keys = json.loads(KEYS_FILE.read_text())
    else:
        deployer = keyinfo(FUNDED_KEY)
        admins = [keygen() for _ in range(3)]
        relayers = [keygen() for _ in range(2)]
        user = keygen()
        keys = {
            "deployer": {"secret": FUNDED_KEY, **deployer},
            "admins": admins,
            "relayers": relayers,
            "user": user,
        }
        KEYS_FILE.write_text(json.dumps(keys, indent=2))
        KEYS_FILE.chmod(0o600)

    deployer = keys["deployer"]
    admins = keys["admins"]
    relayers = keys["relayers"]
    user = keys["user"]
    DEPLOY_SECRET = deployer["secret"]

    # The deployer is relayer 0 so the funded account can complete a withdrawal. The
    # other two are independent dev keys; the threshold is 2.
    relayer_keys = [deployer["public"]] + [relayer["public"] for relayer in relayers]
    relayer_secrets = [deployer["secret"]] + [relayer["secret"] for relayer in relayers]

    term = render.render(
        network=NETWORK,
        bridge_id=BRIDGE_ID,
        admins=[admin["public"] for admin in admins],
        admin_threshold=2,
        relayers=relayer_keys,
        relayer_threshold=2,
        assets=config["assets"],
    )
    installed = deploy(term, deployer["secret"], "install_bridge.rho")
    result = installed.get("deploy_result") or []
    if not result:
        print("FAIL  install produced no result", installed)
        return 1
    uri = decode(result[0])[0]
    (DEVNET / "bridge.json").write_text(
        json.dumps({"uri": uri, "network": NETWORK, "bridge_id": BRIDGE_ID}, indent=2)
    )
    print(f"bridge uri: {uri}")

    passed = True
    recipient = deployer["rev_address"]

    # 1. Config and asset registry.
    config_read = call_read(uri, 'Bridge!("config", *ret)', "read_config.rho")
    passed &= expect("config is a pair", config_read[0], True)
    passed &= expect("network", config_read[1]["network"], NETWORK)
    passed &= expect("bridge id", config_read[1]["bridgeId"], BRIDGE_ID)
    passed &= expect("relayer threshold", config_read[1]["relayerThreshold"], 2)
    asset = call_read(uri, f'Bridge!("asset", "{ASSET_KEY}", *ret)', "read_asset.rho")
    passed &= expect("asset enabled", asset[1]["enabled"], True)

    # 2. Valid mint: 1 USDT, 5 bps fee, 2-of-3.
    tx1 = "demo-deposit-1"
    sigs = [sign_text(secret, canonical(tx1, 1_000_000, recipient, 0))["signature"] for secret in relayer_secrets[:2]]
    mint = call_write(
        uri,
        f'Bridge!("mint", "{CHAIN}", "{ASSET_ID}", "{tx1}", 1000000, "{recipient}", 0, [{signature_literals(sigs)}], *ret)',
        deployer["secret"],
        "mint_1.rho",
    )
    passed &= expect("mint credited (amount - fee)", mint, (True, 999_500))
    balance = call_read(uri, f'Bridge!("balanceOf", "{ASSET_KEY}", "{recipient}", *ret)', "balance_1.rho")
    passed &= expect("balance after mint", balance, (True, 999_500))
    fees = call_read(uri, f'Bridge!("fees", "{ASSET_KEY}", *ret)', "fees_1.rho")
    passed &= expect("deposit fee", fees, (True, 500))

    # 3. Replay, below threshold, unknown asset.
    replay = call_write(
        uri,
        f'Bridge!("mint", "{CHAIN}", "{ASSET_ID}", "{tx1}", 1000000, "{recipient}", 0, [{signature_literals(sigs)}], *ret)',
        deployer["secret"],
        "mint_replay.rho",
    )
    passed &= expect("replay refused", replay, (False, "replay"))
    tx2 = "demo-deposit-2"
    one_sig = [sign_text(relayer_secrets[0], canonical(tx2, 1_000_000, recipient, 0))["signature"]]
    below = call_write(
        uri,
        f'Bridge!("mint", "{CHAIN}", "{ASSET_ID}", "{tx2}", 1000000, "{recipient}", 0, [{signature_literals(one_sig)}], *ret)',
        deployer["secret"],
        "mint_below_threshold.rho",
    )
    passed &= expect("below threshold refused", below, (False, "below threshold"))
    unknown = call_write(
        uri,
        f'Bridge!("mint", "ethereum", "dai", "demo-dai", 1000000, "{recipient}", 0, [{signature_literals(sigs)}], *ret)',
        deployer["secret"],
        "mint_unknown_asset.rho",
    )
    passed &= expect("unknown asset refused", unknown, (False, "unknown asset"))

    # 4. Burn 0.4 USDT and complete the withdrawal as relayer 0.
    withdrawal_id = "demo-withdrawal-1"
    burn = call_write(
        uri,
        f'Bridge!("burn", "{CHAIN}", "{ASSET_ID}", 400000, "ethereum", "0xuser", "{withdrawal_id}", *ret)',
        deployer["secret"],
        "burn_1.rho",
    )
    passed &= expect("burn recorded", burn, (True, withdrawal_id))
    withdrawal = call_read(uri, f'Bridge!("withdrawal", "{withdrawal_id}", *ret)', "read_withdrawal.rho")
    passed &= expect("withdrawal pending", withdrawal[1]["status"], "pending")
    passed &= expect("withdrawal fee", withdrawal[1]["fee"], 200)
    complete = call_write(
        uri,
        f'Bridge!("completeWithdrawal", "{withdrawal_id}", "0xnative", *ret)',
        deployer["secret"],
        "complete_withdrawal.rho",
    )
    passed &= expect("withdrawal completed", complete, (True,))

    # 5. Transfer to a second account.
    to = user["rev_address"]
    transfer = call_write(
        uri,
        f'Bridge!("transfer", "{ASSET_KEY}", "{to}", 100000, *ret)',
        deployer["secret"],
        "transfer_1.rho",
    )
    passed &= expect("transfer", transfer, (True,))
    to_balance = call_read(uri, f'Bridge!("balanceOf", "{ASSET_KEY}", "{to}", *ret)', "balance_to.rho")
    passed &= expect("recipient balance", to_balance, (True, 100_000))

    # 6. Pause is 2-of-3, blocks mint, does not block burn.
    pause_text = "rbridge:admin:v1|setPaused|true|1"
    pause_sigs = [sign_text(admin["secret"], pause_text)["signature"] for admin in admins[:2]]
    pause = call_write(
        uri,
        f'Bridge!("admin", "setPaused", "true", 1, [{signature_literals(pause_sigs)}], *ret)',
        deployer["secret"],
        "pause.rho",
    )
    passed &= expect("pause", pause, (True,))
    paused_mint = call_write(
        uri,
        f'Bridge!("mint", "{CHAIN}", "{ASSET_ID}", "demo-deposit-3", 1000000, "{recipient}", 0, [{signature_literals(sigs)}], *ret)',
        deployer["secret"],
        "mint_paused.rho",
    )
    passed &= expect("mint while paused refused", paused_mint, (False, "paused"))
    paused_burn = call_write(
        uri,
        f'Bridge!("burn", "{CHAIN}", "{ASSET_ID}", 1, "ethereum", "0xuser", "demo-withdrawal-2", *ret)',
        deployer["secret"],
        "burn_paused.rho",
    )
    passed &= expect("burn while paused allowed", paused_burn, (True, "demo-withdrawal-2"))
    unpause_text = "rbridge:admin:v1|setPaused|false|2"
    unpause_sigs = [sign_text(admin["secret"], unpause_text)["signature"] for admin in admins[:2]]
    unpause = call_write(
        uri,
        f'Bridge!("admin", "setPaused", "false", 2, [{signature_literals(unpause_sigs)}], *ret)',
        deployer["secret"],
        "unpause.rho",
    )
    passed &= expect("unpause", unpause, (True,))

    # 7. Conservation: minted 1,000,000 = circulating + fees + burned.
    owner_balance = call_read(uri, f'Bridge!("balanceOf", "{ASSET_KEY}", "{recipient}", *ret)', "balance_final_owner.rho")[1]
    user_balance = call_read(uri, f'Bridge!("balanceOf", "{ASSET_KEY}", "{to}", *ret)', "balance_final_user.rho")[1]
    fee_balance = call_read(uri, f'Bridge!("fees", "{ASSET_KEY}", *ret)', "fees_final.rho")[1]
    burned = 400_000 + 1
    circulating = owner_balance + user_balance
    passed &= expect("conservation", circulating + fee_balance + burned, 1_000_000)

    print()
    print("demo:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
