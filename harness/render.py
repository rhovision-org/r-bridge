"""Render the r-bridge deploy template with devnet keys and assets.

The template is `contracts/rholo/build/00_bridge.rho`; placeholders are replaced with
rholang literals. This is devnet-only: keys are generated or supplied by the harness and
never committed.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "contracts" / "rholo" / "build" / "00_bridge.rho"


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
        "__ADMINS__": key_list(admins),
        "__ADMIN_THRESHOLD__": str(admin_threshold),
        "__RELAYERS__": key_list(relayers),
        "__RELAYER_THRESHOLD__": str(relayer_threshold),
        "__ASSETS__": asset_map(assets),
    }
    for needle, value in replacements.items():
        text = text.replace(needle, value)
    return text
