# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import getpass
import socket
import datetime
import logging
import subprocess
from collections import defaultdict
import pprint
import fnmatch
import concurrent.futures
import json
from json import JSONDecodeError
from functools import cached_property

import six
import pytest
import requests
from _pytest.runner import pytest_runtest_makereport as _makereport

from argus.client.generic.client import ArgusGenericClient

LOGGER = logging.getLogger("argus-reporter")


def parse_json(value: str) -> dict:
    try:
        return json.loads(value)
    except JSONDecodeError as ex:
        raise ValueError(f"--argus-extra-headers should be in json format:\n\n{value}\n\n{ex}")


def pytest_runtest_makereport(item, call):
    report = _makereport(item, call)
    report.keywords = list([m.name for m in item.iter_markers()])
    return report


def pytest_addoption(parser):
    group = parser.getgroup("argus-reporter")

    group.addoption(
        "--argus-run-id",
        action="store",
        dest="run_id",
        default=os.environ.get("ARGUS_RUN_ID", None),
        help="Test ID to be used for reporting",
    )

    group.addoption(
        "--argus-test-type",
        action="store",
        dest="test_type",
        default=os.environ.get("ARGUS_TEST_TYPE", None),
        help="Test type to be used for reporting",
    )

    group.addoption(
        "--argus-post-reports",
        action="store_true",
        dest="post_reports",
        default=False,
        help="Post reports to Argus",
    )

    group.addoption(
        "--argus-no-post-reports",
        action="store_false",
        dest="post_reports",
        default=None,
        help="Don't post reports to Argus",
    )

    group.addoption(
        "--argus-api-key",
        action="store",
        dest="api_key",
        default=None,
        help="Argus API key for authorization",
    )

    group.addoption(
        "--argus-base-url",
        action="store",
        dest="base_url",
        default="https://argus.scylladb.com",
        help="Base URL for argus instance",
    )

    group.addoption(
        "--argus-extra-headers",
        action="store",
        dest="extra_headers",
        type=parse_json,
        default="{}",
        help="extra headers to pass to argus, should be in json format",
    )

    group.addoption(
        "--argus-slices",
        action="store_true",
        dest="slices",
        default=False,
        help="Splice collected tests base on history data",
    )

    group.addoption(
        "--argus-max-splice-time",
        action="store",
        type=float,
        dest="max_splice_time",
        default=60,
        help="Max duration of each splice, in minutes",
    )
    group.addoption(
        "--argus-default-test-time",
        action="store",
        type=float,
        dest="default_test_time",
        default=120,
        help="Default time for a test, if history isn't found for it, in seconds",
    )


def pytest_configure(config):
    # prevent opening argus-reporter on slave nodes (xdist)
    config.argus = ArgusReporter(config)
    config.argus.is_slave = hasattr(config, "slaveinput")
    config.pluginmanager.register(config.argus, "argus-reporter-runtime")


def pytest_unconfigure(config):
    argus = getattr(config, "argus", None)
    if argus:
        del config.argus
        config.pluginmanager.unregister(argus)


def get_username():
    try:
        return getpass.getuser()
    except ImportError:
        try:
            return os.getlogin()
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001
            # seems like there are case we can't get the name of the user that is currently running
            LOGGER.warning("couldn't figure out which user is currently running setting to 'unknown'")
            LOGGER.warning(
                "see https://docs.python.org/3/library/getpass.html#getpass.getuser, "
                "if you want to configure it correctly"
            )
            return "unknown"


class ArgusReporter(object):  # pylint: disable=too-many-instance-attributes
    def __init__(self, config):
        self.post_reports = config.getoption("post_reports")

        self.run_id = config.getoption("run_id")
        self.test_type = config.getoption("test_type")

        self.base_url = config.getoption("base_url")
        self.api_key = config.getoption("api_key")
        self.extra_headers = config.getoption("extra_headers")
        self.max_splice_time = config.getoption("max_splice_time")
        self.default_test_time = config.getoption("default_test_time")
        if self.post_reports:
            assert self.run_id and self.test_type, (
                "'--argus-run-id' and '--argus-test-type' should be set, "
                "or set ARGUS_RUN_ID and ARGUS_TEST_TYPE environment variables"
            )

        self.session_data = dict()
        self.session_data["username"] = get_username()
        self.session_data["hostname"] = socket.gethostname()
        self.test_data = defaultdict(dict)
        self.reports = defaultdict(list)
        self.config = config
        self.is_slave = False
        self.slices_query_fields = dict()

    @cached_property
    def argus_client(self):
        return ArgusGenericClient(auth_token=self.api_key, base_url=self.base_url, extra_headers=self.extra_headers)

    def append_test_data(self, request, test_data):
        self.test_data[request.node.nodeid].update(**test_data)

    def cache_report(self, report_item, outcome):
        nodeid = getattr(report_item, "nodeid", report_item)
        # local hack to handle xdist report order
        slavenode = getattr(report_item, "node", None)
        self.reports[nodeid, slavenode].append((report_item, outcome))

    def get_reports(self, report_item):
        nodeid = getattr(report_item, "nodeid", report_item)
        # local hack to handle xdist report order
        slavenode = getattr(report_item, "node", None)
        return self.reports.get((nodeid, slavenode), [])

    @staticmethod
    def get_failure_messge(item_report):
        if hasattr(item_report, "longreprtext"):
            message = item_report.longreprtext
        elif hasattr(item_report.longrepr, "reprcrash"):
            message = item_report.longrepr.reprcrash.message
        elif isinstance(item_report.longrepr, six.string_types):
            message = item_report.longrepr
        else:
            message = str(item_report.longrepr)
        return message

    def get_worker_id(self):
        # based on https://github.com/pytest-dev/pytest-xdist/pull/505
        # (to support older version of xdist)
        worker_id = "default"
        if hasattr(self.config, "workerinput"):
            worker_id = self.config.workerinput["workerid"]
        if not hasattr(self.config, "workerinput") and getattr(self.config.option, "dist", "no") != "no":
            worker_id = "master"
        return worker_id

    def pytest_runtest_logreport(self, report):
        # pylint: disable=too-many-branches

        if report.passed:
            if report.when == "call":
                if hasattr(report, "wasxfail"):
                    self.cache_report(report, "xpass")
                else:
                    self.cache_report(report, "passed")
        elif report.failed:
            if report.when == "call":
                self.cache_report(report, "failure")
            elif report.when == "setup":
                self.cache_report(report, "error")
        elif report.skipped:
            if hasattr(report, "wasxfail"):
                self.cache_report(report, "xfailed")
            else:
                self.cache_report(report, "skipped")

        if report.when == "teardown":
            # in xdist, report only on worker nodes
            if self.get_worker_id() != "master":
                old_reports = self.get_reports(report)
                for old_report in old_reports:
                    if report.passed and old_report:
                        self.report_test(old_report[0], old_report[1])
                    if report.failed and old_report:
                        self.report_test(report, old_report[1] + " & error", old_report=old_report[0])
                    if report.skipped:
                        self.report_test(report, "skipped")

    def report_test(self, item_report, outcome, old_report=None):
        test_data = dict(
            item_report.user_properties,
            timestamp=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
            name=item_report.nodeid,
            outcome=outcome,
            duration=item_report.duration,
            markers=item_report.keywords,
            **self.session_data,
        )
        context = getattr(item_report, "context", None)
        if context:
            test_data.update(subtest=context.msg)
        test_data.update(self.test_data[item_report.nodeid])
        del self.test_data[item_report.nodeid]

        message = self.get_failure_messge(item_report)
        if old_report:
            message += self.get_failure_messge(old_report)
        if message:
            test_data.update(failure_message=message)
        self.post_to_argus(test_data)

    def pytest_sessionstart(self):
        self.session_data["session_start_time"] = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    def pytest_internalerror(self, excrepr):
        test_data = dict(
            timestamp=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
            outcome="internal-error",
            faiure_message=str(excrepr),
            **self.session_data,
        )
        self.post_to_argus(test_data)

    def post_to_argus(self, test_data):
        if self.post_reports and not self.is_slave:
            try:
                request_data = dict()

                request_data["name"] = test_data.pop("name")

                request_data["test_type"] = self.test_type
                request_data["run_id"] = self.run_id
                request_data["message"] = test_data.pop("failure_message", None)
                request_data["status"] = test_data.pop("outcome")
                request_data["duration"] = test_data.pop("duration")
                request_data["timestamp"] = test_data.pop("timestamp")
                request_data["session_timestamp"] = test_data.pop("session_start_time")
                request_data["markers"] = test_data.pop("markers", [])
                request_data["user_fields"] = {str(k): str(v) for k, v in test_data.items()}
                res = self.argus_client.post(
                    endpoint="/testrun/pytest/result/submit", location_params={}, body=request_data
                )
                res.raise_for_status()

            except Exception as ex:  # pylint: disable=broad-except  # noqa: BLE001
                LOGGER.warning("Failed to POST to argus: [%s]", str(ex))

    def fetch_test_duration(self, collected_test_list, default_time_sec=120.0, max_workers=20):
        """
        fetch test 95 percentile duration of a list of tests

        :param collected_test_list: the names of the test to lookup
        :param default_time_sec: the time to return when no history data found
        :param max_workers: number of threads to use for concurrency

        :returns: map from test_id to 95 percentile duration
        """

        test_durations = []

        def get_test_stats(test_id):
            try:
                res = self.argus_client.get(
                    endpoint=f"/testrun/pytest/{test_id}/stats/duration/avg",
                    location_params=dict(),
                    params=self.slices_query_fields,
                )
                res.raise_for_status()
                test_data = next(iter(res.json()["response"].values()), dict())
                return dict(test_name=test_id, duration=test_data["duration"]["avg"])
            except (requests.exceptions.ReadTimeout, requests.exceptions.HTTPError):
                LOGGER.warning("Failed to fetch test duration for %s", test_id)
                return dict(test_name=test_id, duration=None)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_test_id = {executor.submit(get_test_stats, test_id): test_id for test_id in collected_test_list}
            for future in concurrent.futures.as_completed(future_to_test_id):
                test_id = future_to_test_id[future]
                try:
                    test_durations.append(future.result())
                except Exception:  # pylint: disable=broad-except
                    LOGGER.exception("'%s' generated an exception", test_id)

        for test in test_durations:
            if not test["duration"]:
                test["duration"] = default_time_sec
        test_durations.sort(key=lambda x: x["duration"])
        LOGGER.debug(pprint.pformat(test_durations))

        return test_durations

    @staticmethod
    def clear_old_exclude_files(outputdir):
        print("clear old exclude files")
        # Get a list of all files in directory
        for root_dir, _, filenames in os.walk(outputdir):
            # Find the files that matches the given pattern
            for filename in fnmatch.filter(filenames, "include_*.txt"):
                try:
                    os.remove(os.path.join(root_dir, filename))
                except OSError:
                    print("Error while deleting file {}".format(filename))

    @staticmethod
    def split_files_test_list(outputdir, slices):
        for i, current_slice in enumerate(slices):
            print(
                "{}: {} ".format(i, datetime.timedelta(0, current_slice["total"]))
                + "- {} - {}".format(len(current_slice["tests"]), current_slice["tests"])
            )
            include_filename = os.path.join(outputdir, "include_%03d.txt" % i)

            with open(include_filename, "w") as slice_file:
                for case in current_slice["tests"]:
                    slice_file.write(case + "\n")

    @staticmethod
    def make_test_slices(test_data, max_slice_duration):
        slices = []
        while test_data:
            current_test = test_data.pop(0)
            for current_slice in slices:
                if current_slice["total"] + float(current_test["duration"]) > max_slice_duration:
                    continue
                current_slice["total"] += float(current_test["duration"])
                current_slice["tests"] += [current_test["test_name"]]
                break
            else:
                slices += [dict(total=0.0, tests=[])]
                current_slice = slices[-1]
                current_slice["total"] += float(current_test["duration"])
                current_slice["tests"] += [current_test["test_name"]]
        return slices

    def pytest_collection_finish(self, session):
        if self.config.getoption("slices"):
            assert self.default_test_time and self.max_splice_time, (
                "'--argus-max-splice-time' and '--argus-default-test-time' should be positive numbers"
            )
            test_history_data = self.fetch_test_duration(
                [item.nodeid.replace("::()", "") for item in session.items],
                default_time_sec=self.default_test_time,
            )
            slices = self.make_test_slices(test_history_data, max_slice_duration=self.max_splice_time * 60)
            LOGGER.debug(pprint.pformat(slices))
            self.clear_old_exclude_files(outputdir=".")
            self.split_files_test_list(outputdir=".", slices=slices)


@pytest.fixture(scope="session")
def argus_reporter(request):
    return request.config.pluginmanager.get_plugin("argus-reporter-runtime")


@pytest.fixture(scope="session", autouse=True)
def jenkins_data(request):
    """
    Append jenkins job and user data into results session
    """
    # TODO: maybe filter some, like password/token and such ?
    jenkins_env = {k.lower(): v for k, v in os.environ.items() if k.startswith("JENKINS_")}

    argus = request.config.pluginmanager.get_plugin("argus-reporter-runtime")
    argus.session_data.update(**jenkins_env)


@pytest.fixture(scope="session", autouse=True)
def circle_data(request):
    """
    Append circle ci job and user data into results session
    """
    if os.environ.get("CIRCLECI", "") == "true":
        # TODO: maybe filter some, like password/token and such ?
        circle_env = {k.lower(): v for k, v in os.environ.items() if k.startswith("CIRCLE_")}

        argus = request.config.pluginmanager.get_plugin("argus-reporter-runtime")
        argus.session_data.update(**circle_env)


@pytest.fixture(scope="session", autouse=True)
def travis_data(request):
    """
    Append travis ci job and user data into results session
    """
    if os.environ.get("TRAVIS", "") == "true":
        travis_env = {k.lower(): v for k, v in os.environ.items() if k.startswith("TRAVIS_")}

        argus = request.config.pluginmanager.get_plugin("argus-reporter-runtime")
        argus.session_data.update(**travis_env)


@pytest.fixture(scope="session", autouse=True)
def github_data(request):
    """
    Append github ci job and user data into results session
    """
    if os.environ.get("GITHUB_ACTIONS", "") == "true":
        github_env = {k.lower(): v for k, v in os.environ.items() if k.startswith("GITHUB_")}

        argus = request.config.pluginmanager.get_plugin("argus-reporter-runtime")
        argus.session_data.update(**github_env)


@pytest.fixture(scope="session", autouse=True)
def git_data(request):
    """
    Append git information into results session
    """

    try:
        from subprocess import DEVNULL  # noqa: PLC0415
    except ImportError:
        DEVNULL = open(os.devnull, "wb")

    git_info = dict()
    cmds = (
        ("git_commit_oneline", "git log --oneline  -1 --no-decorate"),
        ("git_commit_full", "git log -1 --no-decorate"),
        ("git_commit_sha", "git rev-parse HEAD"),
        ("git_commit_sha_short", "git rev-parse --short HEAD"),
        ("git_branch", "git rev-parse --abbrev-ref HEAD"),
        ("git_repo", "git config --get remote.origin.url"),
    )
    for key, command in cmds:
        try:
            git_info[key] = subprocess.check_output(command, shell=True, stderr=DEVNULL).decode("utf-8").strip()
        except subprocess.CalledProcessError:
            pass
    argus = request.config.pluginmanager.get_plugin("argus-reporter-runtime")
    argus.session_data.update(**git_info)
