// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

import {BridgeVault} from "../src/BridgeVault.sol";

interface Vm {
    function addr(uint256 privateKey) external returns (address);
    function sign(uint256 privateKey, bytes32 digest)
        external
        returns (uint8 v, bytes32 r, bytes32 s);
    function prank(address sender) external;
    function deal(address account, uint256 amount) external;
    function expectRevert() external;
}

contract MockERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "balance");
        require(allowance[from][msg.sender] >= amount, "allowance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract BridgeVaultTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    BridgeVault vault;
    MockERC20 token;

    uint256 constant ADMIN1 = 0xA11CE;
    uint256 constant ADMIN2 = 0xB0B;
    uint256 constant ADMIN3 = 0xC0FFEE;
    uint256 constant RELAY1 = 0x1001;
    uint256 constant RELAY2 = 0x1002;
    uint256 constant RELAY3 = 0x1003;

    address admin1;
    address admin2;
    address admin3;
    address relayer1;
    address relayer2;
    address relayer3;
    address user = address(0xBEEF);
    address treasury = address(0x7E45);

    string constant NETWORK = "rbridge-devnet";
    string constant CHAIN = "ethereum";
    string constant BRIDGE_ID = "rbridge:devnet:bridge";
    string constant ASSET_KEY = "ethereum.usdt";
    string constant RHOLO_RECIPIENT = "11112VYAt8rUGNRRZX3eJdgagaAhtWTK8Js7F7X5iqddMVqyDTtYau";

    function setUp() public {
        admin1 = vm.addr(ADMIN1);
        admin2 = vm.addr(ADMIN2);
        admin3 = vm.addr(ADMIN3);
        relayer1 = vm.addr(RELAY1);
        relayer2 = vm.addr(RELAY2);
        relayer3 = vm.addr(RELAY3);

        token = new MockERC20();

        BridgeVault.AssetInit[] memory inits = new BridgeVault.AssetInit[](2);
        inits[0] =
            BridgeVault.AssetInit(address(token), ASSET_KEY, 1_000_000_000, 1_000_000_000_000, 5);
        inits[1] = BridgeVault.AssetInit(
            address(0),
            "ethereum.eth",
            1_000_000_000_000_000_000_000, // 1000 ETH in wei
            1_000_000_000_000_000_000_000_000, // 1,000,000 ETH in wei
            5
        );

        address[] memory admins = new address[](3);
        admins[0] = admin1;
        admins[1] = admin2;
        admins[2] = admin3;
        address[] memory relayers = new address[](3);
        relayers[0] = relayer1;
        relayers[1] = relayer2;
        relayers[2] = relayer3;

        vault = new BridgeVault(
            11155111, NETWORK, CHAIN, BRIDGE_ID, admins, 2, relayers, 2, treasury, inits
        );
        token.mint(address(this), 1_000_000_000);
        vm.deal(address(this), 100 ether);
    }

    function testLockAndUnlockErc20() public {
        uint256 amount = 1_000_000;
        token.approve(address(vault), amount);
        vault.lock(address(token), amount, RHOLO_RECIPIENT, 1);
        assertEq(vault.locked(address(token)), amount);

        string memory withdrawalId = "demo-withdrawal-1";
        bytes32 digest = _withdrawDigest(ASSET_KEY, user, amount, withdrawalId, 0);
        bytes[] memory sigs = new bytes[](2);
        sigs[0] = _sig(RELAY1, digest);
        sigs[1] = _sig(RELAY2, digest);

        vault.unlock(address(token), user, amount, withdrawalId, 0, sigs);

        uint256 fee = 500; // 5 bps of 1,000,000
        assertEq(token.balanceOf(user), amount - fee);
        assertEq(vault.fees(address(token)), fee);
        assertEq(vault.locked(address(token)), 0);
        assertTrue(vault.usedWithdrawal(keccak256(bytes(withdrawalId))));

        vm.expectRevert();
        vault.unlock(address(token), user, amount, withdrawalId, 0, sigs);
    }

    function testBelowThresholdIsRefused() public {
        uint256 amount = 1_000_000;
        token.approve(address(vault), amount);
        vault.lock(address(token), amount, RHOLO_RECIPIENT, 1);
        bytes32 digest = _withdrawDigest(ASSET_KEY, user, amount, "wd", 0);
        bytes[] memory sigs = new bytes[](1);
        sigs[0] = _sig(RELAY1, digest);

        vm.expectRevert();
        vault.unlock(address(token), user, amount, "wd", 0, sigs);
    }

    function testDuplicateSignerDoesNotCountTwice() public {
        uint256 amount = 1_000_000;
        token.approve(address(vault), amount);
        vault.lock(address(token), amount, RHOLO_RECIPIENT, 1);
        bytes32 digest = _withdrawDigest(ASSET_KEY, user, amount, "wd", 0);
        bytes[] memory sigs = new bytes[](2);
        sigs[0] = _sig(RELAY1, digest);
        sigs[1] = _sig(RELAY1, digest);

        vm.expectRevert();
        vault.unlock(address(token), user, amount, "wd", 0, sigs);
    }

    function testWrongDigestIsRefused() public {
        uint256 amount = 1_000_000;
        token.approve(address(vault), amount);
        vault.lock(address(token), amount, RHOLO_RECIPIENT, 1);
        bytes32 digest = _withdrawDigest(ASSET_KEY, user, amount + 1, "wd", 0);
        bytes[] memory sigs = new bytes[](2);
        sigs[0] = _sig(RELAY1, digest);
        sigs[1] = _sig(RELAY2, digest);

        vm.expectRevert();
        vault.unlock(address(token), user, amount, "wd", 0, sigs);
    }

    function testPauseBlocksLockButNotUnlock() public {
        uint256 amount = 1_000_000;
        token.approve(address(vault), amount);
        vault.lock(address(token), amount, RHOLO_RECIPIENT, 1);

        bytes[] memory adminSigs = new bytes[](2);
        adminSigs[0] = _sig(ADMIN1, _adminDigest(true, 1));
        adminSigs[1] = _sig(ADMIN2, _adminDigest(true, 1));
        vault.setPaused(true, 1, adminSigs);
        assertTrue(vault.paused());

        vm.expectRevert();
        vault.lock(address(token), amount, RHOLO_RECIPIENT, 2);

        // Unlock remains available during a pause.
        bytes32 digest = _withdrawDigest(ASSET_KEY, user, amount, "wd-paused", 0);
        bytes[] memory sigs = new bytes[](2);
        sigs[0] = _sig(RELAY1, digest);
        sigs[1] = _sig(RELAY2, digest);
        vault.unlock(address(token), user, amount, "wd-paused", 0, sigs);
    }

    function testAdminThreshold() public {
        bytes[] memory one = new bytes[](1);
        one[0] = _sig(ADMIN1, _adminDigest(true, 1));
        vm.expectRevert();
        vault.setPaused(true, 1, one);

        bytes[] memory two = new bytes[](2);
        two[0] = _sig(ADMIN1, _adminDigest(true, 1));
        two[1] = _sig(ADMIN3, _adminDigest(true, 1));
        vault.setPaused(true, 1, two);
        assertTrue(vault.paused());

        vm.expectRevert();
        vault.setPaused(false, 1, two); // replay
    }

    function testMaxDepositAndNonceReplay() public {
        bytes[] memory adminSigs = new bytes[](2);
        adminSigs[0] = _sig(ADMIN1, _adminDigest(false, 1));
        adminSigs[1] = _sig(ADMIN2, _adminDigest(false, 1));
        vault.setPaused(false, 1, adminSigs); // no-op pause false, consumes nonce

        uint256 tooMuch = 1_000_000_001; // maxDeposit is 1,000,000,000
        vm.expectRevert();
        vault.lock(address(token), tooMuch, RHOLO_RECIPIENT, 1);

        uint256 amount = 1_000_000;
        token.approve(address(vault), amount);
        vault.lock(address(token), amount, RHOLO_RECIPIENT, 7);
        token.approve(address(vault), amount);
        vm.expectRevert();
        vault.lock(address(token), amount, RHOLO_RECIPIENT, 7);
    }

    function testEthLockAndUnlockWithFeeWithdrawal() public {
        uint256 amount = 1 ether;
        vault.lock{value: amount}(address(0), amount, RHOLO_RECIPIENT, 1);
        assertEq(vault.locked(address(0)), amount);

        string memory withdrawalId = "eth-withdrawal";
        bytes32 digest = _withdrawDigest("ethereum.eth", user, amount, withdrawalId, 0);
        bytes[] memory sigs = new bytes[](2);
        sigs[0] = _sig(RELAY1, digest);
        sigs[1] = _sig(RELAY2, digest);
        vault.unlock(address(0), user, amount, withdrawalId, 0, sigs);

        uint256 fee = (amount / 10_000) * 5;
        assertEq(user.balance, amount - fee);
        assertEq(vault.fees(address(0)), fee);

        vm.prank(treasury);
        vault.withdrawFees(address(0), treasury, fee);
        assertEq(treasury.balance, fee);
        assertEq(vault.fees(address(0)), 0);
    }

    function testWithdrawalDigestMatchesRustGolden() public pure {
        bytes32 digest =
            _withdrawDigest("ethereum.usdt", address(0xBEEF), 1_000_000, "demo-withdrawal-1", 0);
        assertEq(
            uint256(digest),
            uint256(0xd2f0ca0220d37d6a5cb5f3061140f864b967f6d7fe3596f1f330faeba263e805)
        );
    }

    function _sig(uint256 privateKey, bytes32 digest) internal returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(privateKey, digest);
        return abi.encodePacked(r, s, v);
    }

    function _withdrawDigest(
        string memory assetKey,
        address to,
        uint256 gross,
        string memory withdrawalId,
        uint256 nonce
    ) internal pure returns (bytes32) {
        return keccak256(
            bytes(
                string.concat(
                    "rbridge:v1|",
                    NETWORK,
                    "|",
                    CHAIN,
                    "|",
                    BRIDGE_ID,
                    "|",
                    assetKey,
                    "|withdraw|",
                    withdrawalId,
                    "|",
                    _toString(gross),
                    "|",
                    _toHexAddress(to),
                    "|",
                    _toString(nonce)
                )
            )
        );
    }

    function _adminDigest(bool value, uint256 nonce) internal pure returns (bytes32) {
        return keccak256(
            bytes(
                string.concat(
                    "rbridge:admin:v1|setPaused|", value ? "true" : "false", "|", _toString(nonce)
                )
            )
        );
    }

    function _toString(uint256 value) internal pure returns (string memory) {
        if (value == 0) return "0";
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
        out[0] = 0x30;
        out[1] = 0x78;
        uint160 value = uint160(account);
        for (uint256 i = 0; i < 20; ++i) {
            uint8 byteValue = uint8(value >> (8 * (19 - i)));
            out[2 + 2 * i] = alphabet[byteValue >> 4];
            out[3 + 2 * i] = alphabet[byteValue & 0x0f];
        }
        return string(out);
    }

    function assertTrue(bool value) internal pure {
        require(value, "assertTrue failed");
    }

    function assertEq(uint256 a, uint256 b) internal pure {
        require(a == b, "assertEq uint failed");
    }
}
