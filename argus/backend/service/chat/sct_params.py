"""The rules of the SCT parameter wizard on the run page (frontend/TestRun/Jenkins/SCTParameterWizard.svelte),
applied to the parameters of a start proposed from the chat."""
import re

from argus.backend.service.github_service import GithubService
from argus.backend.service.jenkins_service import SCT_VERSION_SOURCE_FAMILIES

BACKENDS = {
    "aws": "Amazon AWS",
    "aws-siren": "Amazon AWS (Siren-tests)",
    "azure": "Microsoft Azure",
    "gce": "Google Cloud",
    "gce-siren": "Google Cloud (Siren-tests)",
    "oci": "Oracle Cloud",
    "k8s-local-kind-aws": "Kubernetes in Docker on AWS",
    "k8s-local-kind-gce": "Kubernetes in Docker on GCE",
    "k8s-eks": "Kubernetes (Amazon EKS)",
    "k8s-gke": "Kubernetes (Google Kubernetes Engine)",
}
BACKEND_GROUPS = {
    "aws": ("aws", "aws-siren", "k8s-local-kind-aws", "k8s-eks"),
    "azure": ("azure",),
    "oci": ("oci",),
    "gce": ("gce", "gce-siren", "k8s-local-kind-gce", "k8s-gke"),
}
REGIONS = {
    "aws": ("region", ("eu-west-1", "eu-west-2", "us-west-2", "us-east-1", "eu-north-1", "eu-central-1")),
    "azure": ("azure_region_name", ("eastus",)),
    "oci": ("oci_region_name", ("us-ashburn-1", "us-phoenix-1")),
    "gce": ("gce_datacenter", ("us-east1", "us-east4", "us-west1", "us-central1")),
}
POST_BEHAVIOR = ("keep", "keep-on-failure", "destroy")
FIXED_VALUES = {
    "backend": tuple(BACKENDS),
    "provision_type": ("spot", "on_demand", "spot_fleet"),
    "post_behavior_db_nodes": POST_BEHAVIOR,
    "post_behavior_loader_nodes": POST_BEHAVIOR,
    "post_behavior_monitor_nodes": POST_BEHAVIOR,
    "post_behavior_k8s_cluster": POST_BEHAVIOR,
}
URL_RE = re.compile(r"^https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_+.~#?&/=]*)$")
FORMATS = {
    "scylla_version": (re.compile(r"^(([\w\-.]+:(latest|\d+|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z))|"
                                  r"(\d+\.\d+(\.\d+)?)((~|-)rc\d)?)$"),
                       "a version such as 2025.1.0~rc1, or branch:latest"),
    "scylla_repo": (URL_RE, "an http(s) link to the .repo or .list file"),
    "new_scylla_repo": (URL_RE, "an http(s) link to the .repo or .list file"),
    "scylla_ami_id": (re.compile(r"^(ami-[abcdef\d]{4,17}|scylla-.+)$"), "ami-<hex id>"),
    "gce_image_db": (re.compile(r"^https://www\.googleapis\.com/compute/v1/.+$"),
                     "https://www.googleapis.com/compute/v1/<image path>"),
    "azure_image_db": (re.compile(r"^/subscriptions/.+$"), "/subscriptions/<image path>"),
    "oci_image_db": (re.compile(r"^ocid1\.image\.oc1\..+\.aaaaaaaa.+$"), "ocid1.image.oc1.<region>.aaaaaaaa<id>"),
    "byo_scylla_repo": (re.compile(r"^git@github\.com:[\w-]+/[\w-]+\.git$"), "git@github.com:<user>/<repo>.git"),
}
BYO_BRANCH = "byo_scylla_branch"
HTML_TAG = re.compile(r"<[^>]+>")
EMAIL_DEFAULT = "qa@scylladb.com"
FIELD_GROUPS = {
    "environment": ("backend", "region", "gce_datacenter", "azure_region_name", "oci_region_name",
                    "availability_zone", "provision_type", "billing_project"),
    "scylla": ("scylla_version", "scylla_repo", "scylla_ami_id", "gce_image_db", "azure_image_db",
               "oci_image_db", "new_scylla_repo", "base_versions", "byo_scylla_repo", BYO_BRANCH,
               "update_db_packages"),
    "test": ("test_name", "test_config", "stress_duration"),
    "post_test": tuple(name for name in FIXED_VALUES if name.startswith("post_behavior_")),
    "reporting": ("email_recipients",),
}
FAMILY_OF = {key: family for family, keys in SCT_VERSION_SOURCE_FAMILIES.items() for key in keys} | {
    BYO_BRANCH: "scylla_byo"}


def backend_group(backend: str | None) -> str | None:
    return next((group for group, members in BACKEND_GROUPS.items() if backend in members), None)


def allowed_values(name: str, params: dict) -> tuple[str, ...] | None:
    if name in FIXED_VALUES:
        return FIXED_VALUES[name]
    group = backend_group(params.get("backend"))
    if group and REGIONS[group][0] == name:
        return REGIONS[group][1]
    return None


def normalize(params: dict[str, str], overrides: dict[str, str]) -> tuple[dict[str, str], set[str]]:
    """The parameters after the overrides, as the wizard and the command line tool leave them, and the names
    whose values the overrides decided."""
    merged = params | overrides
    changed = set(overrides)
    families = {FAMILY_OF[name] for name in overrides if name in FAMILY_OF and str(overrides[name]).strip()}
    if len(families) == 1:
        for name, family in FAMILY_OF.items():
            if family not in families and name in merged and name not in overrides and merged[name]:
                merged[name] = ""
                changed.add(name)
    if "backend" in overrides and (group := backend_group(overrides["backend"])):
        region, values = REGIONS[group]
        if region in merged and not merged[region] and region not in overrides:
            merged[region] = values[0]
            changed.add(region)
    if "email_recipients" in merged and not str(merged["email_recipients"]).strip():
        merged["email_recipients"] = EMAIL_DEFAULT
    return merged, changed


async def check(params: dict[str, str], changed: set[str]) -> str | None:
    """Why the parameters fail the wizard's rules, looking only at the values the overrides decided, so a
    start that repeats an older build keeps its values."""
    for name in sorted(changed):
        value = str(params.get(name) or "")
        if not value:
            continue
        if (values := allowed_values(name, params)) and value not in values:
            return f"{value} is not a supported {name}; use one of {', '.join(values)}"
        if name in FORMATS and not FORMATS[name][0].match(value):
            return f"{name} must be {FORMATS[name][1]}, not {value}"
    if params.get("byo_scylla_repo") and changed & {"byo_scylla_repo", BYO_BRANCH}:
        if not params.get(BYO_BRANCH):
            return "byo_scylla_branch must name the branch of the BYO repository"
        valid, message = await GithubService().validate_repo(params["byo_scylla_repo"], params[BYO_BRANCH])
        if not valid:
            return message
    return None


def fields(params: dict[str, str], job: list[dict], sct: bool) -> list[dict]:
    """The job's parameters for the card and the model: each with its value, its allowed values, its wizard
    group for an SCT job, and the start of its description."""
    group_of = {name: group for group, names in FIELD_GROUPS.items() for name in names} if sct else {}
    result = []
    for param in job:
        name = param["name"]
        entry = {"name": name, "value": params.get(name, param.get("value")), "group": group_of.get(name, "other")}
        if choices := param.get("choices") or (sct and allowed_values(name, params)):
            entry["choices"] = list(choices)
        if description := HTML_TAG.sub("", param.get("description") or "").strip():
            entry["description"] = description[:160]
        result.append(entry)
    order = list(FIELD_GROUPS) + ["other"]
    return sorted(result, key=lambda entry: order.index(entry["group"]))
