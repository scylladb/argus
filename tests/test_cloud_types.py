import pytest
from pydantic import ValidationError
from argus.db.cloud_types import CloudResource, CloudInstanceDetails, ResourceState


def test_cloud_instance_details_ip_validation_valid_ip():
    instance_info = CloudInstanceDetails(provider="aws", region="eu-west-1", ip="127.0.0.1", private_ip="10.10.10.1")

    assert instance_info.ip == "127.0.0.1" and instance_info.private_ip == "10.10.10.1"


def test_cloud_instance_details_ip_validation_invalid_ip():
    with pytest.raises(ValidationError):
        CloudInstanceDetails(provider="aws", region="eu-west-1", ip="iofdgujbiojxc", private_ip="adkjofhskjlgh")


def test_cloud_instance_details_ip_validation_valid_notation_invalid_octects():
    with pytest.raises(ValidationError):
        CloudInstanceDetails(provider="aws", region="eu-west-1", ip="256.725.513.999", private_ip="521.231.132.5436")


def test_cloud_resource_enum_only_state():
    instance_info = CloudInstanceDetails(provider="aws", region="eu-west-1", ip="127.0.0.1", private_ip="10.10.10.1")
    resource = CloudResource(name="test", resource_state=ResourceState.RUNNING, instance_info=instance_info)

    with pytest.raises(ValueError):
        resource.state = "ASFJKGDSHGKJSG"


def test_cloud_resource_state_coercion():
    instance_info = CloudInstanceDetails(provider="aws", region="eu-west-1", ip="127.0.0.1", private_ip="10.10.10.1")
    resource = CloudResource(name="test", resource_state="running", instance_info=instance_info)

    assert resource.resource_state == ResourceState.RUNNING
