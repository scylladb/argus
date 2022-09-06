import TestRun from "../TestRun/TestRun.svelte";
import UnknownTest from "../WorkArea/UnknownTest.svelte";

export const AVAILABLE_PLUGINS = {
    "scylla-cluster-tests": TestRun,
    unknown: UnknownTest,
};

export const isPluginSupported = function(pluginName) {
    return !(pluginName in AVAILABLE_PLUGINS);
};
