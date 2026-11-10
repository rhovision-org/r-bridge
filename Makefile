SHELL := /bin/bash

.PHONY: fmt clippy test wasm rust-check web-install web-check web-e2e docs docs-check check clean

fmt:
	cargo fmt --all --check

clippy:
	cargo clippy --workspace --all-targets -- -D warnings

test:
	cargo test --workspace

wasm:
	cargo check -p rbridge-wasm --target wasm32-unknown-unknown

rust-check: fmt clippy test wasm

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

check: rust-check web-check docs-check

clean:
	cargo clean
	rm -rf web/node_modules web/dist docs/book
