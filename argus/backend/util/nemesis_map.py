"""
Mapping from disrupt_ function names to human-readable Nemesis class names.

Generated from nemeses.json (inverted), keeping only the first mapping when
multiple Nemesis classes share the same disrupt_ function.
"""

# Original mapping: NemesisClassName -> disrupt_function_name
_NEMESIS_TO_DISRUPT: dict[str, str] = {
    "SslHotReloadingNemesis": "disrupt_hot_reloading_internode_certificate",
    "PauseLdapNemesis": "disrupt_ldap_connection_toggle",
    "ToggleLdapConfiguration": "disrupt_disable_enable_ldap_authorization",
    "AddRemoveDcNemesis": "disrupt_add_remove_dc",
    "GrowShrinkClusterNemesis": "disrupt_grow_shrink_cluster",
    "AddRemoveRackNemesis": "disrupt_grow_shrink_new_rack",
    "StopWaitStartMonkey": "disrupt_stop_wait_start_scylla_server",
    "StopStartMonkey": "disrupt_stop_start_scylla_server",
    "EnableDisableTableEncryptionAwsKmsProviderWithRotationMonkey": "disrupt_enable_disable_table_encryption_aws_kms_provider_with_rotation",
    "EnableDisableTableEncryptionAwsKmsProviderWithoutRotationMonkey": "disrupt_enable_disable_table_encryption_aws_kms_provider_without_rotation",
    "RestartThenRepairNodeMonkey": "disrupt_restart_then_repair_node",
    "MultipleHardRebootNodeMonkey": "disrupt_multiple_hard_reboot_node",
    "HardRebootNodeMonkey": "disrupt_hard_reboot_node",
    "SoftRebootNodeMonkey": "disrupt_soft_reboot_node",
    "DrainerMonkey": "disrupt_nodetool_drain",
    "CorruptThenRepairMonkey": "disrupt_destroy_data_then_repair",
    "CorruptThenRebuildMonkey": "disrupt_destroy_data_then_rebuild",
    "DecommissionMonkey": "disrupt_nodetool_decommission",
    "DecommissionSeedNode": "disrupt_nodetool_seed_decommission",
    "NoCorruptRepairMonkey": "disrupt_no_corrupt_repair",
    "MajorCompactionMonkey": "disrupt_major_compaction",
    "RefreshMonkey": "disrupt_nodetool_refresh",
    "LoadAndStreamMonkey": "disrupt_load_and_stream",
    "RefreshBigMonkey": "disrupt_nodetool_refresh",
    "RemoveServiceLevelMonkey": "disrupt_remove_service_level_while_load",
    "EnospcMonkey": "disrupt_nodetool_enospc",
    "EnospcAllNodesMonkey": "disrupt_nodetool_enospc",
    "NodeToolCleanupMonkey": "disrupt_nodetool_cleanup",
    "TruncateMonkey": "disrupt_truncate",
    "TruncateLargeParititionMonkey": "disrupt_truncate_large_partition",
    "DeleteByPartitionsMonkey": "disrupt_delete_10_full_partitions",
    "DeleteByRowsRangeMonkey": "disrupt_delete_by_rows_range",
    "DeleteOverlappingRowRangesMonkey": "disrupt_delete_overlapping_row_ranges",
    "AddDropColumnMonkey": "disrupt_add_drop_column",
    "ToggleTableIcsMonkey": "disrupt_toggle_table_ics",
    "ToggleGcModeMonkey": "disrupt_toggle_table_gc_mode",
    "MgmtBackup": "disrupt_mgmt_backup",
    "MgmtBackupSpecificKeyspaces": "disrupt_mgmt_backup_specific_keyspaces",
    "MgmtRestore": "disrupt_mgmt_restore",
    "MgmtRepair": "disrupt_mgmt_repair_cli",
    "MgmtCorruptThenRepair": "disrupt_mgmt_corrupt_then_repair",
    "AbortRepairMonkey": "disrupt_abort_repair",
    "NodeTerminateAndReplace": "disrupt_terminate_and_replace_node",
    "DrainKubernetesNodeThenReplaceScyllaNode": "disrupt_drain_kubernetes_node_then_replace_scylla_node",
    "TerminateKubernetesHostThenReplaceScyllaNode": "disrupt_terminate_kubernetes_host_then_replace_scylla_node",
    "DrainKubernetesNodeThenDecommissionAndAddScyllaNode": "disrupt_drain_kubernetes_node_then_decommission_and_add_scylla_node",
    "TerminateKubernetesHostThenDecommissionAndAddScyllaNode": "disrupt_terminate_kubernetes_host_then_decommission_and_add_scylla_node",
    "OperatorNodeReplace": "disrupt_replace_scylla_node_on_kubernetes",
    "OperatorNodetoolFlushAndReshard": "disrupt_nodetool_flush_and_reshard_on_kubernetes",
    "ScyllaKillMonkey": "disrupt_kill_scylla",
    "ValidateHintedHandoffShortDowntime": "disrupt_validate_hh_short_downtime",
    "SnapshotOperations": "disrupt_snapshot_operations",
    "NodeRestartWithResharding": "disrupt_restart_with_resharding",
    "ClusterRollingRestart": "disrupt_rolling_restart_cluster",
    "RollingRestartConfigChangeInternodeCompression": "disrupt_rolling_config_change_internode_compression",
    "ClusterRollingRestartRandomOrder": "disrupt_rolling_restart_cluster",
    "SwitchBetweenPasswordAuthAndSaslauthdAuth": "disrupt_switch_between_password_authenticator_and_saslauthd_authenticator_and_back",
    "TopPartitions": "disrupt_show_toppartitions",
    "RandomInterruptionNetworkMonkey": "disrupt_network_random_interruptions",
    "BlockNetworkMonkey": "disrupt_network_block",
    "RejectInterNodeNetworkMonkey": "disrupt_network_reject_inter_node_communication",
    "RejectNodeExporterNetworkMonkey": "disrupt_network_reject_node_exporter",
    "RejectThriftNetworkMonkey": "disrupt_network_reject_thrift",
    "StopStartInterfacesNetworkMonkey": "disrupt_network_start_stop_interface",
    "NemesisSequence": "disrupt_run_unique_sequence",
    "TerminateAndRemoveNodeMonkey": "disrupt_remove_node_then_add_node",
    "ToggleCDCMonkey": "disrupt_toggle_cdc_feature_properties_on_table",
    "CDCStressorMonkey": "disrupt_run_cdcstressor_tool",
    "DecommissionStreamingErrMonkey": "disrupt_decommission_streaming_err",
    "RebuildStreamingErrMonkey": "disrupt_rebuild_streaming_err",
    "RepairStreamingErrMonkey": "disrupt_repair_streaming_err",
    "CorruptThenScrubMonkey": "disrupt_corrupt_then_scrub",
    "MemoryStressMonkey": "disrupt_memory_stress",
    "ResetLocalSchemaMonkey": "disrupt_resetlocalschema",
    "StartStopMajorCompaction": "disrupt_start_stop_major_compaction",
    "StartStopScrubCompaction": "disrupt_start_stop_scrub_compaction",
    "StartStopCleanupCompaction": "disrupt_start_stop_cleanup_compaction",
    "StartStopValidationCompaction": "disrupt_start_stop_validation_compaction",
    "SlaIncreaseSharesDuringLoad": "disrupt_sla_increase_shares_during_load",
    "SlaDecreaseSharesDuringLoad": "disrupt_sla_decrease_shares_during_load",
    "SlaReplaceUsingDetachDuringLoad": "disrupt_replace_service_level_using_detach_during_load",
    "SlaReplaceUsingDropDuringLoad": "disrupt_replace_service_level_using_drop_during_load",
    "SlaIncreaseSharesByAttachAnotherSlDuringLoad": "disrupt_increase_shares_by_attach_another_sl_during_load",
    "SlaMaximumAllowedSlsWithMaxSharesDuringLoad": "disrupt_maximum_allowed_sls_with_max_shares_during_load",
    "CreateIndexNemesis": "disrupt_create_index",
    "AddRemoveMvNemesis": "disrupt_add_remove_mv",
    "ToggleAuditNemesisSyslog": "disrupt_toggle_audit_syslog",
    "BootstrapStreamingErrorNemesis": "disrupt_bootstrap_streaming_error",
    "DisableBinaryGossipExecuteMajorCompaction": "disrupt_disable_binary_gossip_execute_major_compaction",
    "EndOfQuotaNemesis": "disrupt_end_of_quota_nemesis",
    "GrowShrinkZeroTokenNode": "disrupt_grow_shrink_zero_nodes",
    "SerialRestartOfElectedTopologyCoordinatorNemesis": "disrupt_serial_restart_elected_topology_coordinator",
    "IsolateNodeWithProcessSignalNemesis": "disrupt_refuse_connection_with_send_sigstop_signal_to_scylla_on_banned_node",
    "IsolateNodeWithIptableRuleNemesis": "disrupt_refuse_connection_with_block_scylla_ports_on_banned_node",
    "KillMVBuildingCoordinator": "disrupt_kill_mv_building_coordinator",
    "ModifyTableTwcsWindowSizeMonkey": "disrupt_modify_table_twcs_window_size",
    "ModifyTableCommentMonkey": "disrupt_modify_table_comment",
    "ModifyTableGcGraceTimeMonkey": "disrupt_modify_table_gc_grace_time",
    "ModifyTableCachingMonkey": "disrupt_modify_table_caching",
    "ModifyTableBloomFilterFpChanceMonkey": "disrupt_modify_table_bloom_filter_fp_chance",
    "ModifyTableCompactionMonkey": "disrupt_modify_table_compaction",
    "ModifyTableCompressionMonkey": "disrupt_modify_table_compression",
    "ModifyTableCrcCheckChanceMonkey": "disrupt_modify_table_crc_check_chance",
    "ModifyTableDclocalReadRepairChanceMonkey": "disrupt_modify_table_dclocal_read_repair_chance",
    "ModifyTableDefaultTimeToLiveMonkey": "disrupt_modify_table_default_time_to_live",
    "ModifyTableMaxIndexIntervalMonkey": "disrupt_modify_table_max_index_interval",
    "ModifyTableMinIndexIntervalMonkey": "disrupt_modify_table_min_index_interval",
    "ModifyTableMemtableFlushPeriodInMsMonkey": "disrupt_modify_table_memtable_flush_period_in_ms",
    "ModifyTableReadRepairChanceMonkey": "disrupt_modify_table_read_repair_chance",
    "ModifyTableSpeculativeRetryMonkey": "disrupt_modify_table_speculative_retry",
}

# Inverted mapping: disrupt_function_name -> NemesisClassName
# When multiple Nemesis classes share the same disrupt_ function, only the first is kept.
DISRUPT_TO_NEMESIS: dict[str, str] = {}
for _nemesis_name, _disrupt_name in _NEMESIS_TO_DISRUPT.items():
    if _disrupt_name not in DISRUPT_TO_NEMESIS:
        DISRUPT_TO_NEMESIS[_disrupt_name] = _nemesis_name


def get_nemesis_name(raw_name: str) -> str:
    """Convert a raw nemesis name (possibly a disrupt_ function name) to a human-readable Nemesis class name.

    If the name starts with 'disrupt_', look it up in the map and return the Nemesis class name.
    If no mapping is found, fall back to stripping the 'disrupt_' prefix.
    If the name does not start with 'disrupt_', return it as-is.
    """
    if raw_name.startswith("disrupt_"):
        return DISRUPT_TO_NEMESIS.get(raw_name, raw_name.split("disrupt_", 1)[-1])
    return raw_name
