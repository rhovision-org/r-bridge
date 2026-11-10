// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

/// @title r-bridge Ethereum/TVM vault
/// @notice Locks native assets on the source chain and releases them on an m-of-n
///         relayer attestation over the same canonical digest the rholo contract uses.
///         One vault per chain; asset keys are chain-qualified (`ethereum.usdt`).
/// @dev No proxy, no external dependencies. The relayer and admin sets are fixed at
///      deployment; changing them is a redeploy. This is deliberate for the testnet
///      demo and keeps the trusted surface small.
contract BridgeVault {
    struct AssetInit {
        address token;
        string assetKey;
        uint256 maxDeposit;
        uint256 maxLocked;
        /// Native units per rholo base unit: 1 for 6-decimal assets, 1e10 for 18→8.
        uint256 scale;
        uint256 withdrawFeeBps;
    }

    struct AssetConfig {
        bool enabled;
        uint256 maxDeposit;
        uint256 maxLocked;
        uint256 scale;
        uint256 withdrawFeeBps;
        string assetKey;
    }

    uint256 public immutable chainTag;
    string public network;
    string public chainName;
    string public bridgeId;
    address public immutable treasury;

    bool public paused;
    uint256 public adminNonce;

    address[] public admins;
    mapping(address => bool) public isAdmin;
    uint256 public adminThreshold;

    address[] public relayers;
    mapping(address => bool) public isRelayer;
    uint256 public relayerThreshold;

    mapping(address => AssetConfig) public assets;
    mapping(address => uint256) public locked;
    mapping(address => uint256) public fees;
    mapping(address => mapping(uint256 => bool)) public usedDepositNonce;
    mapping(bytes32 => bool) public usedWithdrawal;
    mapping(bytes32 => bool) public refundedDeposit;

    uint256 private _entered;

    event Deposit(
        bytes32 indexed depositId,
        address indexed token,
        address indexed sender,
        uint256 amount,
        string rholoRecipient,
        uint256 nonce
    );
    event Unlock(
        bytes32 indexed withdrawalId,
        address indexed token,
        address indexed to,
        uint256 grossRholoAmount,
        uint256 grossNativeAmount,
        uint256 fee
    );
    event Paused(bool paused);
    event FeesWithdrawn(address indexed token, address indexed to, uint256 amount);
    event Refund(
        bytes32 indexed depositId, address indexed token, address indexed to, uint256 amount
    );

    modifier nonReentrant() {
        require(_entered == 0, "reentrant");
        _entered = 1;
        _;
        _entered = 0;
    }

    constructor(
        uint256 chainTag_,
        string memory network_,
        string memory chainName_,
        string memory bridgeId_,
        address[] memory admins_,
        uint256 adminThreshold_,
        address[] memory relayers_,
        uint256 relayerThreshold_,
        address treasury_,
        AssetInit[] memory assetInits
    ) {
        require(adminThreshold_ > 0 && adminThreshold_ <= admins_.length, "admin threshold");
        require(relayerThreshold_ > 0 && relayerThreshold_ <= relayers_.length, "relayer threshold");
        require(treasury_ != address(0), "treasury");
        chainTag = chainTag_;
        network = network_;
        chainName = chainName_;
        bridgeId = bridgeId_;
        treasury = treasury_;
        for (uint256 i = 0; i < admins_.length; ++i) {
            address admin = admins_[i];
            require(admin != address(0) && !isAdmin[admin], "admin");
            isAdmin[admin] = true;
            admins.push(admin);
        }
        adminThreshold = adminThreshold_;
        for (uint256 i = 0; i < relayers_.length; ++i) {
            address relayer = relayers_[i];
            require(relayer != address(0) && !isRelayer[relayer], "relayer");
            isRelayer[relayer] = true;
            relayers.push(relayer);
        }
        relayerThreshold = relayerThreshold_;
        for (uint256 i = 0; i < assetInits.length; ++i) {
            AssetInit memory init = assetInits[i];
            require(bytes(init.assetKey).length > 0 && !assets[init.token].enabled, "asset");
            require(init.scale > 0, "scale");
            require(init.withdrawFeeBps <= 10_000, "fee");
            assets[init.token] = AssetConfig({
                enabled: true,
                maxDeposit: init.maxDeposit,
                maxLocked: init.maxLocked,
                scale: init.scale,
                withdrawFeeBps: init.withdrawFeeBps,
                assetKey: init.assetKey
            });
        }
    }

    /// @notice Lock `amount` of `token` and bind it to a rholo recipient.
    /// @dev `token == address(0)` is native ETH; `msg.value` must equal `amount`.
    function lock(address token, uint256 amount, string calldata rholoRecipient, uint256 nonce)
        external
        payable
        nonReentrant
    {
        require(!paused, "paused");
        AssetConfig memory config = assets[token];
        require(config.enabled, "asset");
        require(amount > 0 && amount <= config.maxDeposit, "amount");
        require(amount % config.scale == 0, "scale");
        require(bytes(rholoRecipient).length > 0, "recipient");
        require(!usedDepositNonce[msg.sender][nonce], "nonce");
        usedDepositNonce[msg.sender][nonce] = true;

        if (token == address(0)) {
            require(msg.value == amount, "value");
        } else {
            require(msg.value == 0, "value");
            _safeTransferFrom(token, msg.sender, address(this), amount);
        }

        uint256 newLocked = locked[token] + amount;
        require(newLocked <= config.maxLocked, "max locked");
        locked[token] = newLocked;

        bytes32 depositId = keccak256(
            abi.encode(chainTag, address(this), token, msg.sender, amount, rholoRecipient, nonce)
        );
        emit Deposit(depositId, token, msg.sender, amount, rholoRecipient, nonce);
    }

    /// @notice Release the native equivalent of the rholo burn `grossAmount` on an m-of-n
    ///         relayer attestation.
    /// @dev `grossAmount` is in rholo base units (the burn record's amount). The vault
    ///      converts it with the asset's `scale` and computes the fee in native units.
    function unlock(
        address token,
        address to,
        uint256 grossAmount,
        string calldata withdrawalId,
        uint256 nonce,
        bytes[] calldata signatures
    ) external nonReentrant {
        AssetConfig memory config = assets[token];
        require(config.enabled, "asset");
        require(to != address(0) && grossAmount > 0, "args");
        bytes32 withdrawalKey = keccak256(bytes(withdrawalId));
        require(!usedWithdrawal[withdrawalKey], "withdrawal");
        require(bytes(withdrawalId).length > 0, "withdrawal");
        uint256 grossNative = grossAmount * config.scale;
        require(grossNative / config.scale == grossAmount, "scale");
        require(locked[token] >= grossNative, "locked");

        bytes32 digest = _withdrawalDigest(config.assetKey, to, grossAmount, withdrawalId, nonce);
        _requireThreshold(digest, signatures, relayerThreshold, true);

        uint256 fee = _feeOf(grossNative, config.withdrawFeeBps);
        uint256 net = grossNative - fee;
        usedWithdrawal[withdrawalKey] = true;
        locked[token] -= grossNative;
        if (fee > 0) {
            fees[token] += fee;
        }

        if (token == address(0)) {
            (bool ok,) = to.call{value: net}("");
            require(ok, "eth transfer");
        } else {
            _safeTransfer(token, to, net);
        }
        emit Unlock(withdrawalKey, token, to, grossAmount, grossNative, fee);
    }

    /// @notice 2-of-3-style pause/unpause. The digest matches the rholo admin payload.
    function setPaused(bool value, uint256 nonce, bytes[] calldata signatures) external {
        require(nonce > adminNonce, "replay");
        bytes32 digest = keccak256(
            bytes(
                string.concat(
                    "rbridge:admin:v1|setPaused|", value ? "true" : "false", "|", _toString(nonce)
                )
            )
        );
        _requireThreshold(digest, signatures, adminThreshold, false);
        adminNonce = nonce;
        paused = value;
        emit Paused(value);
    }

    /// @notice 2-of-3 admin refund for a deposit that was never minted on rholo.
    /// @dev The admin set attests the deposit id, token, recipient and amount. The refund
    ///      returns the full locked amount and is one-shot per deposit id. This is the
    ///      recovery path for a deposit the relayer refused (for example below the rholo
    ///      minimum); it deliberately bypasses the withdrawal fee.
    function refund(
        address token,
        address to,
        uint256 amount,
        string calldata depositId,
        uint256 nonce,
        bytes[] calldata signatures
    ) external nonReentrant {
        require(to != address(0) && amount > 0, "args");
        require(bytes(depositId).length > 0, "deposit");
        bytes32 key = keccak256(bytes(depositId));
        require(!refundedDeposit[key], "refunded");
        require(locked[token] >= amount, "locked");
        require(nonce > adminNonce, "replay");
        bytes32 digest = keccak256(
            bytes(
                string.concat(
                    "rbridge:admin:v1|refund|",
                    _toHexAddress(token),
                    "|",
                    _toHexAddress(to),
                    "|",
                    _toString(amount),
                    "|",
                    depositId,
                    "|",
                    _toString(nonce)
                )
            )
        );
        _requireThreshold(digest, signatures, adminThreshold, false);
        adminNonce = nonce;
        refundedDeposit[key] = true;
        locked[token] -= amount;
        if (token == address(0)) {
            (bool ok,) = to.call{value: amount}("");
            require(ok, "eth transfer");
        } else {
            _safeTransfer(token, to, amount);
        }
        emit Refund(key, token, to, amount);
    }

    /// @notice The treasury can withdraw accrued withdrawal fees.
    function withdrawFees(address token, address to, uint256 amount) external nonReentrant {
        require(msg.sender == treasury, "treasury");
        require(to != address(0) && amount <= fees[token], "amount");
        fees[token] -= amount;
        if (token == address(0)) {
            (bool ok,) = to.call{value: amount}("");
            require(ok, "eth transfer");
        } else {
            _safeTransfer(token, to, amount);
        }
        emit FeesWithdrawn(token, to, amount);
    }

    function relayerCount() external view returns (uint256) {
        return relayers.length;
    }

    function adminCount() external view returns (uint256) {
        return admins.length;
    }

    function _withdrawalDigest(
        string memory assetKey,
        address to,
        uint256 grossAmount,
        string calldata withdrawalId,
        uint256 nonce
    ) internal view returns (bytes32) {
        return keccak256(
            bytes(
                string.concat(
                    "rbridge:v1|",
                    network,
                    "|",
                    chainName,
                    "|",
                    bridgeId,
                    "|",
                    assetKey,
                    "|withdraw|",
                    withdrawalId,
                    "|",
                    _toString(grossAmount),
                    "|",
                    _toHexAddress(to),
                    "|",
                    _toString(nonce)
                )
            )
        );
    }

    function _requireThreshold(
        bytes32 digest,
        bytes[] calldata signatures,
        uint256 threshold,
        bool relayerSet
    ) internal view {
        address[] memory seen = new address[](signatures.length);
        uint256 valid;
        for (uint256 i = 0; i < signatures.length; ++i) {
            address signer = _recover(digest, signatures[i]);
            if (signer == address(0)) {
                continue;
            }
            bool member = relayerSet ? isRelayer[signer] : isAdmin[signer];
            if (!member) {
                continue;
            }
            bool duplicate;
            for (uint256 j = 0; j < valid; ++j) {
                if (seen[j] == signer) {
                    duplicate = true;
                    break;
                }
            }
            if (!duplicate) {
                seen[valid] = signer;
                valid += 1;
            }
        }
        require(valid >= threshold, "below threshold");
    }

    /// @dev 65-byte `r || s || v`, low-s only. Returns address(0) for a malformed signature.
    function _recover(bytes32 digest, bytes calldata signature) internal pure returns (address) {
        if (signature.length != 65) {
            return address(0);
        }
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 32))
            v := byte(0, calldataload(add(signature.offset, 64)))
        }
        if (v < 27) {
            v += 27;
        }
        if (v != 27 && v != 28) {
            return address(0);
        }
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            return address(0);
        }
        return ecrecover(digest, v, r, s);
    }

    function _feeOf(uint256 amount, uint256 bps) internal pure returns (uint256) {
        return (amount / 10_000) * bps + ((amount % 10_000) * bps) / 10_000;
    }

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool ok, bytes memory data) = token.call(abi.encodeWithSelector(0xa9059cbb, to, amount));
        require(ok && (data.length == 0 || abi.decode(data, (bool))), "transfer");
    }

    function _safeTransferFrom(address token, address from, address to, uint256 amount) internal {
        (bool ok, bytes memory data) =
            token.call(abi.encodeWithSelector(0x23b872dd, from, to, amount));
        require(ok && (data.length == 0 || abi.decode(data, (bool))), "transferFrom");
    }

    function _toString(uint256 value) internal pure returns (string memory) {
        if (value == 0) {
            return "0";
        }
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) {
            digits++;
            temp /= 10;
        }
        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            digits -= 1;
            buffer[digits] = bytes1(uint8(48 + (value % 10)));
            value /= 10;
        }
        return string(buffer);
    }

    function _toHexAddress(address account) internal pure returns (string memory) {
        bytes16 alphabet = "0123456789abcdef";
        bytes memory out = new bytes(42);
        out[0] = "0";
        out[1] = "x";
        uint160 value = uint160(account);
        for (uint256 i = 0; i < 20; ++i) {
            uint8 byteValue = uint8(value >> (8 * (19 - i)));
            out[2 + 2 * i] = alphabet[byteValue >> 4];
            out[3 + 2 * i] = alphabet[byteValue & 0x0f];
        }
        return string(out);
    }
}
