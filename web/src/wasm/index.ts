import init, { RholoClient, RholoKey } from "./pkg/rbridge_wasm.js";

export { RholoClient, RholoKey };

let ready: Promise<void> | null = null;

export function initWasm(): Promise<void> {
  if (!ready) {
    ready = init().then(() => undefined);
  }
  return ready;
}
