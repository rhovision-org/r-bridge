// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

interface IMailboxProcessor {
    function processor(bytes32 messageId) external view returns (address);
}

/// @title r-bridge trusted-relayer ISM
/// @notice The EVM analogue of the rholo TrustedRelayerIsm: a message is valid when the
///         configured relayer processed it. The Hyperlane Mailbox calls
///         `recipient.interchainSecurityModule()` and then this module's `verify`, so a
///         paired `HyperlanePeer` needs no Mailbox-default validator set while the rholo
///         agent is still a dev relayer.
/// @dev The module type is NULL (6), matching Hyperlane's TrustedRelayerIsm.
contract RbridgeTrustedRelayerIsm {
    address public immutable mailbox;
    address public immutable relayer;

    constructor(address mailbox_, address relayer_) {
        require(mailbox_ != address(0) && relayer_ != address(0), "address");
        mailbox = mailbox_;
        relayer = relayer_;
    }

    function moduleType() external pure returns (uint8) {
        return 6;
    }

    function verify(bytes calldata, bytes calldata message) external view returns (bool) {
        return IMailboxProcessor(mailbox).processor(keccak256(message)) == relayer;
    }
}
