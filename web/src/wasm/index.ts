import init, {
  RholoClient,
  RholoKey,
  keystore_create,
  keystore_unlock,
} from "./pkg/rbridge_wasm.js";

export { RholoClient, RholoKey, keystore_create, keystore_unlock };

let ready: Promise<void> | null = null;

/**
 * Initialize the WASM module once. Tests may pass the built bytes explicitly; in the
 * browser the generated glue fetches `rbridge_wasm_bg.wasm` next to the bundle.
 */
export function initWasm(bytes?: BufferSource): Promise<void> {
  if (!ready) {
    ready = (bytes ? init(bytes) : init()).then(() => undefined);
  }
  return ready;
}
