// Agoric's ava wrapper currently has an Endo/ava version mismatch in this checkout,
// so this test uses the plain SwingSet test environment and Node's assert. The
// behaviour under test is the same; run with `npm test`.
import '@agoric/swingset-liveslots/tools/prepare-test-env.js';

import assert from 'node:assert/strict';
import { AmountMath, makeIssuerKit } from '@agoric/ertp';
import { makeZoeKitForTest } from '@agoric/zoe/tools/setup-zoe.js';
import bundleSource from '@endo/bundle-source';
import { E } from '@endo/far';
import * as secp256k1 from '@noble/secp256k1';
import { keccak_256 } from '@noble/hashes/sha3.js';
import { hmac } from '@noble/hashes/hmac.js';
import { sha256 } from '@noble/hashes/sha2.js';

secp256k1.hashes.hmacSha256 = (key, message) => hmac(sha256, key, message);

const { zoeService: zoe } = makeZoeKitForTest();

const bytesToHex = bytes =>
  Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');

const secrets = [1, 2, 3].map(value => new Uint8Array(32).fill(value));
const pubkeys = secrets.map(secret => bytesToHex(secp256k1.getPublicKey(secret, false)));

const NETWORK = 'rbridge-devnet';
const BRIDGE_ID = 'rbridge:devnet:bridge';
const ASSET_KEY = 'agoric.usdc';

const digestFor = (withdrawalId, amount, recipient, nonce = 0) =>
  keccak_256(
    new TextEncoder().encode(
      `rbridge:v1|${NETWORK}|agoric|${BRIDGE_ID}|${ASSET_KEY}|withdraw|${withdrawalId}|${amount}|${recipient}|${nonce}`,
    ),
  );

const sign = (secret, digest) =>
  bytesToHex(secp256k1.sign(digest, secret, { prehash: false }));

const makeBridge = async () => {
  const kit = makeIssuerKit('USDC');
  const bundle = await bundleSource(
    new URL('../src/bridge-vat.js', import.meta.url).pathname,
  );
  const installation = await E(zoe).install(bundle);
  const terms = {
    Collateral: kit.issuer,
    network: NETWORK,
    bridgeId: BRIDGE_ID,
    assetKey: ASSET_KEY,
    relayers: pubkeys,
    relayerThreshold: 2,
  };
  const { instance } = await E(zoe).startInstance(
    installation,
    harden({ Collateral: kit.issuer }),
    terms,
  );
  const publicFacet = await E(zoe).getPublicFacet(instance);
  return { ...kit, publicFacet };
};

const deposit = async ({ mint, brand, publicFacet }, amountValue) => {
  const amount = AmountMath.make(brand, amountValue);
  const invitation = await E(publicFacet).makeDepositInvitation('1111rholo');
  const seat = await E(zoe).offer(
    invitation,
    harden({ give: { Collateral: amount } }),
    harden({ Collateral: mint.mintPayment(amount) }),
  );
  return E(seat).getOfferResult();
};

const scenarioRelease = async () => {
  const kit = await makeBridge();
  const record = await deposit(kit, 1_000_000n);
  assert.equal(record.rholoRecipient, '1111rholo');
  assert.equal((await E(kit.publicFacet).getDeposits()).length, 1);

  const value = 400_000n;
  const recipient = 'agoric1recipient';
  const digest = digestFor('w1', value, recipient);
  const signatures = secrets.slice(0, 2).map(secret => sign(secret, digest));

  const invitation = await E(kit.publicFacet).makeReleaseInvitation({
    withdrawalId: 'w1',
    amountValue: value,
    recipient,
    nonce: 0,
    signatures,
  });
  const seat = await E(zoe).offer(
    invitation,
    harden({ want: { Collateral: AmountMath.make(kit.brand, value) } }),
  );
  const payout = await E(seat).getPayout('Collateral');
  const purse = await E(kit.issuer).makeEmptyPurse();
  const paid = await E(purse).deposit(payout);
  assert.equal(paid.value, value);

  await assert.rejects(() =>
    E(kit.publicFacet).makeReleaseInvitation({
      withdrawalId: 'w1',
      amountValue: value,
      recipient,
      nonce: 0,
      signatures,
    }),
  );
  console.log('PASS  deposit escrow, 2-of-3 release, replay refusal');
};

const scenarioRefusals = async () => {
  const kit = await makeBridge();
  await deposit(kit, 1_000_000n);

  const value = 100_000n;
  const recipient = 'agoric1recipient';
  const digest = digestFor('w2', value, recipient);

  await assert.rejects(() =>
    E(kit.publicFacet).makeReleaseInvitation({
      withdrawalId: 'w2',
      amountValue: value,
      recipient,
      nonce: 0,
      signatures: [sign(secrets[0], digest)],
    }),
  );

  const wrong = digestFor('w2', value + 1n, recipient);
  await assert.rejects(() =>
    E(kit.publicFacet).makeReleaseInvitation({
      withdrawalId: 'w2',
      amountValue: value,
      recipient,
      nonce: 0,
      signatures: secrets.slice(0, 2).map(secret => sign(secret, wrong)),
    }),
  );
  console.log('PASS  below-threshold and wrong-digest refusals');
};

await scenarioRelease();
await scenarioRefusals();
console.log('agoric vat: PASS');
