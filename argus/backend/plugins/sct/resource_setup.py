import json
import logging
from argus.backend.plugins.sct.udt import CloudNodesInfo, CloudSetupDetails

LOGGER = logging.getLogger(__name__)

XCLOUD_BACKEND = "xcloud"
XCLOUD_CLUSTER_TYPE_STANDARD = "standard"
XCLOUD_CLUSTER_TYPE_XCLOUD = "xcloud"
XCLOUD_NETWORK_TYPE_PUBLIC = "public"
XCLOUD_NETWORK_TYPE_PRIVATE_VPC = "private-vpc"

# Backends where SCT does not know the DB node shape up front, so ``db_node.instance_type`` /
# ``db_node.node_amount`` are derived from the resources SCT registers during the run instead.
RESOURCE_DERIVED_DB_NODE_BACKENDS = frozenset({XCLOUD_BACKEND})


def is_db_resource(resource_type: str | None) -> bool:
    """Mirror SCT's own ``"db" in node_type`` check (``scylla-db``, ``cs-db``...)."""
    return bool(resource_type) and "db" in resource_type


def _as_mapping(value: dict | str | None) -> dict:
    """SCT declares some params as ``dict_or_str``; accept both shapes and treat anything else as empty."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _resolve_node_count(value: int | str | list | None) -> int | None:
    """Normalise the various shapes SCT uses for node counts into a single int.

    Accepted input formats:
    - ``None``        → ``None`` (unknown / not set)
    - ``int``         → returned as-is
    - ``str``         → space-separated token string, e.g. ``"3 1 1"``; tokens are
                        summed after casting to int (multi-DC notation).
    - ``list[int]``   → each element cast to int and summed (multi-DC list notation).
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return sum(int(i) for i in value.split())
    if isinstance(value, list):
        return sum(int(i) for i in value)
    return int(value)


def _get_node_amounts(config: dict) -> tuple[int | None, int | None]:
    num_db_node = _resolve_node_count(config.get("n_db_nodes"))
    num_loaders = _resolve_node_count(config.get("n_loaders"))

    return num_db_node, num_loaders


def _prepare_aws_resource_setup(sct_config: dict) -> CloudSetupDetails:
    num_db_nodes, n_loaders = _get_node_amounts(sct_config)
    db_node_setup = CloudNodesInfo(image_id=sct_config.get("ami_id_db_scylla"),
                                   instance_type=sct_config.get("instance_type_db"),
                                   node_amount=num_db_nodes,
                                   post_behaviour=sct_config.get("post_behavior_db_nodes"))
    loader_node_setup = CloudNodesInfo(image_id=sct_config.get("ami_id_loader"),
                                       instance_type=sct_config.get("instance_type_loader"),
                                       node_amount=n_loaders,
                                       post_behaviour=sct_config.get("post_behavior_loader_nodes"))
    monitor_node_setup = CloudNodesInfo(image_id=sct_config.get("ami_id_monitor"),
                                        instance_type=sct_config.get("instance_type_monitor"),
                                        node_amount=_resolve_node_count(sct_config.get("n_monitor_nodes")),
                                        post_behaviour=sct_config.get("post_behavior_monitor_nodes"))
    cloud_setup = CloudSetupDetails(db_node=db_node_setup, loader_node=loader_node_setup,
                                    monitor_node=monitor_node_setup, backend=sct_config.get("cluster_backend"))

    return cloud_setup


def _prepare_gce_resource_setup(sct_config: dict) -> CloudSetupDetails:
    num_db_nodes, n_loaders = _get_node_amounts(sct_config)
    db_node_setup = CloudNodesInfo(image_id=sct_config.get("gce_image_db"),
                                   instance_type=sct_config.get("gce_instance_type_db"),
                                   node_amount=num_db_nodes,
                                   post_behaviour=sct_config.get("post_behavior_db_nodes"))
    loader_node_setup = CloudNodesInfo(image_id=sct_config.get("gce_image_loader"),
                                       instance_type=sct_config.get("gce_instance_type_loader"),
                                       node_amount=n_loaders,
                                       post_behaviour=sct_config.get("post_behavior_loader_nodes"))
    monitor_node_setup = CloudNodesInfo(image_id=sct_config.get("gce_image_monitor"),
                                        instance_type=sct_config.get("gce_instance_type_monitor"),
                                        node_amount=_resolve_node_count(sct_config.get("n_monitor_nodes")),
                                        post_behaviour=sct_config.get("post_behavior_monitor_nodes"))
    cloud_setup = CloudSetupDetails(db_node=db_node_setup, loader_node=loader_node_setup,
                                    monitor_node=monitor_node_setup, backend=sct_config.get("cluster_backend"))

    return cloud_setup


def _prepare_azure_resource_setup(sct_config: dict) -> CloudSetupDetails:
    num_db_nodes, n_loaders = _get_node_amounts(sct_config)
    db_node_setup = CloudNodesInfo(image_id=sct_config.get("azure_image_db"),
                                   instance_type=sct_config.get("azure_instance_type_db"),
                                   node_amount=num_db_nodes,
                                   post_behaviour=sct_config.get("post_behavior_db_nodes"))
    loader_node_setup = CloudNodesInfo(image_id=sct_config.get("azure_image_loader"),
                                       instance_type=sct_config.get("azure_instance_type_loader"),
                                       node_amount=n_loaders,
                                       post_behaviour=sct_config.get("post_behavior_loader_nodes"))
    monitor_node_setup = CloudNodesInfo(image_id=sct_config.get("azure_image_monitor"),
                                        instance_type=sct_config.get("azure_instance_type_monitor"),
                                        node_amount=_resolve_node_count(sct_config.get("n_monitor_nodes")),
                                        post_behaviour=sct_config.get("post_behavior_monitor_nodes"))
    cloud_setup = CloudSetupDetails(db_node=db_node_setup, loader_node=loader_node_setup,
                                    monitor_node=monitor_node_setup, backend=sct_config.get("cluster_backend"))

    return cloud_setup


def _prepare_oci_resource_setup(sct_config: dict) -> CloudSetupDetails:
    num_db_nodes, n_loaders = _get_node_amounts(sct_config)
    db_node_setup = CloudNodesInfo(
        image_id=sct_config.get("oci_image_db"),
        instance_type=sct_config.get("oci_instance_type_db"),
        node_amount=num_db_nodes,
        post_behaviour=sct_config.get("post_behavior_db_nodes"),
    )
    loader_node_setup = CloudNodesInfo(
        image_id=sct_config.get("oci_image_loader"),
        instance_type=sct_config.get("oci_instance_type_loader"),
        node_amount=n_loaders,
        post_behaviour=sct_config.get("post_behavior_loader_nodes"),
    )
    monitor_node_setup = CloudNodesInfo(
        image_id=sct_config.get("oci_image_monitor"),
        instance_type=sct_config.get("oci_instance_type_monitor"),
        node_amount=_resolve_node_count(sct_config.get("n_monitor_nodes")),
        post_behaviour=sct_config.get("post_behavior_monitor_nodes"),
    )
    cloud_setup = CloudSetupDetails(
        db_node=db_node_setup,
        loader_node=loader_node_setup,
        monitor_node=monitor_node_setup,
        backend=sct_config.get("cluster_backend"),
    )
    return cloud_setup


def _prepare_unknown_resource_setup(sct_config: dict) -> CloudSetupDetails:
    LOGGER.error("Unknown backend encountered: %s", sct_config.get("cluster_backend"))
    db_node_setup = CloudNodesInfo(image_id="UNKNOWN",
                                   instance_type="UNKNOWN",
                                   node_amount=-1,
                                   post_behaviour="UNKNOWN")
    loader_node_setup = CloudNodesInfo(image_id="UNKNOWN",
                                       instance_type="UNKNOWN",
                                       node_amount=-1,
                                       post_behaviour="UNKNOWN")
    monitor_node_setup = CloudNodesInfo(image_id="UNKNOWN",
                                        instance_type="UNKNOWN",
                                        node_amount=-1,
                                        post_behaviour="UNKNOWN")
    cloud_setup = CloudSetupDetails(db_node=db_node_setup, loader_node=loader_node_setup,
                                    monitor_node=monitor_node_setup, backend=sct_config.get("cluster_backend"))

    return cloud_setup


def _prepare_bare_metal_resource_setup(sct_config: dict) -> CloudSetupDetails:
    db_node_setup = CloudNodesInfo(image_id="bare_metal",
                                   instance_type="bare_metal",
                                   node_amount=_resolve_node_count(sct_config.get("n_db_nodes")),
                                   post_behaviour=sct_config.get("post_behavior_db_nodes"))
    loader_node_setup = CloudNodesInfo(image_id="bare_metal",
                                       instance_type="bare_metal",
                                       node_amount=_resolve_node_count(sct_config.get("n_loaders")),
                                       post_behaviour=sct_config.get("post_behavior_loader_nodes"))
    monitor_node_setup = CloudNodesInfo(image_id="bare_metal",
                                        instance_type="bare_metal",
                                        node_amount=_resolve_node_count(sct_config.get("n_monitor_nodes")),
                                        post_behaviour=sct_config.get("post_behavior_monitor_nodes"))
    cloud_setup = CloudSetupDetails(db_node=db_node_setup, loader_node=loader_node_setup,
                                    monitor_node=monitor_node_setup, backend=sct_config.get("cluster_backend"))

    return cloud_setup


def _prepare_k8s_gce_minikube_resource_setup(sct_config: dict) -> CloudSetupDetails:
    cloud_setup = _prepare_gce_resource_setup(sct_config)

    image_id = sct_config.get("scylla_version")
    cloud_setup.db_node.image_id = f"scylladb/scylladb:{image_id}"
    cloud_setup.db_node.instance_type = sct_config.get("gce_instance_type_minikube")

    return cloud_setup


def _prepare_k8s_gke_resource_setup(sct_config: dict) -> CloudSetupDetails:
    cloud_setup = _prepare_gce_resource_setup(sct_config)
    image_id = sct_config.get("scylla_version")
    cloud_setup.db_node.image_id = f"scylladb/scylladb:{image_id}"
    cloud_setup.monitor_node.image_id = sct_config.get("mgmt_docker_image")
    cloud_setup.loader_node.image_id = f"scylladb/scylladb:{image_id}"

    return cloud_setup


def _prepare_k8s_eks_resource_setup(sct_config: dict) -> CloudSetupDetails:
    cloud_setup = _prepare_aws_resource_setup(sct_config)

    return cloud_setup


def _prepare_docker_resource_setup(sct_config: dict) -> CloudSetupDetails:
    db_node_setup = CloudNodesInfo(image_id=sct_config.get('docker_image'),
                                   instance_type="docker",
                                   node_amount=_resolve_node_count(sct_config.get("n_db_nodes")),
                                   post_behaviour=sct_config.get("post_behavior_db_nodes"))
    loader_node_setup = CloudNodesInfo(image_id=sct_config.get('docker_image'),
                                       instance_type="docker",
                                       node_amount=_resolve_node_count(sct_config.get("n_loaders")),
                                       post_behaviour=sct_config.get("post_behavior_loader_nodes"))
    monitor_node_setup = CloudNodesInfo(image_id=sct_config.get('docker_image'),
                                        instance_type="docker",
                                        node_amount=_resolve_node_count(sct_config.get("n_monitor_nodes")),
                                        post_behaviour=sct_config.get("post_behavior_monitor_nodes"))
    cloud_setup = CloudSetupDetails(db_node=db_node_setup, loader_node=loader_node_setup,
                                    monitor_node=monitor_node_setup, backend=sct_config.get("cluster_backend"))

    return cloud_setup


XCLOUD_PROVIDER_MAP = {
    "aws": _prepare_aws_resource_setup,
    "gce": _prepare_gce_resource_setup,
}


def _prepare_xcloud_resource_setup(sct_config: dict) -> CloudSetupDetails:
    """Scylla Cloud (xcloud) backend.

    Loaders and monitors are regular VMs on the underlying provider (``xcloud_provider``), so their
    setup follows that provider's config keys. DB nodes are managed by Scylla Cloud:

    - "standard" clusters are created with the configured instance type and node count;
    - "xcloud" clusters (``xcloud_scaling_config`` set) let Scylla Cloud pick the instance type and
      node count from the scaling policy, so both stay unset here and are filled in from the
      resources SCT registers once the cluster is up (see ``SCTTestRun.sync_db_node_setup_from_resources``).
    """
    provider = str(sct_config.get("xcloud_provider") or "").lower()
    if provider not in XCLOUD_PROVIDER_MAP:
        LOGGER.warning("Unknown xcloud provider encountered: %s", provider or None)
    cloud_setup = XCLOUD_PROVIDER_MAP.get(provider, _prepare_unknown_resource_setup)(sct_config)

    scaling_config = _as_mapping(sct_config.get("xcloud_scaling_config"))
    vpc_peering = _as_mapping(sct_config.get("xcloud_vpc_peering"))
    cloud_setup.cluster_type = XCLOUD_CLUSTER_TYPE_XCLOUD if scaling_config else XCLOUD_CLUSTER_TYPE_STANDARD
    cloud_setup.network_type = (XCLOUD_NETWORK_TYPE_PRIVATE_VPC if vpc_peering.get("enabled")
                                else XCLOUD_NETWORK_TYPE_PUBLIC)

    cloud_setup.db_node.image_id = sct_config.get("scylla_version")
    if scaling_config:
        cloud_setup.db_node.instance_type = None
        cloud_setup.db_node.node_amount = None

    return cloud_setup


class ResourceSetup:
    BACKEND_MAP = {
        "aws": _prepare_aws_resource_setup,
        "aws-siren": _prepare_aws_resource_setup,
        "azure": _prepare_azure_resource_setup,
        "oci": _prepare_oci_resource_setup,
        "gce": _prepare_gce_resource_setup,
        "gce-siren": _prepare_gce_resource_setup,
        "k8s-eks": _prepare_k8s_eks_resource_setup,
        "k8s-gke": _prepare_k8s_gke_resource_setup,
        "k8s-gce-minikube": _prepare_k8s_gce_minikube_resource_setup,
        "baremetal": _prepare_bare_metal_resource_setup,
        "docker": _prepare_docker_resource_setup,
        XCLOUD_BACKEND: _prepare_xcloud_resource_setup,
        "unknown": _prepare_unknown_resource_setup,
    }

    @classmethod
    def get_resource_setup(cls, backend: str, sct_config: dict) -> CloudSetupDetails:
        return cls.BACKEND_MAP.get(backend, _prepare_unknown_resource_setup)(sct_config)
