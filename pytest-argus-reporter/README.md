# pytest-argus-reporter

[![PyPI version](https://img.shields.io/pypi/v/pytest-argus-reporter.svg?style=flat)](https://pypi.org/project/pytest-argus-reporter)
[![Python versions](https://img.shields.io/pypi/pyversions/pytest-argus-reporter.svg?style=flat)](https://pypi.org/project/pytest-argus-reporter)
[![.github/workflows/tests.yml](https://github.com/fruch/pytest-argus-reporter/workflows/.github/workflows/tests.yml/badge.svg)](https://github.com/fruch/pytest-argus-reporter/actions?query=branch%3Amaster)
[![Libraries.io dependency status for GitHub repo](https://img.shields.io/librariesio/github/fruch/pytest-argus-reporter.svg?style=flat)](https://libraries.io/github/fruch/pytest-argus-reporter)
[![Using Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/python/black)
[![Codecov Reports](https://codecov.io/gh/fruch/pytest-argus-reporter/branch/master/graph/badge.svg)](https://codecov.io/gh/fruch/pytest-argus-reporter)

A plugin to send pytest tests results to [Argus], with extra context data

## Features

* Report each test result into Argus as they finish
* Automatically append contextual data to each test:
  * git information such as `branch` or `last commit` and more
  * all of CI env variables
    * Jenkins
    * Travis
    * Circle CI
    * Github Actions
  * username if available
* Report a test summary to Argus for each session with all the context data
* Append any user data into the context sent to Argus

## Requirements

* having [pytest] tests written

## Installation

You can install "pytest-argus-reporter" via [pip] from [PyPI]

``` bash
pip install pytest-argus-reporter
```

## Usage

### Run and configure from command line

```bash
pytest --argus-post-reports --argus-base-url http://argus-server.io:8080 --argus-api-key 1234 --extra-headers '{"X-My-Header": "my-value"}'
```

### Configure from code (ideally in conftest.py)

```python
from pytest_argus_reporter import ArgusReporter

def pytest_plugin_registered(plugin, manager):
    if isinstance(plugin, ArgusReporter):
      # TODO: get credentials in more secure fashion programmatically, maybe AWS secrets or the likes
      # or put them in plain-text in the code... what can ever go wrong...
      plugin.base_url = "https://argus.scylladb.com"
      plugin.api_key = "123456" # get it from your user page on Argus
      plugin.test_type = "dtest"
      plugin.extra_headers = {}
```

see [pytest docs](https://docs.pytest.org/en/latest/customize.html)
for more about how to configure pytest using .ini files

### Collect context data for the whole session

In this example, I'll be able to build a dashboard for each version:

```python
import pytest

@pytest.fixture(scope="session", autouse=True)
def report_formal_version_to_argus(request):
    """
    Append my own data specific, for example which of the code under test is used
    """
    # TODO: programmatically set to the version of the code under test...
    my_data = {"formal_version": "1.0.0-rc2" }

    elk = request.config.pluginmanager.get_plugin("argus-reporter-runtime")
    elk.session_data.update(**my_data)
```

### Collect data for specific tests


```python
import requests

def test_my_service_and_collect_timings(request, argus_reporter):
    response = requests.get("http://my-server.io/api/do_something")
    assert response.status_code == 200

    argus_reporter.append_test_data(request, {"do_something_response_time": response.elapsed.total_seconds() })
    # now, a dashboard showing response time by version should be quite easy
    # and yeah, it's not exactly a real usable metric, but it's just one example...
```

Or via the `record_property` built-in fixture (that is normally used to collect data into junit.xml reports):

```python
import requests

def test_my_service_and_collect_timings(record_property):
    response = requests.get("http://my-server.io/api/do_something")
    assert response.status_code == 200

    record_property("do_something_response_time", response.elapsed.total_seconds())
```

## TODO: Split tests based on their duration histories

One cool thing that can be done now that you have a history of the tests,
is to split the tests based on their actual runtime when passing.
For long-running integration tests, this is priceless.

In this example, we're going to split the run into a maximum of 4 min slices.
Any test that doesn't have history information is assumed to be 60 sec long.

```bash
# pytest --collect-only --argus-splice --argus-max-splice-time=4 --argus-default-test-time=60
...

0: 0:04:00 - 3 - ['test_history_slices.py::test_should_pass_1', 'test_history_slices.py::test_should_pass_2', 'test_history_slices.py::test_should_pass_3']
1: 0:04:00 - 2 - ['test_history_slices.py::test_with_history_data', 'test_history_slices.py::test_that_failed']

...

# cat include000.txt
test_history_slices.py::test_should_pass_1
test_history_slices.py::test_should_pass_2
test_history_slices.py::test_should_pass_3

# cat include000.txt
test_history_slices.py::test_with_history_data
test_history_slices.py::test_that_failed

### now we can run each slice on its own machine
### on machine1
# pytest $(cat include000.txt)

### on machine2
# pytest $(cat include001.txt)
```

## Contributing

Contributions are very welcome. Tests can be run with [`nox`][nox]. Please ensure
the coverage at least stays the same before you submit a pull request.

## License

Distributed under the terms of the [Apache][Apache] license, "pytest-argus-reporter" is free and open source software

## Issues

If you encounter any problems, please [file an issue] along with a detailed description.

## Thanks

This [pytest] plugin was generated with [Cookiecutter] along with [@hackebrot]'s [cookiecutter-pytest-plugin] template.

[Argus]: https://github.com/scylladb/argus
[Cookiecutter]: https://github.com/audreyr/cookiecutter
[@hackebrot]: https://github.com/hackebrot
[Apache]: https://opensource.org/license/apache-2-0
[cookiecutter-pytest-plugin]: https://github.com/pytest-dev/cookiecutter-pytest-plugin
[file an issue]: https://github.com/scylladb/argus/issues
[pytest]: https://github.com/pytest-dev/pytest
[nox]: https://nox.thea.codes/
[pip]: https://pypi.org/project/pip/
[PyPI]: https://pypi.org/project
