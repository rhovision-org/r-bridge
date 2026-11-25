"""Render the r-bridge deploy templates with devnet keys and assets.

`render` fills `contracts/rholo/build/00_bridge.rho`; `render_hyperlane` fills
`contracts/rholo/build/10_hyperlane.rho`. Placeholders are replaced with rholang literals.
This is devnet-only: keys are generated or supplied by the harness and never committed.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "contracts" / "rholo" / "build" / "00_bridge.rho"
HYPERLANE_TEMPLATE = ROOT / "contracts" / "rholo" / "build" / "10_hyperlane.rho"
HYPERLANE_BRIDGE_TEMPLATE = ROOT / "contracts" / "rholo" / "build" / "11_rbridge_hyperlane.rho"


def key_list(pubkeys: list[str]) -> str:
    return "[" + ", ".join(f'"{key}".hexToBytes()' for key in pubkeys) + "]"


def asset_map(assets: list[dict]) -> str:
    rendered: dict[str, dict] = {}
    for asset in assets:
        key = f"{asset['chain']}.{asset['id']}"
        rendered[key] = {
            "symbol": asset["symbol"],
            "wrapped": asset["wrapped"],
            "chain": asset["chain"],
            "id": asset["id"],
            "nativeDecimals": asset["nativeDecimals"],
            "rholoDecimals": asset["rholoDecimals"],
            "feeBpsDeposit": asset["feeBpsDeposit"],
            "feeBpsWithdraw": asset["feeBpsWithdraw"],
            "minDeposit": asset["minDeposit"],
            "maxDeposit": asset["maxDeposit"],
            "enabled": asset["enabled"],
        }
    return json.dumps(rendered, indent=2)


def render(
    network: str,
    bridge_id: str,
    treasury: str,
    admins: list[str],
    admin_threshold: int,
    relayers: list[str],
    relayer_threshold: int,
    assets: list[dict],
) -> str:
    text = TEMPLATE.read_text()
    replacements = {
        "__NETWORK__": json.dumps(network),
        "__BRIDGE_ID__": json.dumps(bridge_id),
        "__TREASURY__": json.dumps(treasury),
        "__ADMINS__": key_list(admins),
        "__ADMIN_THRESHOLD__": str(admin_threshold),
        "__RELAYERS__": key_list(relayers),
        "__RELAYER_THRESHOLD__": str(relayer_threshold),
        "__ASSETS__": asset_map(assets),
    }
    for needle, value in replacements.items():
        text = text.replace(needle, value)
    return text


def render_hyperlane(
    local_domain: int,
    sender_id: str,
    trusted_relayer: str,
    ism_mode: str = "test",
    validators: list[str] | None = None,
    threshold: int = 0,
    tree_id: str = "11" * 32,
) -> str:
    """Render the Hyperlane suite. The trusted relayer is keccak256(pubkey) as lowercase hex."""
    text = HYPERLANE_TEMPLATE.read_text()
    validator_list = validators or []
    validators_literal = "[" + ", ".join(f'"{key}".hexToBytes()' for key in validator_list) + "]"
    replacements = {
        "__LOCAL_DOMAIN__": str(local_domain),
        "__SENDER_ID__": f'"{sender_id}".hexToBytes()',
        "__TRUSTED_RELAYER__": json.dumps(trusted_relayer),
        "__ISM_MODE__": json.dumps(ism_mode),
        "__VALIDATORS__": validators_literal,
        "__THRESHOLD__": str(threshold),
        "__TREE_ID__": json.dumps(tree_id),
    }
    for needle, value in replacements.items():
        text = text.replace(needle, value)
    if "__" in text:
        raise RuntimeError("render_hyperlane: unrendered placeholder remains")
    return text


def render_hyperlane_bridge(
    *,
    network: str,
    bridge_id: str,
    treasury: str,
    admins: list[str],
    admin_threshold: int,
    relayers: list[str],
    relayer_threshold: int,
    assets: list[dict],
    local_domain: int,
    sender_id: str,
    trusted_relayer: str,
    ism_mode: str = "test",
    validators: list[str] | None = None,
    threshold: int = 0,
    tree_id: str = "11" * 32,
    by_domain: dict[str, str] | None = None,
    routes: dict[str, dict] | None = None,
) -> str:
    """Render the wired Bridge + Hyperlane term."""
    text = HYPERLANE_BRIDGE_TEMPLATE.read_text()
    validator_list = validators or []
    replacements = {
        "__NETWORK__": json.dumps(network),
        "__BRIDGE_ID__": json.dumps(bridge_id),
        "__TREASURY__": json.dumps(treasury),
        "__ADMINS__": key_list(admins),
        "__ADMIN_THRESHOLD__": str(admin_threshold),
        "__RELAYERS__": key_list(relayers),
        "__RELAYER_THRESHOLD__": str(relayer_threshold),
        "__ASSETS__": asset_map(assets),
        "__LOCAL_DOMAIN__": str(local_domain),
        "__SENDER_ID__": f'"{sender_id}".hexToBytes()',
        "__TRUSTED_RELAYER__": json.dumps(trusted_relayer),
        "__ISM_MODE__": json.dumps(ism_mode),
        "__VALIDATORS__": "[" + ", ".join(f'"{key}".hexToBytes()' for key in validator_list) + "]",
        "__THRESHOLD__": str(threshold),
        "__TREE_ID__": json.dumps(tree_id),
        "__BY_DOMAIN__": json.dumps(by_domain or {}),
        "__ROUTES__": json.dumps(routes or {}),
    }
    for needle, value in replacements.items():
        text = text.replace(needle, value)
    if "__" in text:
        raise RuntimeError("render_hyperlane_bridge: unrendered placeholder remains")
    return text
