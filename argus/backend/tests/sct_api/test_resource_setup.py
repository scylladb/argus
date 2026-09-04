import json

import pytest

from argus.backend.plugins.sct.resource_setup import (
    ResourceSetup,
    is_db_resource,
    xcloud_cluster_type,
    xcloud_details_from_config_params,
    xcloud_network_type,
)
from argus.backend.plugins.sct.testrun import get_region_property

XCLOUD_SCALING_CONFIG = {
    "InstanceFamilies": ["i8g"],
    "Mode": "xcloud",
    "Policies": {"Storage": {"Min": 0, "TargetUtilization": 0.8}, "VCPU": {"Min": 0}},
}


def _xcloud_config(provider: str, **overrides) -> dict:
    config = {
        "cluster_backend": "xcloud",
        "xcloud_provider": provider,
        "scylla_version": "2025.3.0",
        "n_db_nodes": 3,
        "n_loaders": 2,
        "n_monitor_nodes": 1,
        "xcloud_scaling_config": {},
        "xcloud_vpc_peering": {"enabled": True, "cidr_pool_base": "172.31.0.0/16", "cidr_subnet_size": 24},
        "post_behavior_db_nodes": "destroy",
        "post_behavior_loader_nodes": "destroy",
        "post_behavior_monitor_nodes": "keep-on-failure",
        # aws keys
        "instance_type_db": "i4i.large",
        "instance_type_loader": "c6i.2xlarge",
        "instance_type_monitor": "t3.large",
        "ami_id_loader": "ami-loader",
        "ami_id_monitor": "ami-monitor",
        # gce keys
        "gce_instance_type_db": "n2-highmem-16",
        "gce_instance_type_loader": "e2-standard-8",
        "gce_instance_type_monitor": "e2-standard-2",
        "gce_image_loader": "gce-loader",
        "gce_image_monitor": "gce-monitor",
    }
    config.update(overrides)
    return config


def test_xcloud_standard_cluster_on_aws():
    setup = ResourceSetup.get_resource_setup("xcloud", _xcloud_config("aws"))

    assert setup.backend == "xcloud"
    assert setup.db_node.instance_type == "i4i.large"
    assert setup.db_node.node_amount == 3
    assert setup.db_node.image_id == "2025.3.0"
    assert setup.db_node.post_behaviour == "destroy"
    # loaders / monitors are plain provider VMs
    assert setup.loader_node.instance_type == "c6i.2xlarge"
    assert setup.loader_node.image_id == "ami-loader"
    assert setup.loader_node.node_amount == 2
    assert setup.monitor_node.instance_type == "t3.large"


def test_xcloud_scaling_cluster_on_gce_leaves_db_node_shape_unset():
    config = _xcloud_config("gce", xcloud_scaling_config=XCLOUD_SCALING_CONFIG,
                            xcloud_vpc_peering={"enabled": False})
    setup = ResourceSetup.get_resource_setup("xcloud", config)

    assert setup.db_node.instance_type is None
    assert setup.db_node.node_amount is None
    assert setup.db_node.image_id == "2025.3.0"
    assert setup.loader_node.instance_type == "e2-standard-8"
    assert setup.loader_node.image_id == "gce-loader"


def test_xcloud_accepts_json_string_params():
    config = _xcloud_config(
        "aws",
        xcloud_scaling_config=json.dumps(XCLOUD_SCALING_CONFIG),
        xcloud_vpc_peering=json.dumps({"enabled": True}),
    )
    setup = ResourceSetup.get_resource_setup("xcloud", config)

    assert setup.db_node.instance_type is None
    assert setup.db_node.node_amount is None


@pytest.mark.parametrize("value", [None, "", "not json", "[1, 2]"])
def test_xcloud_unparseable_scaling_config_keeps_configured_db_node_shape(value):
    setup = ResourceSetup.get_resource_setup(
        "xcloud", _xcloud_config("aws", xcloud_scaling_config=value, xcloud_vpc_peering=value))

    assert setup.db_node.instance_type == "i4i.large"
    assert setup.db_node.node_amount == 3


def test_xcloud_unknown_provider_still_classifies_cluster():
    config = _xcloud_config("azure", xcloud_scaling_config=XCLOUD_SCALING_CONFIG)
    setup = ResourceSetup.get_resource_setup("xcloud", config)

    assert setup.backend == "xcloud"
    assert setup.db_node.instance_type is None
    assert setup.db_node.node_amount is None


@pytest.mark.parametrize("scaling_config,expected", [
    (XCLOUD_SCALING_CONFIG, "xcloud"),
    (json.dumps(XCLOUD_SCALING_CONFIG), "xcloud"),
    ({}, "standard"),
    ("{}", "standard"),
    (None, "standard"),
    ("", "standard"),
    ("not json", "standard"),
    ("[1, 2]", "standard"),
])
def test_xcloud_cluster_type(scaling_config, expected):
    assert xcloud_cluster_type(scaling_config) == expected


@pytest.mark.parametrize("vpc_peering,expected", [
    ({"enabled": True}, "private-vpc"),
    ({"enabled": "True"}, "private-vpc"),
    ({"enabled": "true"}, "private-vpc"),
    (json.dumps({"enabled": True}), "private-vpc"),
    ({"enabled": False}, "public"),
    ({"enabled": "False"}, "public"),
    ({}, "public"),
    (None, "public"),
    ("not json", "public"),
])
def test_xcloud_network_type(vpc_peering, expected):
    assert xcloud_network_type(vpc_peering) == expected


def test_xcloud_details_from_flattened_dict_params():
    # what ClientService.parse_config_values produces for dict-valued params
    params = {
        "sct_config.cluster_backend": "xcloud",
        "sct_config.xcloud_scaling_config.Mode": "xcloud",
        "sct_config.xcloud_scaling_config.InstanceFamilies.0": "i8g",
        "sct_config.xcloud_scaling_config.Policies.VCPU.Min": "0",
        "sct_config.xcloud_vpc_peering.enabled": "True",
        "sct_config.xcloud_vpc_peering.cidr_pool_base": "172.31.0.0/16",
    }
    assert xcloud_details_from_config_params(params) == {"cluster_type": "xcloud", "network_type": "private-vpc"}


def test_xcloud_details_from_json_string_params():
    # SCT declares these as dict_or_str; a string value is stored as a single scalar row
    params = {
        "sct_config.cluster_backend": "xcloud",
        "sct_config.xcloud_scaling_config": json.dumps(XCLOUD_SCALING_CONFIG),
        "sct_config.xcloud_vpc_peering": json.dumps({"enabled": False}),
    }
    assert xcloud_details_from_config_params(params) == {"cluster_type": "xcloud", "network_type": "public"}


def test_xcloud_details_empty_scaling_config_leaves_no_rows():
    # an empty dict is not scalar, so it is skipped entirely => standard cluster
    params = {
        "sct_config.cluster_backend": "xcloud",
        "sct_config.xcloud_vpc_peering.enabled": "False",
    }
    assert xcloud_details_from_config_params(params) == {"cluster_type": "standard", "network_type": "public"}


def test_xcloud_details_unknown_until_config_is_submitted():
    assert xcloud_details_from_config_params({}) == {"cluster_type": None, "network_type": None}
    # rows from some other config file do not count
    assert xcloud_details_from_config_params({"my_config.cluster_backend": "xcloud"}) == {
        "cluster_type": None, "network_type": None}


@pytest.mark.parametrize("backend,config,expected", [
    ("aws", {}, "region_name"),
    ("gce", {}, "gce_datacenter"),
    ("xcloud", {"xcloud_provider": "aws"}, "region_name"),
    ("xcloud", {"xcloud_provider": "GCE"}, "gce_datacenter"),
    ("xcloud", {}, "region_name"),
    ("something-new", {}, "region_name"),
])
def test_get_region_property(backend, config, expected):
    assert get_region_property(backend, config) == expected


@pytest.mark.parametrize("resource_type,expected", [
    ("scylla-db", True),
    ("cs-db", True),
    ("db_node", True),
    ("loader", False),
    ("monitor", False),
    ("vector-store", False),
    ("sct-runner", False),
    (None, False),
    ("", False),
])
def test_is_db_resource(resource_type, expected):
    assert is_db_resource(resource_type) is expected
