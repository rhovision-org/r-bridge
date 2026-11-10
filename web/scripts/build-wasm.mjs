import { execFileSync } from "node:child_process";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const crate = resolve(root, "crates/rbridge-wasm");
const outDir = resolve(root, "web/src/wasm/pkg");

execFileSync(
  "wasm-pack",
  ["build", crate, "--target", "web", "--release", "--out-dir", relative(crate, outDir)],
  { cwd: root, stdio: "inherit" },
);
