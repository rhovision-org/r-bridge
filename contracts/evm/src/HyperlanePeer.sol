// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

/// @title r-bridge Hyperlane peer
/// @notice A single-asset Hyperlane endpoint for the r-bridge canonical payload. It locks
///         an ERC-20 on this chain and dispatches a v3 message; an inbound message with a
///         `withdraw` payload releases the asset. It is deliberately standalone: the
///         attested `BridgeVault` is unchanged, so the two rails can be compared.
/// @dev Interfaces are declared locally so the contract has no external dependencies.
interface IMailbox {
    function dispatch(uint32 destinationDomain, bytes32 recipientAddress, bytes calldata body)
        external
        payable
        returns (bytes32 messageId);
}

interface IMessageRecipient {
    function handle(uint32 origin, bytes32 sender, bytes calldata body) external payable;
}

contract HyperlanePeer is IMessageRecipient {
    address public immutable mailbox;
    uint32 public immutable localDomain;
    uint32 public immutable remoteDomain;
    bytes32 public immutable remotePeer;
    address public immutable token;
    string public assetKey;
    uint256 public immutable scale;
    uint256 public immutable maxDeposit;
    uint256 public immutable maxLocked;
    address public immutable owner;

    bool public paused;
    uint256 public nonce;
    uint256 public locked;
    mapping(bytes32 => bool) public usedWithdrawal;
    uint256 private _entered;

    event DepositDispatched(
        bytes32 indexed messageId,
        address indexed sender,
        uint256 amount,
        uint256 rholoAmount,
        string rholoRecipient,
        uint256 nonce
    );
    event Released(
        bytes32 indexed withdrawalKey,
        address indexed token,
        address indexed to,
        uint256 rholoAmount,
        uint256 nativeAmount
    );
    event Paused(bool paused);

    modifier nonReentrant() {
        require(_entered == 0, "reentrant");
        _entered = 1;
        _;
        _entered = 0;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "owner");
        _;
    }

    constructor(
        address mailbox_,
        uint32 localDomain_,
        uint32 remoteDomain_,
        bytes32 remotePeer_,
        address token_,
        string memory assetKey_,
        uint256 scale_,
        uint256 maxDeposit_,
        uint256 maxLocked_,
        address owner_
    ) {
        require(mailbox_ != address(0) && token_ != address(0), "address");
        require(remotePeer_ != bytes32(0) && owner_ != address(0), "peer");
        require(bytes(assetKey_).length > 0 && scale_ > 0, "config");
        mailbox = mailbox_;
        localDomain = localDomain_;
        remoteDomain = remoteDomain_;
        remotePeer = remotePeer_;
        token = token_;
        assetKey = assetKey_;
        scale = scale_;
        maxDeposit = maxDeposit_;
        maxLocked = maxLocked_;
        owner = owner_;
    }

    /// @notice Lock `amount` (native base units) and dispatch the canonical deposit payload.
    function lock(uint256 amount, string calldata rholoRecipient) external nonReentrant returns (bytes32) {
        require(!paused, "paused");
        require(amount > 0 && amount <= maxDeposit, "amount");
        require(amount % scale == 0, "scale");
        require(bytes(rholoRecipient).length > 0, "recipient");
        uint256 rholoAmount = amount / scale;

        uint256 newLocked = locked + amount;
        require(newLocked <= maxLocked, "max locked");
        locked = newLocked;
        _safeTransferFrom(token, msg.sender, address(this), amount);

        uint256 depositNonce = nonce;
        nonce = depositNonce + 1;
        bytes32 depositId = keccak256(abi.encode(block.chainid, address(this), msg.sender, depositNonce));
        string memory payload = string.concat(
            "rbridge:hyperlane:v1|deposit|",
            assetKey,
            "|",
            _toString(rholoAmount),
            "|",
            rholoRecipient,
            "|",
            _toHex(depositId),
            "|",
            _toString(depositNonce)
        );
        bytes32 messageId = IMailbox(mailbox).dispatch(remoteDomain, remotePeer, bytes(payload));
        emit DepositDispatched(messageId, msg.sender, amount, rholoAmount, rholoRecipient, depositNonce);
        return messageId;
    }

    /// @notice Release collateral for an inbound `withdraw` payload.
    function handle(uint32 origin, bytes32 sender, bytes calldata body) external payable nonReentrant {
        require(msg.sender == mailbox, "mailbox");
        require(origin == remoteDomain && sender == remotePeer, "peer");

        bytes[] memory parts = _split(body, 7);
        require(_eq(parts[0], "rbridge:hyperlane:v1"), "tag");
        require(_eq(parts[1], "withdraw"), "action");
        require(_eq(parts[2], assetKey), "asset");
        uint256 rholoAmount = _parseUint(parts[3]);
        require(rholoAmount > 0, "amount");
        address to = _parseAddress(parts[4]);
        bytes32 withdrawalKey = keccak256(parts[5]);
        require(!usedWithdrawal[withdrawalKey], "withdrawal");
        usedWithdrawal[withdrawalKey] = true;
        _parseUint(parts[6]); // nonce is part of the authenticated string

        uint256 nativeAmount = rholoAmount * scale;
        require(nativeAmount / scale == rholoAmount, "scale");
        require(locked >= nativeAmount, "locked");
        locked -= nativeAmount;
        _safeTransfer(token, to, nativeAmount);
        emit Released(withdrawalKey, token, to, rholoAmount, nativeAmount);
    }

    function setPaused(bool value) external onlyOwner {
        paused = value;
        emit Paused(value);
    }

    function _split(bytes memory data, uint256 expected) internal pure returns (bytes[] memory parts) {
        parts = new bytes[](expected);
        uint256 count;
        uint256 start;
        for (uint256 i = 0; i <= data.length; ++i) {
            if (i == data.length || data[i] == 0x7c) {
                require(count < expected, "parts");
                bytes memory part = new bytes(i - start);
                for (uint256 j = 0; j < part.length; ++j) {
                    part[j] = data[start + j];
                }
                parts[count] = part;
                ++count;
                start = i + 1;
            }
        }
        require(count == expected, "parts");
    }

    function _eq(bytes memory a, string memory b) internal pure returns (bool) {
        return keccak256(a) == keccak256(bytes(b));
    }

    function _parseUint(bytes memory b) internal pure returns (uint256 value) {
        require(b.length > 0 && b.length <= 77, "uint");
        for (uint256 i = 0; i < b.length; ++i) {
            require(b[i] >= 0x30 && b[i] <= 0x39, "digit");
            value = value * 10 + (uint256(uint8(b[i])) - 0x30);
        }
    }

    function _parseAddress(bytes memory b) internal pure returns (address out) {
        require(b.length == 42 && b[0] == 0x30 && (b[1] == 0x78 || b[1] == 0x58), "address");
        uint160 value;
        for (uint256 i = 2; i < 42; ++i) {
            value = (value << 4) | _hexNibble(b[i]);
        }
        out = address(value);
    }

    function _hexNibble(bytes1 c) internal pure returns (uint8) {
        uint8 v = uint8(c);
        if (v >= 0x30 && v <= 0x39) return v - 0x30;
        if (v >= 0x61 && v <= 0x66) return v - 0x57;
        if (v >= 0x41 && v <= 0x46) return v - 0x37;
        revert("hex");
    }

    function _toHex(bytes32 value) internal pure returns (string memory) {
        bytes16 alphabet = "0123456789abcdef";
        bytes memory out = new bytes(64);
        for (uint256 i = 0; i < 32; ++i) {
            uint8 byteValue = uint8(value[i]);
            out[2 * i] = alphabet[byteValue >> 4];
            out[2 * i + 1] = alphabet[byteValue & 0x0f];
        }
        return string(out);
    }

    function _toString(uint256 value) internal pure returns (string memory) {
        if (value == 0) return "0";
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) {
            ++digits;
            temp /= 10;
        }
        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            --digits;
            buffer[digits] = bytes1(uint8(48 + (value % 10)));
            value /= 10;
        }
        return string(buffer);
    }

    function _safeTransfer(address token_, address to, uint256 amount) internal {
        (bool ok, bytes memory data) = token_.call(abi.encodeWithSelector(0xa9059cbb, to, amount));
        require(ok && (data.length == 0 || abi.decode(data, (bool))), "transfer");
    }

    function _safeTransferFrom(address token_, address from, address to, uint256 amount) internal {
        (bool ok, bytes memory data) = token_.call(abi.encodeWithSelector(0x23b872dd, from, to, amount));
        require(ok && (data.length == 0 || abi.decode(data, (bool))), "transferFrom");
    }
}
