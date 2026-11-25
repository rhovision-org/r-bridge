// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

import {HyperlanePeer, IMessageRecipient} from "../src/HyperlanePeer.sol";
import {RbridgeTrustedRelayerIsm} from "../src/RbridgeTrustedRelayerIsm.sol";
import {MockERC20} from "../src/MockERC20.sol";

interface Vm {
    function prank(address sender) external;
    function expectRevert() external;
}

contract MockMailbox {
    struct Message {
        uint32 destination;
        bytes32 recipient;
        bytes body;
        bytes32 id;
    }

    Message[] public messages;

    function dispatch(uint32 destination, bytes32 recipient, bytes calldata body)
        external
        payable
        returns (bytes32)
    {
        bytes32 id = keccak256(abi.encodePacked(destination, recipient, body));
        messages.push(Message(destination, recipient, body, id));
        return id;
    }

    function quoteDispatch(uint32, bytes32, bytes calldata) external pure returns (uint256) {
        return 0;
    }

    function deliver(address recipient, uint32 origin, bytes32 sender, bytes calldata body)
        external
        payable
    {
        IMessageRecipient(recipient).handle{value: msg.value}(origin, sender, body);
    }

    function count() external view returns (uint256) {
        return messages.length;
    }

    function last() external view returns (uint32, bytes32, bytes memory) {
        Message storage message = messages[messages.length - 1];
        return (message.destination, message.recipient, message.body);
    }
}

contract MockProcessorMailbox {
    mapping(bytes32 => address) public processor;

    function setProcessor(bytes32 id, address relayer) external {
        processor[id] = relayer;
    }
}

contract HyperlanePeerTest {
    Vm constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);

    MockMailbox mailbox;
    MockERC20 usdt;
    MockERC20 usdc;
    HyperlanePeer peer;

    address constant ALICE = address(0xA11CE);
    address constant BOB = address(0xB0B);
    uint32 constant LOCAL = 9999;
    uint32 constant REMOTE = 11155111;
    bytes32 constant PEER_ID = bytes32(uint256(0xcc));
    bytes32 constant MESSAGE_ID =
        0xf44504e00b9ef65496c962d2c682804f0ec047ee58f0b3cd30c6b116895e04e9;

    function setUp() public {
        mailbox = new MockMailbox();
        usdt = new MockERC20("USDT", "USDT", 6);
        usdc = new MockERC20("USDC", "USDC", 6);
        peer = new HyperlanePeer(
            address(mailbox),
            LOCAL,
            REMOTE,
            PEER_ID,
            address(0),
            address(this),
            _assets(address(usdt), address(usdc))
        );
        usdt.mint(ALICE, 10_000_000);
        usdc.mint(ALICE, 10_000_000);
        vm.prank(ALICE);
        usdt.approve(address(peer), type(uint256).max);
        vm.prank(ALICE);
        usdc.approve(address(peer), type(uint256).max);
    }

    function testMessageIdMatchesRustGolden() public pure {
        bytes memory body =
            bytes("rbridge:hyperlane:v1|deposit|ethereum.usdt|1000000|rho:id:recipient|0xabc:0|7");
        bytes memory message = abi.encodePacked(
            uint8(3),
            uint32(7),
            uint32(11_155_111),
            bytes32(uint256(0xaa)),
            uint32(84_532),
            bytes32(uint256(0xbb)),
            body
        );
        assertEq(keccak256(message), MESSAGE_ID);
    }

    function testCheckpointDigestMatchesRustGolden() public pure {
        bytes32 domain = keccak256(
            abi.encodePacked(
                uint32(11_155_111),
                bytes32(uint256(0x1111111111111111111111111111111111111111111111111111111111111111)),
                "HYPERLANE"
            )
        );
        bytes32 inner = keccak256(
            abi.encodePacked(
                domain,
                bytes32(uint256(0x2222222222222222222222222222222222222222222222222222222222222222)),
                uint32(3),
                MESSAGE_ID
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", inner));
        assertEq(digest, 0xa4411138366886244ae59b3f44587dc9f12edd373b6c0603f8909e3785e3d963);
    }

    function testLockUsdtDispatchesCanonicalDeposit() public {
        vm.prank(ALICE);
        peer.lock(address(usdt), 1_000_000, "rho:id:alice");

        assertEq(mailbox.count(), 1);
        (uint32 destination, bytes32 recipient, bytes memory body) = mailbox.last();
        assertEq(uint256(destination), uint256(REMOTE));
        assertEq(recipient, PEER_ID);
        assertTrue(_contains(body, bytes("rbridge:hyperlane:v1|deposit|ethereum.usdt|1000000|rho:id:alice|")));
        assertEq(peer.locked(address(usdt)), 1_000_000);
        assertEq(usdt.balanceOf(address(peer)), 1_000_000);
    }

    function testLockUsdcDispatchesCanonicalDeposit() public {
        vm.prank(ALICE);
        peer.lock(address(usdc), 2_000_000, "rho:id:alice");
        (, , bytes memory body) = mailbox.last();
        assertTrue(_contains(body, bytes("rbridge:hyperlane:v1|deposit|ethereum.usdc|2000000|rho:id:alice|")));
        assertEq(peer.locked(address(usdc)), 2_000_000);
        assertEq(usdc.balanceOf(address(peer)), 2_000_000);
    }

    function testHandleReleasesUsdt() public {
        vm.prank(ALICE);
        peer.lock(address(usdt), 1_000_000, "rho:id:alice");
        mailbox.deliver(address(peer), REMOTE, PEER_ID, bytes(_withdrawPayload("usdt", "ethereum.usdt", "w-1", 500_000)));
        assertEq(usdt.balanceOf(BOB), 500_000);
        assertEq(peer.locked(address(usdt)), 500_000);
        assertTrue(peer.usedWithdrawal(keccak256(bytes("w-1"))));
    }

    function testHandleReleasesUsdc() public {
        vm.prank(ALICE);
        peer.lock(address(usdc), 2_000_000, "rho:id:alice");
        mailbox.deliver(address(peer), REMOTE, PEER_ID, bytes(_withdrawPayload("usdc", "ethereum.usdc", "w-2", 1_000_000)));
        assertEq(usdc.balanceOf(BOB), 1_000_000);
        assertEq(peer.locked(address(usdc)), 1_000_000);
    }

    function testReplayRefused() public {
        vm.prank(ALICE);
        peer.lock(address(usdt), 1_000_000, "rho:id:alice");
        bytes memory payload = bytes(_withdrawPayload("usdt", "ethereum.usdt", "w-1", 500_000));
        mailbox.deliver(address(peer), REMOTE, PEER_ID, payload);
        vm.expectRevert();
        mailbox.deliver(address(peer), REMOTE, PEER_ID, payload);
    }

    function testWrongSenderRefused() public {
        vm.prank(ALICE);
        peer.lock(address(usdt), 1_000_000, "rho:id:alice");
        vm.expectRevert();
        mailbox.deliver(address(peer), REMOTE, bytes32(uint256(0xee)), bytes(_withdrawPayload("usdt", "ethereum.usdt", "w-1", 500_000)));
    }

    function testWrongOriginRefused() public {
        vm.prank(ALICE);
        peer.lock(address(usdt), 1_000_000, "rho:id:alice");
        vm.expectRevert();
        mailbox.deliver(address(peer), 1, PEER_ID, bytes(_withdrawPayload("usdt", "ethereum.usdt", "w-1", 500_000)));
    }

    function testUnknownAssetRefused() public {
        vm.prank(ALICE);
        peer.lock(address(usdt), 1_000_000, "rho:id:alice");
        vm.expectRevert();
        mailbox.deliver(address(peer), REMOTE, PEER_ID, bytes(_withdrawPayload("usdt", "ethereum.dai", "w-1", 500_000)));
    }

    function testDirectHandleRefused() public {
        vm.expectRevert();
        peer.handle(REMOTE, PEER_ID, bytes(_withdrawPayload("usdt", "ethereum.usdt", "w-1", 500_000)));
    }

    function testPauseRefusesLock() public {
        peer.setPaused(true);
        vm.prank(ALICE);
        vm.expectRevert();
        peer.lock(address(usdt), 1_000_000, "rho:id:alice");
    }

    function testDustRefused() public {
        HyperlanePeer scaled = new HyperlanePeer(
            address(mailbox),
            LOCAL,
            REMOTE,
            PEER_ID,
            address(0),
            address(this),
            _scaledAssets(address(usdt))
        );
        vm.prank(ALICE);
        usdt.approve(address(scaled), type(uint256).max);
        vm.prank(ALICE);
        vm.expectRevert();
        scaled.lock(address(usdt), 1, "rho:id:alice");
    }

    function testTrustedRelayerIsm() public {
        MockProcessorMailbox processorMailbox = new MockProcessorMailbox();
        RbridgeTrustedRelayerIsm relayerIsm =
            new RbridgeTrustedRelayerIsm(address(processorMailbox), ALICE);
        bytes memory message = abi.encodePacked("rbridge:hyperlane:v1|withdraw|usdt");
        bytes32 id = keccak256(message);
        processorMailbox.setProcessor(id, ALICE);
        assertTrue(relayerIsm.verify("", message));
        processorMailbox.setProcessor(id, BOB);
        assertTrue(!relayerIsm.verify("", message));
        assertEq(relayerIsm.moduleType(), 6);
    }

    function testPeerReportsConfiguredIsm() public {
        RbridgeTrustedRelayerIsm relayerIsm =
            new RbridgeTrustedRelayerIsm(address(mailbox), ALICE);
        HyperlanePeer withIsm = new HyperlanePeer(
            address(mailbox),
            LOCAL,
            REMOTE,
            PEER_ID,
            address(relayerIsm),
            address(this),
            _assets(address(usdt), address(usdc))
        );
        assertEq(uint256(uint160(withIsm.interchainSecurityModule())), uint256(uint160(address(relayerIsm))));
    }

    function _assets(address tokenA, address tokenB)
        internal
        pure
        returns (HyperlanePeer.AssetInit[] memory inits)
    {
        inits = new HyperlanePeer.AssetInit[](2);
        inits[0] = HyperlanePeer.AssetInit(tokenA, "ethereum.usdt", 1, 10_000_000, 1_000_000_000);
        inits[1] = HyperlanePeer.AssetInit(tokenB, "ethereum.usdc", 1, 10_000_000, 1_000_000_000);
    }

    function _scaledAssets(address token) internal pure returns (HyperlanePeer.AssetInit[] memory inits) {
        inits = new HyperlanePeer.AssetInit[](1);
        inits[0] = HyperlanePeer.AssetInit(token, "ethereum.usdt", 1e10, 10_000_000, 1_000_000_000);
    }

    function _withdrawPayload(
        string memory,
        string memory assetKey,
        string memory withdrawalId,
        uint256 amount
    ) internal pure returns (string memory) {
        return string.concat(
            "rbridge:hyperlane:v1|withdraw|",
            assetKey,
            "|",
            _toString(amount),
            "|",
            _toHexAddress(BOB),
            "|",
            withdrawalId,
            "|0"
        );
    }

    function _contains(bytes memory haystack, bytes memory needle) internal pure returns (bool) {
        if (needle.length > haystack.length) return false;
        for (uint256 i = 0; i <= haystack.length - needle.length; ++i) {
            bool matched = true;
            for (uint256 j = 0; j < needle.length; ++j) {
                if (haystack[i + j] != needle[j]) {
                    matched = false;
                    break;
                }
            }
            if (matched) return true;
        }
        return false;
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

    function assertEq(bytes32 a, bytes32 b) internal pure {
        require(a == b, "assertEq bytes32 failed");
    }
}
