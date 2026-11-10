#!/usr/bin/env python3
"""Deploy and verify a BridgeVault from a network profile.

A profile (`configs/networks/*.json`) is the single source of truth for a deployment:
chain id, rholo network id, bridge id, admin/relayer sets and thresholds, treasury, and
the asset registry. Addresses and the RPC URL may be `${ENV_VAR}` references, so operator
addresses and endpoints never enter git. The deployer key is always read from an
environment variable and is never written to a manifest or printed.

`deploy` refuses mainnet, refuses a chain id that does not match the profile, checks that
every ERC-20 has code and the declared decimals, broadcasts through
`contracts/evm/script/DeployVault.s.sol`, reads the deployed configuration back from the
chain, compares it with the profile, and only then writes the manifest to
`deployments/<network>.json` (gitignored).

`verify` re-reads a manifest against the chain, so a drift or a hand-edited manifest is
detected. `plan` prints the deployment without a key or an RPC, for review.
`print-env` turns a manifest into the web app's environment variables.

Devnet keys are throwaway. No mainnet deployment before the external audit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EVM = ROOT / "contracts" / "evm"
DEPLOYMENTS = ROOT / "deployments"
ZERO = "0x0000000000000000000000000000000000000000"
SCHEMA = "rbridge.deployment.v1"
MAINNET_CHAIN_IDS = {1, 728126428}  # Ethereum, Tron mainnet
LOCAL_CHAIN_IDS = {31337, 1337}
ENV_REF = re.compile(r"\$\{([A-Z0-9_]+)\}")
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
UINT = re.compile(r"^[0-9]+$")


class ConfigError(RuntimeError):
    """The profile, environment or chain data is unusable. Exit 2."""


class Refused(RuntimeError):
    """A safety gate refused the deployment. Exit 3."""


class VerifyError(RuntimeError):
    """The deployed configuration does not match the expected one. Exit 1."""


def find_bin(name: str, env_name: str) -> Path:
    override = os.environ.get(env_name)
    if override:
        path = Path(override)
        if not path.exists():
            raise ConfigError(f"{env_name}={override} does not exist")
        return path
    found = shutil.which(name)
    if found:
        return Path(found)
    candidate = Path.home() / ".foundry" / "bin" / name
    if candidate.exists():
        return candidate
    raise ConfigError(f"{name} not found; install Foundry or set {env_name}")


FORGE = None
CAST = None


def tools() -> tuple[Path, Path]:
    global FORGE, CAST
    if FORGE is None:
        FORGE = find_bin("forge", "FORGE")
        CAST = find_bin("cast", "CAST")
    return FORGE, CAST


def run(args: list[str], *, timeout: int = 900, **kwargs: Any) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kwargs)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{' '.join(args[:3])} failed:\n{detail}")
    return result


def rpc(url: str, method: str, params: list | None = None) -> Any:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    ).encode()
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if "error" in body:
        raise ConfigError(f"{method} failed: {body['error']}")
    return body.get("result")


def cast_json(
    address: str, signature: str, *args: str, rpc_url: str, block: str = "latest"
) -> Any:
    _, cast = tools()
    result = run(
        [
            str(cast),
            "call",
            address,
            signature,
            *args,
            "--block",
            block,
            "--rpc-url",
            rpc_url,
            "--json",
        ]
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as caught:
        raise VerifyError(f"could not decode {signature}: {result.stdout!r}") from caught


def cast_value(address: str, signature: str, *args: str, rpc_url: str) -> Any:
    values = cast_json(address, signature, *args, rpc_url=rpc_url)
    if not isinstance(values, list) or len(values) != 1:
        raise VerifyError(f"{signature} returned {values!r}")
    return values[0]


def as_uint(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("a boolean is not a uint")
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text, 0) if text.lower().startswith("0x") else int(text)


def as_address(value: Any) -> str:
    text = str(value)
    if not ADDRESS.match(text):
        raise ConfigError(f"not an address: {text!r}")
    return text.lower()


def rpc_chain_id(url: str) -> int:
    return int(rpc(url, "eth_chainId"), 16)


def code_at(url: str, address: str, block: str = "latest") -> str:
    return rpc(url, "eth_getCode", [address, block])


def keccak(code: str) -> str:
    _, cast = tools()
    return run([str(cast), "keccak", code]).stdout.strip()


def asset_decimal(token: str, url: str) -> int:
    _, cast = tools()
    result = run([str(cast), "call", token, "decimals()(uint8)", "--rpc-url", url])
    return int(result.stdout.strip())


# --------------------------------------------------------------------------- profile


def interpolate(value: Any, environ: dict[str, str], missing: list[str]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if not environ.get(name):
                missing.append(name)
                return ""
            return environ[name]

        return ENV_REF.sub(replace, value)
    if isinstance(value, list):
        return [interpolate(item, environ, missing) for item in value]
    if isinstance(value, dict):
        return {key: interpolate(item, environ, missing) for key, item in value.items()}
    return value


def load_profile(path: Path, environ: dict[str, str] | None = None) -> dict:
    if not path.exists():
        raise ConfigError(f"profile not found: {path}")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as caught:
        raise ConfigError(f"{path} is not valid JSON: {caught}") from caught
    missing: list[str] = []
    profile = interpolate(raw, environ if environ is not None else os.environ, missing)
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise ConfigError(f"profile {path} needs environment variable(s): {names}")
    profile["_path"] = str(path)
    return profile


def require(profile: dict, name: str, kind: type) -> Any:
    if name not in profile:
        raise ConfigError(f"profile is missing {name!r}")
    value = profile[name]
    if not isinstance(value, kind):
        raise ConfigError(f"profile field {name!r} must be {kind.__name__}")
    return value


def parse_uint(value: Any, label: str) -> int:
    text = str(value)
    if not UINT.match(text):
        raise ConfigError(f"{label} must be a non-negative decimal integer, got {text!r}")
    return int(text)


def validate_profile(profile: dict) -> None:
    chain_id = require(profile, "chainId", int)
    if chain_id in MAINNET_CHAIN_IDS or profile.get("mainnet") is True:
        raise Refused(
            "mainnet deployments are disabled: no mainnet value before the external audit"
        )
    for name in ("network", "chainName", "bridgeId", "rpc"):
        if not str(profile.get(name) or "").strip():
            raise ConfigError(f"profile field {name!r} must be a non-empty string")
    if not str(profile["rpc"]).startswith(("http://", "https://")):
        raise ConfigError(f"rpc must be an http(s) URL, got {profile['rpc']!r}")

    admins = require(profile, "admins", list)
    relayers = require(profile, "relayers", list)
    if not admins or len(admins) > 10:
        raise ConfigError("admins must have 1..10 entries")
    if not relayers or len(relayers) > 10:
        raise ConfigError("relayers must have 1..10 entries")
    admin_set = [as_address(item) for item in admins]
    relayer_set = [as_address(item) for item in relayers]
    if len(set(admin_set)) != len(admin_set):
        raise ConfigError("admin addresses must be distinct")
    if len(set(relayer_set)) != len(relayer_set):
        raise ConfigError("relayer addresses must be distinct")
    if ZERO in admin_set or ZERO in relayer_set:
        raise ConfigError("admin and relayer addresses must not be zero")
    treasury = as_address(require(profile, "treasury", str))
    if treasury == ZERO:
        raise ConfigError("treasury must not be zero")

    admin_threshold = require(profile, "adminThreshold", int)
    relayer_threshold = require(profile, "relayerThreshold", int)
    if not 1 <= admin_threshold <= len(admin_set):
        raise ConfigError("adminThreshold must be between 1 and the admin count")
    if not 1 <= relayer_threshold <= len(relayer_set):
        raise ConfigError("relayerThreshold must be between 1 and the relayer count")

    assets = require(profile, "assets", list)
    if not assets or len(assets) > 8:
        raise ConfigError("assets must have 1..8 entries")
    seen_keys: set[str] = set()
    seen_tokens: set[str] = set()
    native_seen = False
    for index, asset in enumerate(assets, start=1):
        label = f"asset {index}"
        if not isinstance(asset, dict):
            raise ConfigError(f"{label} must be an object")
        for name in (
            "assetKey",
            "token",
            "nativeDecimals",
            "rholoDecimals",
            "maxDeposit",
            "maxLocked",
            "withdrawFeeBps",
        ):
            if name not in asset:
                raise ConfigError(f"{label} is missing {name!r}")
        key = str(asset["assetKey"])
        if not key.startswith(f"{profile['chainName']}."):
            raise ConfigError(
                f"{label} assetKey {key!r} is not chain-qualified for {profile['chainName']!r}"
            )
        if key in seen_keys:
            raise ConfigError(f"{label} duplicates assetKey {key!r}")
        seen_keys.add(key)
        token = str(asset["token"])
        if token in ("native", ZERO):
            if native_seen:
                raise ConfigError("only one native asset is allowed")
            native_seen = True
            token = ZERO
        else:
            token = as_address(token)
            if token == ZERO:
                raise ConfigError(f"{label} token must not be the zero address")
        if token in seen_tokens:
            raise ConfigError(f"{label} reuses a token address")
        seen_tokens.add(token)
        native_decimals = parse_uint(asset["nativeDecimals"], f"{label} nativeDecimals")
        rholo_decimals = parse_uint(asset["rholoDecimals"], f"{label} rholoDecimals")
        if native_decimals > 18:
            raise ConfigError(f"{label} nativeDecimals must be <= 18")
        if rholo_decimals > native_decimals:
            raise ConfigError(f"{label} rholoDecimals exceeds nativeDecimals")
        if token == ZERO and native_decimals != 18:
            raise ConfigError(f"{label}: native ETH is 18 decimals")
        max_deposit = parse_uint(asset["maxDeposit"], f"{label} maxDeposit")
        max_locked = parse_uint(asset["maxLocked"], f"{label} maxLocked")
        if max_deposit == 0:
            raise ConfigError(f"{label} maxDeposit must be positive")
        if max_locked < max_deposit:
            raise ConfigError(f"{label} maxLocked must be at least maxDeposit")
        fee = parse_uint(asset["withdrawFeeBps"], f"{label} withdrawFeeBps")
        if fee > 10_000:
            raise ConfigError(f"{label} withdrawFeeBps must be <= 10000")


def plan(profile: dict) -> dict:
    """Normalize a validated profile into the values the contract expects."""
    assets = []
    for asset in profile["assets"]:
        token = str(asset["token"])
        token = ZERO if token in ("native", ZERO) else as_address(token)
        native_decimals = parse_uint(asset["nativeDecimals"], "nativeDecimals")
        rholo_decimals = parse_uint(asset["rholoDecimals"], "rholoDecimals")
        assets.append(
            {
                "assetKey": str(asset["assetKey"]),
                "token": token,
                "nativeDecimals": native_decimals,
                "rholoDecimals": rholo_decimals,
                "scale": 10 ** (native_decimals - rholo_decimals),
                "maxDeposit": parse_uint(asset["maxDeposit"], "maxDeposit"),
                "maxLocked": parse_uint(asset["maxLocked"], "maxLocked"),
                "withdrawFeeBps": parse_uint(asset["withdrawFeeBps"], "withdrawFeeBps"),
            }
        )
    return {
        "network": profile["network"],
        "chainName": profile["chainName"],
        "chainId": profile["chainId"],
        "bridgeId": profile["bridgeId"],
        "rpc": profile["rpc"],
        "admins": [as_address(item) for item in profile["admins"]],
        "adminThreshold": profile["adminThreshold"],
        "relayers": [as_address(item) for item in profile["relayers"]],
        "relayerThreshold": profile["relayerThreshold"],
        "treasury": as_address(profile["treasury"]),
        "assets": assets,
    }


def describe(plan_rows: dict) -> str:
    lines = [
        f"network:   {plan_rows['network']} ({plan_rows['chainName']}, chain id {plan_rows['chainId']})",
        f"bridge id: {plan_rows['bridgeId']}",
        f"rpc:       {plan_rows['rpc']}",
        f"admins:    {len(plan_rows['admins'])} (threshold {plan_rows['adminThreshold']})",
        f"relayers:  {len(plan_rows['relayers'])} (threshold {plan_rows['relayerThreshold']})",
        f"treasury:  {plan_rows['treasury']}",
        "assets:",
    ]
    for asset in plan_rows["assets"]:
        lines.append(
            f"  {asset['assetKey']:<16} token {asset['token']} scale {asset['scale']} "
            f"fee {asset['withdrawFeeBps']} bps"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- deploy


def deploy_env(plan_rows: dict, private_key: str) -> dict[str, str]:
    env = {
        "PRIVATE_KEY": private_key,
        "CHAIN_TAG": str(plan_rows["chainId"]),
        "NETWORK": plan_rows["network"],
        "CHAIN_NAME": plan_rows["chainName"],
        "BRIDGE_ID": plan_rows["bridgeId"],
        "ADMIN_COUNT": str(len(plan_rows["admins"])),
        "ADMIN_THRESHOLD": str(plan_rows["adminThreshold"]),
        "RELAYER_COUNT": str(len(plan_rows["relayers"])),
        "RELAYER_THRESHOLD": str(plan_rows["relayerThreshold"]),
        "TREASURY": plan_rows["treasury"],
        "ASSET_COUNT": str(len(plan_rows["assets"])),
    }
    for index, admin in enumerate(plan_rows["admins"], start=1):
        env[f"ADMIN_{index}"] = admin
    for index, relayer in enumerate(plan_rows["relayers"], start=1):
        env[f"RELAYER_{index}"] = relayer
    for index, asset in enumerate(plan_rows["assets"], start=1):
        env[f"ASSET_{index}_TOKEN"] = asset["token"]
        env[f"ASSET_{index}_KEY"] = asset["assetKey"]
        env[f"ASSET_{index}_MAX_DEPOSIT"] = str(asset["maxDeposit"])
        env[f"ASSET_{index}_MAX_LOCKED"] = str(asset["maxLocked"])
        env[f"ASSET_{index}_SCALE"] = str(asset["scale"])
        env[f"ASSET_{index}_WITHDRAW_FEE_BPS"] = str(asset["withdrawFeeBps"])
    return env


def preflight_chain(plan_rows: dict) -> None:
    on_chain = rpc_chain_id(plan_rows["rpc"])
    if on_chain != plan_rows["chainId"]:
        raise Refused(
            f"rpc reports chain id {on_chain}, profile says {plan_rows['chainId']}"
        )
    for asset in plan_rows["assets"]:
        token = asset["token"]
        if token == ZERO:
            continue
        if code_at(plan_rows["rpc"], token) in ("0x", "0x0"):
            raise ConfigError(f"{asset['assetKey']}: no ERC-20 code at {token}")
        decimals = asset_decimal(token, plan_rows["rpc"])
        if decimals != asset["nativeDecimals"]:
            raise ConfigError(
                f"{asset['assetKey']}: token reports {decimals} decimals, "
                f"profile says {asset['nativeDecimals']}"
            )


def broadcast(plan_rows: dict, private_key: str, verify: bool) -> dict:
    forge, _ = tools()
    args = [
        str(forge),
        "script",
        "script/DeployVault.s.sol:DeployVault",
        "--rpc-url",
        plan_rows["rpc"],
        "--broadcast",
    ]
    if plan_rows["chainId"] not in LOCAL_CHAIN_IDS:
        args.append("--slow")
    api_key = os.environ.get("ETHERSCAN_API_KEY")
    if verify and api_key:
        args += ["--verify", "--etherscan-api-key", api_key]
    env = {**os.environ, **deploy_env(plan_rows, private_key)}
    result = subprocess.run(
        args, cwd=EVM, env=env, capture_output=True, text=True, timeout=900
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace(private_key, "<redacted>")
        raise RuntimeError(f"forge script failed:\n{detail}")
    broadcast_file = (
        EVM / "broadcast" / "DeployVault.s.sol" / str(plan_rows["chainId"]) / "run-latest.json"
    )
    if not broadcast_file.exists():
        raise RuntimeError(f"no broadcast artifact at {broadcast_file}")
    data = json.loads(broadcast_file.read_text())
    for tx in data.get("transactions", []):
        if tx.get("contractName") == "BridgeVault" and tx.get("contractAddress"):
            return {
                "address": tx["contractAddress"],
                "txHash": tx.get("hash"),
                "deployer": (tx.get("transaction") or {}).get("from"),
            }
    raise RuntimeError("broadcast artifact has no BridgeVault address")


def read_config(address: str, plan_rows: dict) -> dict:
    rpc_url = plan_rows["rpc"]
    if code_at(rpc_url, address) in ("0x", "0x0"):
        raise VerifyError(f"no code at {address}")
    admins = [
        as_address(cast_value(address, "admins(uint256)(address)", str(index), rpc_url=rpc_url))
        for index in range(int(cast_value(address, "adminCount()(uint256)", rpc_url=rpc_url)))
    ]
    relayers = [
        as_address(cast_value(address, "relayers(uint256)(address)", str(index), rpc_url=rpc_url))
        for index in range(int(cast_value(address, "relayerCount()(uint256)", rpc_url=rpc_url)))
    ]
    assets = {}
    for asset in plan_rows["assets"]:
        values = cast_json(
            address,
            "assets(address)(bool,uint256,uint256,uint256,uint256,string)",
            asset["token"],
            rpc_url=rpc_url,
        )
        if not isinstance(values, list) or len(values) != 6:
            raise VerifyError(f"assets({asset['token']}) returned {values!r}")
        assets[asset["token"]] = {
            "enabled": bool(values[0]),
            "maxDeposit": as_uint(values[1]),
            "maxLocked": as_uint(values[2]),
            "scale": as_uint(values[3]),
            "withdrawFeeBps": as_uint(values[4]),
            "assetKey": str(values[5]),
        }
    return {
        "chainTag": as_uint(cast_value(address, "chainTag()(uint256)", rpc_url=rpc_url)),
        "network": str(cast_value(address, "network()(string)", rpc_url=rpc_url)),
        "chainName": str(cast_value(address, "chainName()(string)", rpc_url=rpc_url)),
        "bridgeId": str(cast_value(address, "bridgeId()(string)", rpc_url=rpc_url)),
        "treasury": as_address(cast_value(address, "treasury()(address)", rpc_url=rpc_url)),
        "admins": admins,
        "adminThreshold": as_uint(cast_value(address, "adminThreshold()(uint256)", rpc_url=rpc_url)),
        "relayers": relayers,
        "relayerThreshold": as_uint(cast_value(address, "relayerThreshold()(uint256)", rpc_url=rpc_url)),
        "paused": bool(cast_value(address, "paused()(bool)", rpc_url=rpc_url)),
        "assets": assets,
    }


def compare(plan_rows: dict, actual: dict) -> list[str]:
    issues: list[str] = []

    def check(label: str, got: Any, want: Any) -> None:
        if got != want:
            issues.append(f"{label}: chain has {got!r}, expected {want!r}")

    check("chainTag", actual["chainTag"], plan_rows["chainId"])
    check("network", actual["network"], plan_rows["network"])
    check("chainName", actual["chainName"], plan_rows["chainName"])
    check("bridgeId", actual["bridgeId"], plan_rows["bridgeId"])
    check("treasury", actual["treasury"], plan_rows["treasury"])
    check("admins", actual["admins"], plan_rows["admins"])
    check("adminThreshold", actual["adminThreshold"], plan_rows["adminThreshold"])
    check("relayers", actual["relayers"], plan_rows["relayers"])
    check("relayerThreshold", actual["relayerThreshold"], plan_rows["relayerThreshold"])
    check("paused", actual["paused"], False)
    for asset in plan_rows["assets"]:
        got = actual["assets"].get(asset["token"])
        if got is None:
            issues.append(f"{asset['assetKey']}: asset missing on chain")
            continue
        check(f"{asset['assetKey']}.enabled", got["enabled"], True)
        check(f"{asset['assetKey']}.assetKey", got["assetKey"], asset["assetKey"])
        check(f"{asset['assetKey']}.maxDeposit", got["maxDeposit"], asset["maxDeposit"])
        check(f"{asset['assetKey']}.maxLocked", got["maxLocked"], asset["maxLocked"])
        check(f"{asset['assetKey']}.scale", got["scale"], asset["scale"])
        check(
            f"{asset['assetKey']}.withdrawFeeBps",
            got["withdrawFeeBps"],
            asset["withdrawFeeBps"],
        )
    return issues


def manifest(plan_rows: dict, tx: dict, actual: dict, runtime_code: str) -> dict:
    receipt = (
        rpc(plan_rows["rpc"], "eth_getTransactionReceipt", [tx["txHash"]])
        if tx.get("txHash")
        else None
    )
    deploy_block = int(receipt["blockNumber"], 16) if receipt else None
    return {
        "schema": SCHEMA,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "profile": None,
        "network": actual["network"],
        "chain": actual["chainName"],
        "chainId": actual["chainTag"],
        "bridgeId": actual["bridgeId"],
        "contract": {
            "name": "BridgeVault",
            "address": tx["address"].lower(),
            "txHash": tx["txHash"],
            "deployBlock": deploy_block,
            "deployer": (tx.get("deployer") or "").lower() or None,
            "runtimeCodeKeccak": keccak(runtime_code),
        },
        "admins": actual["admins"],
        "adminThreshold": actual["adminThreshold"],
        "relayers": actual["relayers"],
        "relayerThreshold": actual["relayerThreshold"],
        "treasury": actual["treasury"],
        "assets": [
            {
                "assetKey": actual["assets"][asset["token"]]["assetKey"],
                "token": asset["token"],
                "nativeDecimals": asset["nativeDecimals"],
                "rholoDecimals": asset["rholoDecimals"],
                "maxDeposit": str(actual["assets"][asset["token"]]["maxDeposit"]),
                "maxLocked": str(actual["assets"][asset["token"]]["maxLocked"]),
                "scale": str(actual["assets"][asset["token"]]["scale"]),
                "withdrawFeeBps": actual["assets"][asset["token"]]["withdrawFeeBps"],
            }
            for asset in plan_rows["assets"]
        ],
    }


def write_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=path.name, suffix=".tmp", delete=False
    ) as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def cmd_deploy(args: argparse.Namespace) -> int:
    profile_path = Path(args.profile)
    profile = load_profile(profile_path)
    validate_profile(profile)
    plan_rows = plan(profile)
    key_env = str(profile.get("deployerKeyEnv") or "DEPLOYER_KEY")
    key = os.environ.get(key_env, "")

    print(describe(plan_rows))
    if args.dry_run:
        print(f"deployer key: {'<set>' if key else '<missing: ' + key_env + '>'} (not used)")
        print("plan: OK (no transaction sent)")
        return 0

    if not key:
        raise ConfigError(f"{key_env} is not set (the deployer private key)")
    if not re.match(r"^0x[0-9a-fA-F]{64}$", key):
        raise ConfigError(f"{key_env} must be a 0x-prefixed 32-byte hex private key")
    if plan_rows["chainId"] not in LOCAL_CHAIN_IDS and not args.yes:
        raise Refused(
            f"chain id {plan_rows['chainId']} is not local; re-run with --yes to deploy"
        )

    preflight_chain(plan_rows)
    tx = broadcast(plan_rows, key, verify=not args.no_verify)
    actual = read_config(tx["address"], plan_rows)
    issues = compare(plan_rows, actual)
    runtime_code = code_at(plan_rows["rpc"], tx["address"])
    data = manifest(plan_rows, tx, actual, runtime_code)
    data["profile"] = str(profile_path)
    out = Path(args.out) if args.out else DEPLOYMENTS / f"{plan_rows['network']}.json"
    write_manifest(out, data)
    print(f"vault:    {tx['address']}")
    print(f"tx:       {tx['txHash']}")
    print(f"manifest: {out}")
    if issues:
        print("deployed configuration does not match the profile:")
        for issue in issues:
            print(f"  FAIL  {issue}")
        return 1
    print("deploy: PASS (chain configuration read back and matched)")
    return 0


# --------------------------------------------------------------------------- verify


def cmd_verify(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if not path.exists():
        raise ConfigError(f"manifest not found: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as caught:
        raise ConfigError(f"{path} is not valid JSON: {caught}") from caught
    if data.get("schema") != SCHEMA:
        raise ConfigError(f"{path} has schema {data.get('schema')!r}, expected {SCHEMA}")
    required = (
        "network",
        "chain",
        "chainId",
        "bridgeId",
        "contract",
        "admins",
        "adminThreshold",
        "relayers",
        "relayerThreshold",
        "treasury",
        "assets",
    )
    missing = [name for name in required if name not in data]
    if missing:
        raise ConfigError(f"{path} is missing {', '.join(missing)}")
    if "address" not in data["contract"] or "runtimeCodeKeccak" not in data["contract"]:
        raise ConfigError(f"{path} has an incomplete contract record")
    for index, asset in enumerate(data["assets"], start=1):
        for name in (
            "assetKey",
            "token",
            "nativeDecimals",
            "rholoDecimals",
            "maxDeposit",
            "maxLocked",
            "scale",
            "withdrawFeeBps",
        ):
            if name not in asset:
                raise ConfigError(f"{path} asset {index} is missing {name}")

    rpc_url = args.rpc or os.environ.get("RBRIDGE_RPC_URL", "")
    if not rpc_url:
        raise ConfigError("pass --rpc or set RBRIDGE_RPC_URL to verify against a chain")
    address = as_address(data["contract"]["address"])
    plan_rows = {
        "rpc": rpc_url,
        "chainId": data["chainId"],
        "network": data["network"],
        "chainName": data["chain"],
        "bridgeId": data["bridgeId"],
        "admins": [as_address(item) for item in data["admins"]],
        "adminThreshold": data["adminThreshold"],
        "relayers": [as_address(item) for item in data["relayers"]],
        "relayerThreshold": data["relayerThreshold"],
        "treasury": as_address(data["treasury"]),
        "assets": [
            {
                "assetKey": asset["assetKey"],
                "token": as_address(asset["token"]),
                "nativeDecimals": int(asset["nativeDecimals"]),
                "rholoDecimals": int(asset["rholoDecimals"]),
                "scale": int(asset["scale"]),
                "maxDeposit": int(asset["maxDeposit"]),
                "maxLocked": int(asset["maxLocked"]),
                "withdrawFeeBps": int(asset["withdrawFeeBps"]),
            }
            for asset in data["assets"]
        ],
    }
    on_chain = rpc_chain_id(rpc_url)
    if on_chain != data["chainId"]:
        raise VerifyError(f"rpc reports chain id {on_chain}, manifest says {data['chainId']}")
    tx_hash = data["contract"].get("txHash")
    if tx_hash:
        receipt = rpc(rpc_url, "eth_getTransactionReceipt", [tx_hash])
        if not receipt:
            raise VerifyError(f"deploy transaction {tx_hash} not found on chain")
        if str(receipt.get("contractAddress") or "").lower() != address:
            raise VerifyError(f"transaction {tx_hash} did not create {address}")
        recorded_block = data["contract"].get("deployBlock")
        if recorded_block is not None and int(receipt["blockNumber"], 16) != int(
            recorded_block
        ):
            raise VerifyError(
                f"deploy block {recorded_block} does not match the chain "
                f"({int(receipt['blockNumber'], 16)})"
            )
        recorded_deployer = (data["contract"].get("deployer") or "").lower()
        if recorded_deployer and str(receipt.get("from", "")).lower() != recorded_deployer:
            raise VerifyError(
                f"deployer {recorded_deployer} does not match the transaction sender"
            )
    runtime_code = code_at(rpc_url, address)
    if runtime_code in ("0x", "0x0"):
        raise VerifyError(f"no code at {address}")
    if keccak(runtime_code) != data["contract"]["runtimeCodeKeccak"]:
        raise VerifyError(
            f"runtime code at {address} does not match the manifest "
            f"({data['contract']['runtimeCodeKeccak']})"
        )
    actual = read_config(address, plan_rows)
    issues = compare(plan_rows, actual)
    if issues:
        print(f"verify: FAIL ({len(issues)} mismatch(es))")
        for issue in issues:
            print(f"  FAIL  {issue}")
        return 1
    print(f"verify: PASS ({data['network']} at {address})")
    return 0


# --------------------------------------------------------------------------- print-env


def cmd_print_env(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if not path.exists():
        raise ConfigError(f"manifest not found: {path}")
    data = json.loads(path.read_text())
    vault = data.get("contract", {}).get("address")
    if not vault:
        raise ConfigError(f"{path} has no contract address")
    print(f"VITE_RBRIDGE_VAULT={vault}")
    for asset in data.get("assets", []):
        if asset.get("assetKey", "").endswith(".usdt") and asset.get("token") != ZERO:
            print(f"VITE_RBRIDGE_USDT={asset['token']}")
    return 0


# --------------------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    deploy = sub.add_parser("deploy", help="validate a profile, deploy the vault, write a manifest")
    deploy.add_argument("--profile", required=True, help="network profile JSON")
    deploy.add_argument("--out", help="manifest path (default deployments/<network>.json)")
    deploy.add_argument("--yes", action="store_true", help="allow a non-local chain")
    deploy.add_argument("--dry-run", action="store_true", help="print the plan, send nothing")
    deploy.add_argument("--no-verify", action="store_true", help="skip Etherscan verification")
    deploy.set_defaults(func=cmd_deploy)

    verify = sub.add_parser("verify", help="re-read a manifest against its chain")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--rpc", help="RPC URL (or RBRIDGE_RPC_URL)")
    verify.set_defaults(func=cmd_verify)

    print_env = sub.add_parser("print-env", help="web env vars for a manifest")
    print_env.add_argument("--manifest", required=True)
    print_env.set_defaults(func=cmd_print_env)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Refused as caught:
        print(f"refused: {caught}", file=sys.stderr)
        return 3
    except ConfigError as caught:
        print(f"config: {caught}", file=sys.stderr)
        return 2
    except VerifyError as caught:
        print(f"verify: {caught}", file=sys.stderr)
        return 1
    except RuntimeError as caught:
        print(f"error: {caught}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
