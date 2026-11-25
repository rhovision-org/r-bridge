// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.24;

import {MockERC20} from "../src/MockERC20.sol";
import {MockHyperlaneMailbox} from "../src/MockHyperlaneMailbox.sol";

interface VmDeployMocks {
    function envUint(string calldata name) external view returns (uint256);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Deploys the local Mailbox and two stablecoin mocks for the Anvil peer demos.
contract DeployHyperlaneMocks {
    VmDeployMocks constant vm =
        VmDeployMocks(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run()
        external
        returns (MockHyperlaneMailbox mailbox, MockERC20 usdt, MockERC20 usdc)
    {
        uint256 privateKey = vm.envUint("PRIVATE_KEY");
        uint32 domain = uint32(vm.envUint("LOCAL_DOMAIN"));
        vm.startBroadcast(privateKey);
        mailbox = new MockHyperlaneMailbox(domain);
        usdt = new MockERC20("USDT", "USDT", 6);
        usdc = new MockERC20("USDC", "USDC", 6);
        vm.stopBroadcast();
    }
}
