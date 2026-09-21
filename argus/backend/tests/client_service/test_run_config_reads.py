from argus.backend.tests.client_service.test_run_config_index import CONFIG, make_run, submit_config


def test_get_config_params_reads_the_by_run_partition(api_client, client_service, testrun_service, fake_test):
    run = make_run(client_service, testrun_service, fake_test)
    submit_config(api_client, run.id, CONFIG)

    params = testrun_service.get_run("scylla-cluster-tests", run.id).get_config_params()

    assert params["sct_config.backend"] == "aws"
    assert params["sct_config.nested.inner.deep"] == "10"
