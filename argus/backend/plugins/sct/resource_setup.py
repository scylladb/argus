import logging
from argus.backend.plugins.sct.udt import CloudNodesInfo, CloudSetupDetails

LOGGER = logging.getLogger(__name__)


def _get_node_amounts(config: dict) -> tuple[int, int]:
    num_db_node = config.get("n_db_nodes")
    num_db_node = sum([int(i) for i in num_db_node.split()]) if isinstance(num_db_node, str) else num_db_node
    num_loaders = config.get("n_loaders")
    num_loaders = sum([int(i) for i in num_loaders.split()]) if isinstance(num_loaders, str) else num_loaders

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
                                        node_amount=sct_config.get("n_monitor_nodes"),
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
                                        node_amount=sct_config.get("n_monitor_nodes"),
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
                                        node_amount=sct_config.get("n_monitor_nodes"),
                                        post_behaviour=sct_config.get("post_behavior_monitor_nodes"))
    cloud_setup = CloudSetupDetails(db_node=db_node_setup, loader_node=loader_node_setup,
                                    monitor_node=monitor_node_setup, backend=sct_config.get("cluster_backend"))

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
                                   node_amount=sct_config.get("n_db_nodes"),
                                   post_behaviour=sct_config.get("post_behavior_db_nodes"))
    loader_node_setup = CloudNodesInfo(image_id="bare_metal",
                                       instance_type="bare_metal",
                                       node_amount=sct_config.get("n_loaders"),
                                       post_behaviour=sct_config.get("post_behavior_loader_nodes"))
    monitor_node_setup = CloudNodesInfo(image_id="bare_metal",
                                        instance_type="bare_metal",
                                        node_amount=sct_config.get("n_monitor_nodes"),
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
                                   node_amount=sct_config.get("n_db_nodes"),
                                   post_behaviour=sct_config.get("post_behavior_db_nodes"))
    loader_node_setup = CloudNodesInfo(image_id=sct_config.get('docker_image'),
                                       instance_type="docker",
                                       node_amount=sct_config.get("n_loaders"),
                                       post_behaviour=sct_config.get("post_behavior_loader_nodes"))
    monitor_node_setup = CloudNodesInfo(image_id=sct_config.get('docker_image'),
                                        instance_type="docker",
                                        node_amount=sct_config.get("n_monitor_nodes"),
                                        post_behaviour=sct_config.get("post_behavior_monitor_nodes"))
    cloud_setup = CloudSetupDetails(db_node=db_node_setup, loader_node=loader_node_setup,
                                    monitor_node=monitor_node_setup, backend=sct_config.get("cluster_backend"))

    return cloud_setup


class ResourceSetup:
    # pylint: disable=too-few-public-methods
    BACKEND_MAP = {
        "aws": _prepare_aws_resource_setup,
        "aws-siren": _prepare_aws_resource_setup,
        "azure": _prepare_azure_resource_setup,
        "gce": _prepare_gce_resource_setup,
        "gce-siren": _prepare_gce_resource_setup,
        "k8s-eks": _prepare_k8s_eks_resource_setup,
        "k8s-gke": _prepare_k8s_gke_resource_setup,
        "k8s-gce-minikube": _prepare_k8s_gce_minikube_resource_setup,
        "baremetal": _prepare_bare_metal_resource_setup,
        "docker": _prepare_docker_resource_setup,
        "unknown": _prepare_unknown_resource_setup,
    }

    @classmethod
    def get_resource_setup(cls, backend: str, sct_config: dict) -> CloudSetupDetails:
        return cls.BACKEND_MAP.get(backend, _prepare_unknown_resource_setup)(sct_config)
