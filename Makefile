SHELL := /bin/bash
PY ?= python3
RHOLO_DIR ?= ../RNodeRust
NODE ?= http://localhost:40403
FORGE ?= $(HOME)/.foundry/bin/forge

.PHONY: fmt clippy test wasm rust-check build-contracts contracts-check evm-test evm-build agoric-install agoric-test web-install web-check web-e2e docs docs-check check clean devnet-up devnet-down demo mock-relayer e2e-evm relayer-watch refund-failed reorg-demo

fmt:
	cargo fmt --all --check

clippy:
	cargo clippy --workspace --all-targets -- -D warnings

test:
	cargo test --workspace

wasm:
	cargo check -p rbridge-wasm --target wasm32-unknown-unknown

rust-check: fmt clippy test wasm

build-contracts:
	python3 tools/build_contracts.py

contracts-check:
	python3 tools/build_contracts.py --check

evm-build:
	$(FORGE) build --root contracts/evm

evm-test:
	$(FORGE) test --root contracts/evm -vv

agoric-install:
	npm --prefix contracts/agoric ci --legacy-peer-deps

agoric-test:
	npm --prefix contracts/agoric test

web-install:
	npm --prefix web install

web-check: web-install
	npm --prefix web run typecheck
	npm --prefix web run test
	npm --prefix web run build

web-e2e: web-install
	npm --prefix web run test:e2e

docs:
	cd docs && mdbook build

docs-check:
	cd docs && mdbook build

# Local demo rails. The rholo devnet is Docker-based and lives in RHOLO_DIR.
devnet-up:
	cd $(RHOLO_DIR) && DEVNET_NODE_MEMORY=8g tools/devnet.sh up --validators 1

devnet-down:
	cd $(RHOLO_DIR) && tools/devnet.sh down

demo: build-contracts
	cargo build -p rbridge-cli
	$(PY) harness/demo.py

mock-relayer:
	$(PY) harness/mock_relayer.py

# Requires Anvil on :8545 and a rholo devnet with a bridge installed (`make demo`).
e2e-evm:
	$(PY) harness/e2e_evm.py

# Dev watcher loop; start before locking. Requires the e2e rails.
relayer-watch:
	$(PY) -u harness/dev_relayer.py

refund-failed:
	$(PY) harness/evm_refund.py

reorg-demo:
	$(PY) harness/reorg_demo.py

check: rust-check contracts-check evm-test web-check docs-check

clean:
	cargo clean
	rm -rf web/node_modules web/dist docs/book
