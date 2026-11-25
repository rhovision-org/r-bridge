// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

interface IMockMessageRecipient {
    function handle(uint32 origin, bytes32 sender, bytes calldata body) external payable;
}

interface IMockIsm {
    function verify(bytes calldata metadata, bytes calldata message) external view returns (bool);
}

interface IMockIsmRecipient {
    function interchainSecurityModule() external view returns (address);
}

/// @notice A local Hyperlane Mailbox for the Anvil demos. It speaks the canonical message
///         format and dispatch/process shape, stores dispatched messages for the relayer,
///         and honours a recipient's application ISM. It is not a production Mailbox: it
///         does not implement hooks, gas payment, or the default validator ISM.
contract MockHyperlaneMailbox {
    uint32 public immutable localDomain;
    uint32 public nonce;
    bytes32 public latestDispatchedId;

    mapping(bytes32 => bytes) public dispatched;
    mapping(bytes32 => bool) public delivered;
    mapping(bytes32 => address) public processor;
    address public defaultIsm;

    event Dispatch(address indexed sender, uint32 indexed destination, bytes32 indexed recipient, bytes message);
    event Process(uint32 indexed origin, bytes32 indexed sender, address indexed recipient);
    event IsmSet(address ism);

    constructor(uint32 localDomain_) {
        localDomain = localDomain_;
    }

    function setDefaultIsm(address ism) external {
        defaultIsm = ism;
        emit IsmSet(ism);
    }

    function dispatch(uint32 destination, bytes32 recipient, bytes calldata body)
        external
        payable
        returns (bytes32 messageId)
    {
        bytes memory message = abi.encodePacked(
            uint8(3),
            nonce,
            localDomain,
            bytes32(uint256(uint160(msg.sender))),
            destination,
            recipient,
            body
        );
        messageId = keccak256(message);
        latestDispatchedId = messageId;
        nonce = nonce + 1;
        dispatched[messageId] = message;
        emit Dispatch(msg.sender, destination, recipient, message);
    }

    function quoteDispatch(uint32, bytes32, bytes calldata) external pure returns (uint256) {
        return 0;
    }

    function process(bytes calldata metadata, bytes calldata message) external payable {
        require(message.length >= 77 && uint8(message[0]) == 3, "version");
        uint32 destination = _uint32(message, 41);
        require(destination == localDomain, "destination");
        bytes32 id = keccak256(message);
        require(!delivered[id], "already delivered");

        uint32 origin = _uint32(message, 5);
        bytes32 sender = _bytes32(message, 9);
        bytes32 recipientWord = _bytes32(message, 45);
        address recipient = address(uint160(uint256(recipientWord)));

        processor[id] = msg.sender;
        address ism = _recipientIsm(recipient);
        if (ism == address(0)) {
            ism = defaultIsm;
        }
        if (ism != address(0)) {
            require(IMockIsm(ism).verify(metadata, message), "ism");
        }
        delivered[id] = true;
        bytes calldata body = message[77:];
        IMockMessageRecipient(recipient).handle{value: msg.value}(origin, sender, body);
        emit Process(origin, sender, recipient);
    }

    function _recipientIsm(address recipient) internal view returns (address ism) {
        (bool ok, bytes memory data) = recipient.staticcall(
            abi.encodeWithSelector(IMockIsmRecipient.interchainSecurityModule.selector)
        );
        if (!ok || data.length < 32) {
            return address(0);
        }
        ism = address(uint160(uint256(bytes32(data))));
    }

    function _uint32(bytes calldata data, uint256 offset) internal pure returns (uint32) {
        return uint32(bytes4(data[offset:offset + 4]));
    }

    function _bytes32(bytes calldata data, uint256 offset) internal pure returns (bytes32) {
        return bytes32(data[offset:offset + 32]);
    }
}
