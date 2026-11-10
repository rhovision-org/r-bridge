// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

import {BridgeVault} from "../src/BridgeVault.sol";

interface VmScript {
    function envUint(string calldata name) external returns (uint256);
    function envAddress(string calldata name) external returns (address);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Local Anvil deployment for the cross-chain demo. ETH-only asset config.
///         Env: PRIVATE_KEY, ADMIN1..3, RELAYER1..3, TREASURY.
contract DeployAnvil {
    VmScript constant vm = VmScript(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external returns (BridgeVault vault) {
        uint256 privateKey = vm.envUint("PRIVATE_KEY");

        address[] memory admins = new address[](3);
        admins[0] = vm.envAddress("ADMIN1");
        admins[1] = vm.envAddress("ADMIN2");
        admins[2] = vm.envAddress("ADMIN3");

        address[] memory relayers = new address[](3);
        relayers[0] = vm.envAddress("RELAYER1");
        relayers[1] = vm.envAddress("RELAYER2");
        relayers[2] = vm.envAddress("RELAYER3");

        BridgeVault.AssetInit[] memory inits = new BridgeVault.AssetInit[](1);
        inits[0] = BridgeVault.AssetInit(
            address(0), // native ETH
            "ethereum.eth",
            1_000_000_000_000_000_000_000, // 1000 ETH in wei
            1_000_000_000_000_000_000_000_000, // 1,000,000 ETH
            10_000_000_000, // 18 native decimals -> 8 rholo decimals
            5
        );

        vm.startBroadcast(privateKey);
        vault = new BridgeVault(
            31337,
            "rbridge-devnet",
            "ethereum",
            "rbridge:devnet:bridge",
            admins,
            2,
            relayers,
            2,
            vm.envAddress("TREASURY"),
            inits
        );
        vm.stopBroadcast();
    }
}
