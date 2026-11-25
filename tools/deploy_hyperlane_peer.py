#!/usr/bin/env python3
"""Deploy and verify the r-bridge HyperlanePeer from a network profile.

The profile names the chain, the canonical Hyperlane Mailbox, the rholo domain and peer,
the relayer and owner, and the ERC-20 stables to support. `deploy` refuses mainnet,
checks the chain id, the Mailbox's `localDomain`, and every token's code and decimals,
broadcasts through `contracts/evm/script/DeployHyperlanePeer.s.sol`, reads the peer back
from the chain, and writes a gitignored manifest. `verify` re-reads it.

The deployer key is read from the profile's `deployerKeyEnv` and never persisted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import deploy_evm as base  # noqa: E402

EVM = ROOT / "contracts" / "evm"
DEPLOYMENTS = ROOT / "deployments"
SCHEMA = "rbridge.hyperlane-peer.v1"
HEX32 = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


def validate(profile: dict) -> dict:
    chain_id = base.require(profile, "chainId", int)
    if chain_id in base.MAINNET_CHAIN_IDS or profile.get("mainnet") is True:
        raise base.Refused(
            "mainnet deployments are disabled: no mainnet value before the external audit"
        )
    for name in ("network", "chainName", "rpc", "mailbox", "owner", "relayer", "deployerKeyEnv"):
        base.require(profile, name, str)
    local_domain = base.parse_uint(base.require(profile, "localDomain", int), "localDomain")
    remote_domain = base.parse_uint(base.require(profile, "remoteDomain", int), "remoteDomain")
    if not 0 < local_domain < 2**32 or not 0 < remote_domain < 2**32:
        raise base.ConfigError("domains must be nonzero uint32 values")
    remote_peer = str(base.require(profile, "remotePeer", str))
    if not HEX32.match(remote_peer):
        raise base.ConfigError("remotePeer must be a 32-byte hex value")
    if not remote_peer.startswith("0x"):
        remote_peer = "0x" + remote_peer
    for name in ("mailbox", "owner", "relayer"):
        if not base.ADDRESS.match(profile[name]):
            raise base.ConfigError(f"{name} must be a 20-byte hex address")

    raw_assets = base.require(profile, "assets", list)
    if not raw_assets:
        raise base.ConfigError("assets must not be empty")
    assets = []
    seen_tokens, seen_keys = set(), set()
    for raw in raw_assets:
        if not isinstance(raw, dict):
            raise base.ConfigError("each asset must be an object")
        asset_key = str(raw.get("assetKey", ""))
        token = str(raw.get("token", ""))
        if "." not in asset_key:
            raise base.ConfigError(f"assetKey {asset_key!r} must be chain-qualified")
        if not base.ADDRESS.match(token):
            raise base.ConfigError(f"{asset_key}: token must be a 20-byte address")
        if token.lower() in seen_tokens or asset_key in seen_keys:
            raise base.ConfigError(f"{asset_key}: duplicate token or asset key")
        seen_tokens.add(token.lower())
        seen_keys.add(asset_key)
        decimals = base.parse_uint(raw.get("decimals"), f"{asset_key}.decimals")
        scale = base.parse_uint(raw.get("scale"), f"{asset_key}.scale")
        if scale <= 0:
            raise base.ConfigError(f"{asset_key}.scale must be positive")
        assets.append(
            {
                "assetKey": asset_key,
                "token": token,
                "decimals": decimals,
                "scale": scale,
                "maxDeposit": base.parse_uint(raw.get("maxDeposit"), f"{asset_key}.maxDeposit"),
                "maxLocked": base.parse_uint(raw.get("maxLocked"), f"{asset_key}.maxLocked"),
            }
        )

    return {
        "network": profile["network"],
        "chainName": profile["chainName"],
        "chainId": chain_id,
        "rpc": profile["rpc"],
        "mailbox": profile["mailbox"],
        "localDomain": local_domain,
        "remoteDomain": remote_domain,
        "remotePeer": remote_peer.lower(),
        "owner": profile["owner"].lower(),
        "relayer": profile["relayer"].lower(),
        "deployerKeyEnv": profile["deployerKeyEnv"],
        "assets": assets,
        "profile": profile.get("_path", ""),
    }


def preflight(plan: dict) -> None:
    on_chain = base.rpc_chain_id(plan["rpc"])
    if on_chain != plan["chainId"]:
        raise base.Refused(f"rpc reports chain id {on_chain}, profile says {plan['chainId']}")
    if base.code_at(plan["rpc"], plan["mailbox"]) in ("0x", "0x0"):
        raise base.ConfigError(f"no Hyperlane Mailbox code at {plan['mailbox']}")
    domain = base.as_uint(
        base.cast_value(plan["mailbox"], "localDomain()(uint32)", rpc_url=plan["rpc"])
    )
    if domain != plan["localDomain"]:
        raise base.ConfigError(
            f"Mailbox localDomain is {domain}, profile says {plan['localDomain']}"
        )
    for asset in plan["assets"]:
        if base.code_at(plan["rpc"], asset["token"]) in ("0x", "0x0"):
            raise base.ConfigError(f"{asset['assetKey']}: no ERC-20 code at {asset['token']}")
        decimals = base.asset_decimal(asset["token"], plan["rpc"])
        if decimals != asset["decimals"]:
            raise base.ConfigError(
                f"{asset['assetKey']}: token reports {decimals} decimals, "
                f"profile says {asset['decimals']}"
            )


def deploy_env(plan: dict, private_key: str) -> dict[str, str]:
    env = {
        "PRIVATE_KEY": private_key,
        "MAILBOX": plan["mailbox"],
        "LOCAL_DOMAIN": str(plan["localDomain"]),
        "REMOTE_DOMAIN": str(plan["remoteDomain"]),
        "REMOTE_PEER": plan["remotePeer"],
        "OWNER": plan["owner"],
        "RELAYER": plan["relayer"],
        "ASSET_COUNT": str(len(plan["assets"])),
    }
    for index, asset in enumerate(plan["assets"], start=1):
        env[f"ASSET_{index}_TOKEN"] = asset["token"]
        env[f"ASSET_{index}_KEY"] = asset["assetKey"]
        env[f"ASSET_{index}_SCALE"] = str(asset["scale"])
        env[f"ASSET_{index}_MAX_DEPOSIT"] = str(asset["maxDeposit"])
        env[f"ASSET_{index}_MAX_LOCKED"] = str(asset["maxLocked"])
    return env


def broadcast(plan: dict, private_key: str, verify: bool) -> dict:
    forge, _ = base.tools()
    args = [
        str(forge),
        "script",
        "script/DeployHyperlanePeer.s.sol:DeployHyperlanePeer",
        "--rpc-url",
        plan["rpc"],
        "--broadcast",
    ]
    if plan["chainId"] not in base.LOCAL_CHAIN_IDS:
        args.append("--slow")
    api_key = os.environ.get("ETHERSCAN_API_KEY")
    if verify and api_key:
        args += ["--verify", "--etherscan-api-key", api_key]
    env = {**os.environ, **deploy_env(plan, private_key)}
    result = subprocess.run(args, cwd=EVM, env=env, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace(private_key, "<redacted>")
        raise RuntimeError(f"forge script failed:\n{detail}")
    artifact = (
        EVM / "broadcast" / "DeployHyperlanePeer.s.sol" / str(plan["chainId"]) / "run-latest.json"
    )
    if not artifact.exists():
        raise RuntimeError(f"no broadcast artifact at {artifact}")
    data = json.loads(artifact.read_text())
    found: dict[str, dict] = {}
    for tx in data.get("transactions", []):
        name = tx.get("contractName")
        address = tx.get("contractAddress")
        if name in ("HyperlanePeer", "RbridgeTrustedRelayerIsm") and address:
            found[name] = {
                "address": address,
                "txHash": tx.get("hash"),
                "deployer": (tx.get("transaction") or {}).get("from"),
            }
    if "HyperlanePeer" not in found or "RbridgeTrustedRelayerIsm" not in found:
        raise RuntimeError("broadcast artifact is missing the peer or ISM")
    return found


def read_peer(address: str, plan: dict) -> dict:
    rpc_url = plan["rpc"]
    if base.code_at(rpc_url, address) in ("0x", "0x0"):
        raise base.VerifyError(f"no code at {address}")

    def value(signature: str, *args: str) -> Any:
        return base.cast_value(address, signature, *args, rpc_url=rpc_url)

    assets = {}
    for asset in plan["assets"]:
        values = base.cast_json(
            address,
            "assets(address)(bool,uint256,uint256,uint256,string)",
            asset["token"],
            rpc_url=rpc_url,
        )
        if not isinstance(values, list) or len(values) != 5:
            raise base.VerifyError(f"assets({asset['token']}) returned {values!r}")
        key_hash = base.run([str(base.tools()[1]), "keccak", asset["assetKey"]]).stdout.strip()
        token = base.as_address(
            value("tokenForAssetKey(bytes32)(address)", key_hash)
        )
        assets[asset["token"]] = {
            "enabled": bool(values[0]),
            "scale": base.as_uint(values[1]),
            "maxDeposit": base.as_uint(values[2]),
            "maxLocked": base.as_uint(values[3]),
            "assetKey": str(values[4]),
            "tokenForAssetKey": token,
        }
    return {
        "mailbox": base.as_address(value("mailbox()(address)")),
        "localDomain": base.as_uint(value("localDomain()(uint32)")),
        "remoteDomain": base.as_uint(value("remoteDomain()(uint32)")),
        "remotePeer": str(value("remotePeer()(bytes32)")).lower(),
        "ism": base.as_address(value("ism()(address)")),
        "owner": base.as_address(value("owner()(address)")),
        "paused": bool(value("paused()(bool)")),
        "assets": assets,
    }


def compare(plan: dict, actual: dict) -> list[str]:
    issues: list[str] = []

    def check(label: str, got: Any, want: Any) -> None:
        if got != want:
            issues.append(f"{label}: chain has {got!r}, expected {want!r}")

    check("mailbox", actual["mailbox"], plan["mailbox"].lower())
    check("localDomain", actual["localDomain"], plan["localDomain"])
    check("remoteDomain", actual["remoteDomain"], plan["remoteDomain"])
    check("remotePeer", actual["remotePeer"], plan["remotePeer"].lower())
    check("owner", actual["owner"], plan["owner"].lower())
    check("paused", actual["paused"], False)
    for asset in plan["assets"]:
        got = actual["assets"].get(asset["token"])
        if got is None:
            issues.append(f"{asset['assetKey']}: asset missing on chain")
            continue
        check(f"{asset['assetKey']}.enabled", got["enabled"], True)
        check(f"{asset['assetKey']}.assetKey", got["assetKey"], asset["assetKey"])
        check(f"{asset['assetKey']}.scale", got["scale"], asset["scale"])
        check(f"{asset['assetKey']}.maxDeposit", got["maxDeposit"], asset["maxDeposit"])
        check(f"{asset['assetKey']}.maxLocked", got["maxLocked"], asset["maxLocked"])
        check(
            f"{asset['assetKey']}.tokenForAssetKey",
            got["tokenForAssetKey"],
            asset["token"].lower(),
        )
    return issues


def manifest(plan: dict, deployed: dict, actual: dict) -> dict:
    peer = deployed["HyperlanePeer"]
    ism = deployed["RbridgeTrustedRelayerIsm"]
    runtime = base.code_at(plan["rpc"], peer["address"])
    return {
        "schema": SCHEMA,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "profile": plan["profile"],
        "network": plan["network"],
        "chain": plan["chainName"],
        "chainId": plan["chainId"],
        "mailbox": plan["mailbox"],
        "localDomain": plan["localDomain"],
        "remoteDomain": plan["remoteDomain"],
        "remotePeer": plan["remotePeer"],
        "relayer": plan["relayer"],
        "owner": plan["owner"],
        "peer": {
            "address": peer["address"],
            "txHash": peer.get("txHash"),
            "deployer": peer.get("deployer"),
            "runtimeCodeKeccak": base.keccak(runtime),
        },
        "ism": {"address": ism["address"], "txHash": ism.get("txHash")},
        "assets": plan["assets"],
    }


def cmd_plan(args: argparse.Namespace) -> int:
    profile = base.load_profile(Path(args.profile))
    plan = validate(profile)
    print(json.dumps(plan, indent=2))
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    profile = base.load_profile(Path(args.profile))
    plan = validate(profile)
    if plan["chainId"] not in base.LOCAL_CHAIN_IDS and not args.yes:
        raise base.Refused("non-local deployment needs --yes")
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    private_key = os.environ.get(plan["deployerKeyEnv"])
    if not private_key:
        raise base.ConfigError(f"environment variable {plan['deployerKeyEnv']} is not set")
    preflight(plan)
    deployed = broadcast(plan, private_key, not args.no_verify)
    actual = read_peer(deployed["HyperlanePeer"]["address"], plan)
    issues = compare(plan, actual)
    if issues:
        raise base.VerifyError("deployed configuration mismatch: " + "; ".join(issues))
    out = Path(args.out or DEPLOYMENTS / f"hyperlane-peer-{plan['network']}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest(plan, deployed, actual), indent=2) + "\n")
    print(f"peer: {deployed['HyperlanePeer']['address']}")
    print(f"ism:  {deployed['RbridgeTrustedRelayerIsm']['address']}")
    print(f"manifest: {out}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if not path.exists():
        raise base.ConfigError(f"manifest not found: {path}")
    data = json.loads(path.read_text())
    rpc_url = args.rpc or os.environ.get("RBRIDGE_RPC_URL")
    if not rpc_url:
        raise base.ConfigError("verify needs --rpc or RBRIDGE_RPC_URL")
    plan = {
        "rpc": rpc_url,
        "chainId": data["chainId"],
        "mailbox": data["mailbox"],
        "localDomain": data["localDomain"],
        "remoteDomain": data["remoteDomain"],
        "remotePeer": data["remotePeer"],
        "owner": data["owner"],
        "assets": data["assets"],
    }
    on_chain = base.rpc_chain_id(rpc_url)
    if on_chain != plan["chainId"]:
        raise base.VerifyError(f"rpc reports chain id {on_chain}, manifest says {plan['chainId']}")
    peer = data["peer"]["address"]
    runtime = base.code_at(rpc_url, peer)
    if base.keccak(runtime) != data["peer"]["runtimeCodeKeccak"]:
        raise base.VerifyError("peer runtime code hash differs from the manifest")
    receipt = base.rpc(rpc_url, "eth_getTransactionReceipt", [data["peer"]["txHash"]])
    if not receipt or (receipt.get("contractAddress") or "").lower() != peer.lower():
        raise base.VerifyError("peer deploy transaction did not create the manifest address")
    actual = read_peer(peer, plan)
    issues = compare(plan, actual)
    if issues:
        raise base.VerifyError("; ".join(issues))
    print(f"verified {peer}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="validate a profile and print the plan")
    plan.add_argument("--profile", required=True)
    plan.set_defaults(func=cmd_plan)

    deploy = sub.add_parser("deploy", help="preflight, deploy, read back and write a manifest")
    deploy.add_argument("--profile", required=True)
    deploy.add_argument("--out")
    deploy.add_argument("--yes", action="store_true")
    deploy.add_argument("--dry-run", action="store_true")
    deploy.add_argument("--no-verify", action="store_true")
    deploy.set_defaults(func=cmd_deploy)

    verify = sub.add_parser("verify", help="re-read a manifest against the chain")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--rpc")
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except base.Refused as caught:
        print(f"refused: {caught}", file=sys.stderr)
        return 3
    except base.ConfigError as caught:
        print(f"config: {caught}", file=sys.stderr)
        return 2
    except base.VerifyError as caught:
        print(f"verify: {caught}", file=sys.stderr)
        return 1
    except RuntimeError as caught:
        print(f"error: {caught}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
