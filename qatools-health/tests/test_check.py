import pytest

from qatools_health import CallableHealthCheck, HealthCheck, Severity, healthcheck, strictest_severity
from qatools_health.check import freeze
from qatools_health.checks import StalenessHealthCheck
from qatools_health.runner import merge_policy


class ProbeCheck(HealthCheck):
    name = "probe"
    severity = Severity.CRITICAL
    interval = 30.0

    async def perform_check(self):
        return None


class ArgumentCheck(HealthCheck):
    name = "arguments"

    def __init__(self, url, *, headers=None, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.headers = headers

    async def perform_check(self):
        return None


def test_class_attributes_become_the_defaults():
    check = ProbeCheck()
    assert (check.name, check.severity, check.interval) == ("probe", Severity.CRITICAL, 30.0)
    assert check.timeout == 10.0
    assert check.stale_after_intervals == 3.0


def test_the_default_severity_is_important():
    class Plain(HealthCheck):
        name = "plain"

        async def perform_check(self):
            return None

    assert Plain().severity is Severity.IMPORTANT


def test_constructor_overrides_one_instance_only():
    override = ProbeCheck(name="probe:second", severity="optional", interval=5, timeout=1)
    assert (override.name, override.severity, override.interval, override.timeout) == (
        "probe:second",
        Severity.OPTIONAL,
        5.0,
        1.0,
    )
    assert ProbeCheck().severity is Severity.CRITICAL


def test_a_check_without_a_name_is_rejected():
    class Unnamed(HealthCheck):
        async def perform_check(self):
            return None

    with pytest.raises(ValueError, match="has no name"):
        Unnamed()


@pytest.mark.parametrize("kwargs", [{"interval": 0}, {"timeout": -1}, {"stale_after_intervals": 0}])
def test_non_positive_schedule_values_are_rejected(kwargs):
    with pytest.raises(ValueError, match="must be positive"):
        ProbeCheck(**kwargs)


async def test_aclose_is_a_no_op_by_default():
    assert await ProbeCheck().aclose() is None


async def test_the_decorator_builds_an_instance():
    @healthcheck(name="queue_depth", interval=30)
    async def queue_depth():
        return True

    assert isinstance(queue_depth, CallableHealthCheck)
    assert (queue_depth.name, queue_depth.interval) == ("queue_depth", 30.0)
    assert await queue_depth.perform_check() is True


async def test_the_decorator_takes_the_function_name():
    @healthcheck
    async def api_queue_depth():
        return None

    assert api_queue_depth.name == "api_queue_depth"


def test_the_decorator_rejects_a_synchronous_function():
    with pytest.raises(TypeError, match="not an async function"):

        @healthcheck(name="blocking")
        def blocking():
            return True


def test_repr_names_the_check_and_hides_the_arguments():
    rendered = repr(ArgumentCheck("https://jira.test", headers={"Authorization": "token secret"}))
    assert "arguments" in rendered
    assert "secret" not in rendered


def test_two_instances_of_one_dependency_share_an_identity():
    assert ArgumentCheck("https://jira.test").identity() == ArgumentCheck("https://jira.test").identity()


def test_a_different_argument_is_a_different_dependency():
    assert ArgumentCheck("https://jira.test").identity() != ArgumentCheck("https://other.test").identity()


def test_another_class_over_one_argument_is_another_dependency():
    class Second(ArgumentCheck):
        name = "second"

    assert ArgumentCheck("https://jira.test").identity() != Second("https://jira.test").identity()


def test_policy_keywords_stay_out_of_the_identity():
    plain = ArgumentCheck("https://jira.test")
    tuned = ArgumentCheck("https://jira.test", name="jira", severity=Severity.CRITICAL, interval=5, timeout=1)
    assert plain.identity() == tuned.identity()


def test_an_unhashable_argument_still_yields_an_identity():
    first = ArgumentCheck("https://jira.test", headers={"Accept": "application/json"})
    second = ArgumentCheck("https://jira.test", headers={"Accept": "application/json"})
    assert first.identity() == second.identity()
    assert first.identity() != ArgumentCheck("https://jira.test", headers={"Accept": "text/plain"}).identity()


def test_the_identity_of_a_decorated_function_is_the_function():
    async def queue_depth():
        return None

    assert healthcheck(queue_depth, name="a").identity() == healthcheck(queue_depth, name="a").identity()


def test_freeze_keeps_a_container_comparable():
    assert freeze([1, {"b": 2}]) == (1, (("b", 2),))
    assert freeze({1, 2}) == frozenset({1, 2})
    assert freeze("token") == "token"


def test_freeze_falls_back_to_the_object_for_an_unhashable_leaf():
    class Unhashable:
        __hash__ = None

    leaf = Unhashable()
    assert freeze(leaf) == ("Unhashable", id(leaf))


def test_two_decorated_functions_are_two_dependencies():
    @healthcheck
    async def scylla():
        return True

    @healthcheck
    async def jenkins():
        return True

    assert scylla.identity() != jenkins.identity()


def test_a_bound_method_of_the_check_stays_out_of_the_identity():
    class Bound(HealthCheck):
        name = "bound"

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.probe = self.perform_check

        async def perform_check(self):
            return None

    assert Bound().identity() == Bound().identity()
    assert "probe" not in Bound().identity_fields()


def test_two_staleness_getters_are_two_dependencies():
    def jenkins_poll():
        return 0.0

    def github_poll():
        return 0.0

    first = StalenessHealthCheck(jenkins_poll, 60, 600, name="poll")
    second = StalenessHealthCheck(github_poll, 60, 600, name="poll")
    assert first.identity() != second.identity()
    assert first.identity() == StalenessHealthCheck(jenkins_poll, 60, 600, name="poll").identity()


@pytest.mark.parametrize(
    ("running", "incoming"),
    [
        ((Severity.CRITICAL, 10.0), (Severity.OPTIONAL, 600.0)),
        ((Severity.OPTIONAL, 600.0), (Severity.CRITICAL, 10.0)),
        ((Severity.IMPORTANT, 10.0), (Severity.CRITICAL, 600.0)),
        ((Severity.CRITICAL, 600.0), (Severity.IMPORTANT, 10.0)),
    ],
)
def test_a_merged_policy_never_lowers_the_severity_and_keeps_the_shorter_interval(running, incoming):
    check = ProbeCheck(severity=running[0], interval=running[1])
    merge_policy(check, ProbeCheck(severity=incoming[0], interval=incoming[1]))
    assert check.severity is strictest_severity(running[0], incoming[0])
    assert check.interval == min(running[1], incoming[1])


def test_a_lower_severity_leaves_a_critical_check_critical():
    check = ProbeCheck(severity=Severity.CRITICAL, interval=30)
    for lower in (Severity.IMPORTANT, Severity.OPTIONAL):
        merge_policy(check, ProbeCheck(severity=lower, interval=900))
    assert (check.severity, check.interval) == (Severity.CRITICAL, 30.0)
