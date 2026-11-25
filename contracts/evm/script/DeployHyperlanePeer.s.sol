// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

import {HyperlanePeer} from "../src/HyperlanePeer.sol";
import {RbridgeTrustedRelayerIsm} from "../src/RbridgeTrustedRelayerIsm.sol";

interface VmDeployHyperlane {
    function envUint(string calldata name) external view returns (uint256);
    function envAddress(string calldata name) external view returns (address);
    function envBytes32(string calldata name) external view returns (bytes32);
    function envString(string calldata name) external view returns (string memory);
    function toString(uint256 value) external pure returns (string memory);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Environment-driven HyperlanePeer deployment used by
///         `tools/deploy_hyperlane_peer.py`. The script deploys a TrustedRelayerISM and
///         the peer; the tool checks the chain, Mailbox, tokens and read-back before
///         writing a manifest.
contract DeployHyperlanePeer {
    VmDeployHyperlane constant vm =
        VmDeployHyperlane(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external returns (HyperlanePeer peer, RbridgeTrustedRelayerIsm ism) {
        uint256 privateKey = vm.envUint("PRIVATE_KEY");
        uint256 assetCount = vm.envUint("ASSET_COUNT");
        require(assetCount > 0 && assetCount <= 8, "asset count");

        HyperlanePeer.AssetInit[] memory inits = new HyperlanePeer.AssetInit[](assetCount);
        for (uint256 i = 0; i < assetCount; ++i) {
            string memory prefix = _indexed("ASSET_", i);
            inits[i] = HyperlanePeer.AssetInit({
                token: vm.envAddress(string.concat(prefix, "_TOKEN")),
                assetKey: vm.envString(string.concat(prefix, "_KEY")),
                scale: vm.envUint(string.concat(prefix, "_SCALE")),
                maxDeposit: vm.envUint(string.concat(prefix, "_MAX_DEPOSIT")),
                maxLocked: vm.envUint(string.concat(prefix, "_MAX_LOCKED"))
            });
        }

        address mailbox = vm.envAddress("MAILBOX");
        vm.startBroadcast(privateKey);
        ism = new RbridgeTrustedRelayerIsm(mailbox, vm.envAddress("RELAYER"));
        peer = new HyperlanePeer(
            mailbox,
            uint32(vm.envUint("LOCAL_DOMAIN")),
            uint32(vm.envUint("REMOTE_DOMAIN")),
            vm.envBytes32("REMOTE_PEER"),
            address(ism),
            vm.envAddress("OWNER"),
            inits
        );
        vm.stopBroadcast();
    }

    function _indexed(string memory prefix, uint256 index) private pure returns (string memory) {
        return string.concat(prefix, vm.toString(index + 1));
    }
}
