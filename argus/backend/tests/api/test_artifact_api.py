import json
from unittest.mock import Mock, patch, MagicMock
from urllib.parse import quote
from botocore.exceptions import ClientError
import pytest

from argus.backend.service.testrun import TestRunServiceException


class TestResolveArtifactSize:
    """Tests for /api/v1/artifact/resolveSize endpoint"""

    @staticmethod
    def _make_request(flask_client, url: str):
        """Helper method to make a request with properly encoded URL parameter"""
        return flask_client.get(f"/api/v1/artifact/resolveSize?l={quote(url, safe='')}")

    def test_resolve_artifact_size_valid_s3_url(self, flask_client):
        """Test resolving artifact size for a valid S3 URL with existing object"""
        s3_url = "https://test-bucket.s3.amazonaws.com/test-folder/test-file.txt"
        
        with patch('argus.backend.service.testrun.boto3.client') as mock_boto_client:
            mock_s3 = Mock()
            mock_s3.get_object.return_value = {"ContentLength": 12345}
            mock_boto_client.return_value = mock_s3
            
            response = self._make_request(flask_client, s3_url)
            
            assert response.status_code == 200
            data = response.json
            assert data["status"] == "ok"
            assert data["response"]["artifactSize"] == 12345

    def test_resolve_artifact_size_s3_no_such_key(self, flask_client):
        """Test resolving artifact size for S3 URL when the object doesn't exist"""
        s3_url = "https://test-bucket.s3.amazonaws.com/nonexistent/file.txt"
        
        with patch('argus.backend.service.testrun.boto3.client') as mock_boto_client:
            mock_s3 = Mock()
            error_response = {
                'Error': {
                    'Code': 'NoSuchKey',
                    'Message': 'The specified key does not exist.'
                }
            }
            mock_s3.get_object.side_effect = ClientError(error_response, 'GetObject')
            mock_boto_client.return_value = mock_s3
            
            response = self._make_request(flask_client, s3_url)
            
            assert response.status_code == 200
            data = response.json
            assert data["status"] == "error"
            assert "not found" in data["response"]["message"].lower()

    def test_resolve_artifact_size_s3_access_denied(self, flask_client):
        """Test resolving artifact size for S3 URL when access is denied"""
        s3_url = "https://test-bucket.s3.amazonaws.com/restricted/file.txt"
        
        with patch('argus.backend.service.testrun.boto3.client') as mock_boto_client:
            mock_s3 = Mock()
            error_response = {
                'Error': {
                    'Code': 'AccessDenied',
                    'Message': 'Access Denied'
                }
            }
            mock_s3.get_object.side_effect = ClientError(error_response, 'GetObject')
            mock_boto_client.return_value = mock_s3
            
            response = self._make_request(flask_client, s3_url)
            
            assert response.status_code == 200
            data = response.json
            assert data["status"] == "error"
            assert "access denied" in data["response"]["message"].lower()

    def test_resolve_artifact_size_s3_other_error(self, flask_client):
        """Test resolving artifact size for S3 URL with other boto3 errors"""
        s3_url = "https://test-bucket.s3.amazonaws.com/test-folder/file.txt"
        
        with patch('argus.backend.service.testrun.boto3.client') as mock_boto_client:
            mock_s3 = Mock()
            error_response = {
                'Error': {
                    'Code': 'ServiceUnavailable',
                    'Message': 'Service is temporarily unavailable'
                }
            }
            mock_s3.get_object.side_effect = ClientError(error_response, 'GetObject')
            mock_boto_client.return_value = mock_s3
            
            response = self._make_request(flask_client, s3_url)
            
            assert response.status_code == 200
            data = response.json
            assert data["status"] == "error"
            assert "error accessing s3 object" in data["response"]["message"].lower()

    def test_resolve_artifact_size_valid_http_url_with_content_length(self, flask_client):
        """Test resolving artifact size for a valid HTTP URL with Content-Length header"""
        http_url = "https://example.com/test-file.zip"
        
        with patch('argus.backend.service.testrun.requests.head') as mock_head:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Length": "54321"}
            mock_head.return_value = mock_response
            
            response = self._make_request(flask_client, http_url)
            
            assert response.status_code == 200
            data = response.json
            assert data["status"] == "ok"
            assert data["response"]["artifactSize"] == 54321

    def test_resolve_artifact_size_http_url_without_content_length(self, flask_client):
        """Test resolving artifact size for HTTP URL without Content-Length header"""
        http_url = "https://example.com/streaming-content"
        
        with patch('argus.backend.service.testrun.requests.head') as mock_head:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_head.return_value = mock_response
            
            response = self._make_request(flask_client, http_url)
            
            assert response.status_code == 200
            data = response.json
            assert data["status"] == "ok"
            assert data["response"]["artifactSize"] is None

    def test_resolve_artifact_size_http_url_not_found(self, flask_client):
        """Test resolving artifact size for HTTP URL that returns 404"""
        http_url = "https://example.com/nonexistent.zip"
        
        with patch('argus.backend.service.testrun.requests.head') as mock_head:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_head.return_value = mock_response
            
            response = self._make_request(flask_client, http_url)
            
            assert response.status_code == 200
            data = response.json
            assert data["status"] == "error"
            # The endpoint raises a generic Exception for non-200 status codes
            assert "exception" in data["response"]

    def test_resolve_artifact_size_no_link_provided(self, flask_client):
        """Test resolving artifact size without providing a link parameter"""
        response = flask_client.get("/api/v1/artifact/resolveSize")
        
        assert response.status_code == 200
        data = response.json
        assert data["status"] == "error"
        assert "exception" in data["response"]

    def test_resolve_artifact_size_s3_with_region(self, flask_client):
        """Test resolving artifact size for S3 URL with region specified"""
        s3_url = "https://test-bucket.s3.us-west-2.amazonaws.com/test-folder/file.txt"
        
        with patch('argus.backend.service.testrun.boto3.client') as mock_boto_client:
            mock_s3 = Mock()
            mock_s3.get_object.return_value = {"ContentLength": 99999}
            mock_boto_client.return_value = mock_s3
            
            response = self._make_request(flask_client, s3_url)
            
            assert response.status_code == 200
            data = response.json
            assert data["status"] == "ok"
            assert data["response"]["artifactSize"] == 99999

    def test_resolve_artifact_size_s3_url_without_https(self, flask_client):
        """Test resolving artifact size for S3 URL without https protocol"""
        s3_url = "test-bucket.s3.amazonaws.com/test-folder/file.txt"
        
        with patch('argus.backend.service.testrun.boto3.client') as mock_boto_client:
            mock_s3 = Mock()
            mock_s3.get_object.return_value = {"ContentLength": 11111}
            mock_boto_client.return_value = mock_s3
            
            response = self._make_request(flask_client, s3_url)
            
            assert response.status_code == 200
            data = response.json
            assert data["status"] == "ok"
            assert data["response"]["artifactSize"] == 11111
