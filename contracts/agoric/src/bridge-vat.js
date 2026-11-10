// r-bridge Agoric-side escrow vat.
//
// Holds an external asset (the IBC denom represented by the Collateral issuer) in a
// contract-owned Zoe seat. A deposit invitation records the amount and rholo recipient
// for the relayer to attest. A release invitation verifies the m-of-n relayer
// attestation over the canonical withdrawal digest and pays the escrowed asset to the
// recipient.
//
// The canonical digest is shared with rholo and the EVM vault:
//   rbridge:v1|<network>|agoric|<bridgeId>|<assetKey>|withdraw|
//   <withdrawalId>|<amount>|<recipient>|<nonce>
// Signatures are compact 64-byte secp256k1 over keccak256(utf8(message)). The relayer
// emits compact for this chain; rholo uses DER and the EVM vault uses r||s||v over the
// same digest.
//
// This is a demo vat: deposits and used ids live in closure Maps (not durable stores),
// and the release invitation is a bearer capability delivered to the recipient. A
// production vat uses baggage stores and an account/address binding for the recipient.

import { AmountMath } from '@agoric/ertp';
import { Far } from '@endo/far';
import * as secp256k1 from '@noble/secp256k1';
import { keccak_256 } from '@noble/hashes/sha3.js';

const fail = message => {
  throw Error(message);
};

const hexToBytes = hex => {
  typeof hex === 'string' || fail('hex must be a string');
  /^[0-9a-fA-F]*$/.test(hex) && hex.length % 2 === 0 || fail('invalid hex');
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
};

/**
 * @param {ZCF} zcf
 */
export const start = (zcf, _privateArgs, _baggage) => {
  const terms = zcf.getTerms();
  const collateralBrand = terms.brands.Collateral;
  const { network, bridgeId, assetKey, relayers, relayerThreshold } = terms;

  typeof network === 'string' && network.length > 0 || fail('network');
  typeof bridgeId === 'string' && bridgeId.length > 0 || fail('bridge id');
  typeof assetKey === 'string' && assetKey.length > 0 || fail('asset key');
  Array.isArray(relayers) && relayers.length > 0 || fail('relayers');
  relayerThreshold > 0 && relayerThreshold <= relayers.length || fail('threshold');

  const normalisedRelayers = relayers.map(key => key.toLowerCase());
  const { zcfSeat: escrowSeat } = zcf.makeEmptySeatKit();
  const deposits = new Map();
  const usedWithdrawals = new Set();
  let sequence = 0;

  const verifyThreshold = (message, signatures) => {
    const digest = keccak_256(new TextEncoder().encode(message));
    const seen = new Set();
    let valid = 0;
    for (const signatureHex of signatures) {
      const signature = hexToBytes(signatureHex);
      for (const relayer of normalisedRelayers) {
        if (seen.has(relayer)) continue;
        if (
          secp256k1.verify(signature, digest, hexToBytes(relayer), {
            prehash: false,
          })
        ) {
          seen.add(relayer);
          valid += 1;
        }
      }
    }
    return valid >= relayerThreshold;
  };

  const publicFacet = Far('BridgeVat', {
    makeDepositInvitation(rholoRecipient) {
      typeof rholoRecipient === 'string' && rholoRecipient.length > 0 || fail('recipient');
      return zcf.makeInvitation(
        seat => {
          const amount = seat.getCurrentAllocation().Collateral;
          amount && amount.value > 0n || fail('amount');
          zcf.atomicRearrange(harden([[seat, escrowSeat, { Collateral: amount }]]));
          seat.exit();
          sequence += 1;
          const depositId = `agoric-deposit-${sequence}`;
          const record = harden({ depositId, amount, rholoRecipient });
          deposits.set(depositId, record);
          return record;
        },
        'deposit',
        harden({ rholoRecipient }),
      );
    },

    makeReleaseInvitation({ withdrawalId, amountValue, recipient, nonce = 0, signatures }) {
      typeof withdrawalId === 'string' && withdrawalId.length > 0 || fail('withdrawal id');
      typeof recipient === 'string' && recipient.length > 0 || fail('recipient');
      typeof amountValue === 'bigint' && amountValue > 0n || fail('amount');
      Array.isArray(signatures) || fail('signatures');
      !usedWithdrawals.has(withdrawalId) || fail('withdrawal already used');

      const message = `rbridge:v1|${network}|agoric|${bridgeId}|${assetKey}|withdraw|${withdrawalId}|${amountValue}|${recipient}|${nonce}`;
      verifyThreshold(message, signatures) || fail('below threshold');

      const amount = AmountMath.make(collateralBrand, amountValue);
      const escrow = escrowSeat.getAmountAllocated('Collateral', collateralBrand);
      AmountMath.isGTE(escrow, amount) || fail('insufficient escrow');

      return zcf.makeInvitation(
        seat => {
          !usedWithdrawals.has(withdrawalId) || fail('withdrawal already used');
          zcf.atomicRearrange(harden([[escrowSeat, seat, { Collateral: amount }]]));
          usedWithdrawals.add(withdrawalId);
          seat.exit();
          return harden({ withdrawalId, amount, recipient });
        },
        'release',
        harden({ withdrawalId, amount, recipient }),
      );
    },

    getDeposits() {
      return harden([...deposits.values()]);
    },

    getRelayerConfig() {
      return harden({ relayers: normalisedRelayers, relayerThreshold });
    },
  });

  return harden({ publicFacet });
};

harden(start);
