// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

import {BridgeVault} from "../src/BridgeVault.sol";

interface VmDeploy {
    function envUint(string calldata name) external view returns (uint256);
    function envAddress(string calldata name) external view returns (address);
    function envString(string calldata name) external view returns (string memory);
    function toString(uint256 value) external pure returns (string memory);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Environment-driven vault deployment used by `tools/deploy_evm.py`.
///         Every parameter comes from a network profile, so the same script deploys
///         Anvil, Sepolia or Nile. Run it through the tool: the tool checks the chain id,
///         the asset addresses and the deployed configuration before writing a manifest.
contract DeployVault {
    VmDeploy constant vm = VmDeploy(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external returns (BridgeVault vault) {
        uint256 privateKey = vm.envUint("PRIVATE_KEY");
        uint256 adminCount = vm.envUint("ADMIN_COUNT");
        uint256 relayerCount = vm.envUint("RELAYER_COUNT");
        uint256 assetCount = vm.envUint("ASSET_COUNT");
        require(adminCount > 0 && adminCount <= 10, "admin count");
        require(relayerCount > 0 && relayerCount <= 10, "relayer count");
        require(assetCount > 0 && assetCount <= 8, "asset count");

        address[] memory admins = new address[](adminCount);
        for (uint256 i = 0; i < adminCount; ++i) {
            admins[i] = vm.envAddress(_indexed("ADMIN_", i));
        }

        address[] memory relayers = new address[](relayerCount);
        for (uint256 i = 0; i < relayerCount; ++i) {
            relayers[i] = vm.envAddress(_indexed("RELAYER_", i));
        }

        BridgeVault.AssetInit[] memory inits = new BridgeVault.AssetInit[](assetCount);
        for (uint256 i = 0; i < assetCount; ++i) {
            string memory prefix = _indexed("ASSET_", i);
            inits[i] = BridgeVault.AssetInit({
                token: vm.envAddress(string.concat(prefix, "_TOKEN")),
                assetKey: vm.envString(string.concat(prefix, "_KEY")),
                maxDeposit: vm.envUint(string.concat(prefix, "_MAX_DEPOSIT")),
                maxLocked: vm.envUint(string.concat(prefix, "_MAX_LOCKED")),
                scale: vm.envUint(string.concat(prefix, "_SCALE")),
                withdrawFeeBps: vm.envUint(string.concat(prefix, "_WITHDRAW_FEE_BPS"))
            });
        }

        vm.startBroadcast(privateKey);
        vault = new BridgeVault(
            vm.envUint("CHAIN_TAG"),
            vm.envString("NETWORK"),
            vm.envString("CHAIN_NAME"),
            vm.envString("BRIDGE_ID"),
            admins,
            vm.envUint("ADMIN_THRESHOLD"),
            relayers,
            vm.envUint("RELAYER_THRESHOLD"),
            vm.envAddress("TREASURY"),
            inits
        );
        vm.stopBroadcast();
    }

    function _indexed(string memory prefix, uint256 index) private pure returns (string memory) {
        return string.concat(prefix, vm.toString(index + 1));
    }
}
