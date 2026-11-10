#!/usr/bin/env python3
"""Dev-only mock relayer with the rail-agnostic HTTP surface.

This is not a relayer: it watches no chain and holds fixed devnet keys. It exists so the
dApp/CLI can exercise the interface in spec/relayer-interface.md while the production
rail (standalone bridge node vs rholo plugin/sidecar) is still undecided.

Endpoints:
  GET  /health
  GET  /v1/chains
  POST /v1/deposits                    {"chain","assetId","tx","amount","recipient","nonce"}
  GET  /v1/deposits/{id}
  GET  /v1/deposits/{id}/attestation

Devnet only. Never expose this to a network holding real value.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "target" / "debug" / "rbridge"


def cli(*args: str) -> dict:
    if not BIN.is_file():
        subprocess.run(["cargo", "build", "-p", "rbridge-cli"], cwd=ROOT, check=True)
    result = subprocess.run([str(BIN), *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"rbridge {' '.join(args)} failed: {result.stderr}{result.stdout}")
    return json.loads(result.stdout.splitlines()[-1])


class Relayer:
    def __init__(self, keys: dict, network: str, bridge_id: str) -> None:
        self.network = network
        self.bridge_id = bridge_id
        self.threshold = 2
        self.secrets = [keys["deployer"]["secret"]] + [
            relayer["secret"] for relayer in keys["relayers"]
        ]
        self.pubkeys = [keys["deployer"]["public"]] + [
            relayer["public"] for relayer in keys["relayers"]
        ]
        self.deposits: dict[str, dict] = {}

    def sign_message(self, text: str) -> list[str]:
        return [cli("sign-text", "--key", secret, "--text", text)["signature"] for secret in self.secrets]

    def canonical(self, chain: str, asset_id: str, tx: str, amount: int, recipient: str, nonce: int) -> str:
        return (
            f"rbridge:v1|{self.network}|{chain}|{self.bridge_id}|"
            f"{chain}.{asset_id}|deposit|{tx}|{amount}|{recipient}|{nonce}"
        )

    def attest(self, payload: dict) -> dict:
        chain = str(payload["chain"])
        asset_id = str(payload["assetId"])
        tx = str(payload["tx"])
        amount = int(payload["amount"])
        recipient = str(payload["recipient"])
        nonce = int(payload.get("nonce", 0))
        message = self.canonical(chain, asset_id, tx, amount, recipient, nonce)
        signatures = self.sign_message(message)
        record = {
            "deposit_id": tx,
            "state": "attested",
            "message": message,
            "signatures": signatures,
            "threshold": self.threshold,
            "signers": len(self.pubkeys),
        }
        self.deposits[tx] = record
        return record

    def health(self) -> dict:
        return {
            "version": "rbridge-mock-relayer/0.1",
            "chains": ["ethereum", "tron", "agoric"],
            "threshold": self.threshold,
            "signers": len(self.pubkeys),
            "paused": False,
            "mock": True,
        }


def handler(relayer: Relayer):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._send(200, relayer.health())
            elif self.path == "/v1/chains":
                self._send(200, {"chains": relayer.health()["chains"]})
            elif self.path.startswith("/v1/deposits/"):
                parts = self.path.strip("/").split("/")
                if len(parts) == 4 and parts[3] == "attestation":
                    record = relayer.deposits.get(parts[2])
                    if record:
                        self._send(200, {"message": record["message"], "signatures": record["signatures"]})
                    else:
                        self._send(404, {"error": "unknown deposit"})
                elif len(parts) == 3:
                    record = relayer.deposits.get(parts[2])
                    if record:
                        self._send(200, record)
                    else:
                        self._send(404, {"error": "unknown deposit"})
                else:
                    self._send(404, {"error": "not found"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/deposits":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("content-length", "0"))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
                self._send(200, relayer.attest(payload))
            except Exception as error:  # noqa: BLE001 - dev server, surface the reason
                self._send(400, {"error": str(error)})

        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("mock-relayer: " + fmt % args + "\n")

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", default=str(ROOT / ".devnet" / "demo-keys.json"))
    ap.add_argument("--network", default="rbridge-devnet")
    ap.add_argument("--bridge-id", default="rbridge:devnet:bridge")
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args()

    keys_path = Path(args.keys)
    if not keys_path.is_file():
        print(f"mock-relayer: missing {keys_path}; run `make demo` first", file=sys.stderr)
        return 2
    relayer = Relayer(json.loads(keys_path.read_text()), args.network, args.bridge_id)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(relayer))
    print(f"mock-relayer: http://127.0.0.1:{args.port} (dev only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
