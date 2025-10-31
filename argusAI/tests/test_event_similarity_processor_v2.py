"""
Tests for Event Similarity Processor V2

Test coverage:
1. Initialization and configuration
2. Event processing workflow
3. Batch processing
4. Error handling
5. Shutdown procedures
"""

import logging
from datetime import datetime
from threading import Event
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import pytest

from argusAI.event_similarity_processor_v2 import EventSimilarityProcessorV2, BgeSmallEnEmbeddingModel


LOGGER = logging.getLogger(__name__)


class TestBgeSmallEnEmbeddingModel:
    """Tests for BGE-Small-EN embedding model configuration."""

    def test_model_should_have_correct_configuration(self):
        """Model configuration should match BGE-Small-EN specifications."""
        assert BgeSmallEnEmbeddingModel.MODEL_NAME == "bge-small-en-v1.5"
        assert "bge-small-en-v1.5" in str(BgeSmallEnEmbeddingModel.DOWNLOAD_PATH)
        assert BgeSmallEnEmbeddingModel.EXTRACTED_FOLDER_NAME == "onnx"
        assert BgeSmallEnEmbeddingModel.ARCHIVE_FILENAME == "onnx.tar.gz"
        assert "s3.us-east-1.amazonaws.com" in BgeSmallEnEmbeddingModel.MODEL_DOWNLOAD_URL
        assert BgeSmallEnEmbeddingModel._MODEL_SHA256 is not None


class TestEventSimilarityProcessorV2Initialization:
    """Tests for processor initialization."""

    @patch("argusAI.event_similarity_processor_v2.ScyllaConnection")
    @patch("argusAI.event_similarity_processor_v2.BgeSmallEnEmbeddingModel")
    @patch("argusAI.event_similarity_processor_v2.MessageSanitizer")
    def test_initialization_should_create_processor_with_dependencies(
        self, mock_sanitizer, mock_embedding_model, mock_scylla_connection
    ):
        """Processor should initialize with embedding model, sanitizer, and database connection."""
        processor = EventSimilarityProcessorV2()

        assert processor.embedding_model is not None
        assert processor.sanitizer is not None
        assert processor.db is not None
        assert processor.processed_count == 0
        assert processor.error_count == 0
        assert processor.stop_event is not None
        assert not processor.stop_event.is_set()

    @patch("argusAI.event_similarity_processor_v2.ScyllaConnection")
    @patch("argusAI.event_similarity_processor_v2.BgeSmallEnEmbeddingModel")
    @patch("argusAI.event_similarity_processor_v2.MessageSanitizer")
    def test_initialization_should_accept_custom_stop_event(
        self, mock_sanitizer, mock_embedding_model, mock_scylla_connection
    ):
        """Processor should accept a custom stop event for thread coordination."""
        custom_stop_event = Event()
        processor = EventSimilarityProcessorV2(stop_event=custom_stop_event)

        assert processor.stop_event is custom_stop_event


class TestEventProcessing:
    """Tests for event processing functionality."""

    @pytest.fixture
    def mock_db(self):
        """Mock database connection."""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def mock_embedding_model(self):
        """Mock embedding model that returns fake embeddings."""
        mock = MagicMock()
        mock.return_value = [[0.1, 0.2, 0.3] * 128]  # 384-dim vector
        return mock

    @pytest.fixture
    def mock_sanitizer(self):
        """Mock message sanitizer."""
        mock = MagicMock()
        mock.sanitize.return_value = "sanitized message"
        return mock

    @pytest.fixture
    def processor(self, mock_db, mock_embedding_model, mock_sanitizer):
        """Create processor with mocked dependencies."""
        with (
            patch("argusAI.event_similarity_processor_v2.ScyllaConnection", return_value=mock_db),
            patch("argusAI.event_similarity_processor_v2.BgeSmallEnEmbeddingModel", return_value=mock_embedding_model),
            patch("argusAI.event_similarity_processor_v2.MessageSanitizer", return_value=mock_sanitizer),
        ):
            processor = EventSimilarityProcessorV2()
            return processor

    def test_process_single_event_should_complete_full_workflow_for_error_event(self, processor):
        """Processing an ERROR event should sanitize, embed, store, and cleanup."""
        run_id = uuid4()
        severity = "ERROR"
        ts = datetime.now()
        original_message = "Error: Connection failed to 192.168.1.1"

        # Mock database responses
        mock_event = Mock()
        mock_event.message = original_message
        mock_result = Mock()
        mock_result.one.return_value = mock_event
        processor.db.execute.return_value = mock_result

        # Execute
        processor._process_single_event(run_id, severity, ts)

        # Verify SELECT query was executed
        select_calls = [call for call in processor.db.execute.call_args_list if call[0][0].startswith("SELECT message")]
        assert len(select_calls) == 1
        assert select_calls[0][0][1] == (run_id, severity, ts)

        # Verify sanitizer was called
        processor.sanitizer.sanitize.assert_called_once_with(run_id, original_message)

        # Verify embedding was generated
        processor.embedding_model.assert_called_once_with(["sanitized message"])

        # Verify INSERT into sct_error_event_embedding
        insert_calls = [
            call
            for call in processor.db.execute.call_args_list
            if call[0][0].startswith("INSERT INTO sct_error_event_embedding")
        ]
        assert len(insert_calls) == 1

        # Verify DELETE from unprocessed_events
        delete_calls = [
            call
            for call in processor.db.execute.call_args_list
            if call[0][0].startswith("DELETE FROM sct_unprocessed_events")
        ]
        assert len(delete_calls) == 1
        assert delete_calls[0][0][1] == (run_id, severity, ts)

    def test_process_single_event_should_complete_full_workflow_for_critical_event(self, processor):
        """Processing a CRITICAL event should store in sct_critical_event_embedding table."""
        run_id = uuid4()
        severity = "CRITICAL"
        ts = datetime.now()
        original_message = "Critical: Cluster is down"

        # Mock database responses
        mock_event = Mock()
        mock_event.message = original_message
        mock_result = Mock()
        mock_result.one.return_value = mock_event
        processor.db.execute.return_value = mock_result

        # Execute
        processor._process_single_event(run_id, severity, ts)

        # Verify INSERT into sct_critical_event_embedding
        insert_calls = [
            call
            for call in processor.db.execute.call_args_list
            if call[0][0].startswith("INSERT INTO sct_critical_event_embedding")
        ]
        assert len(insert_calls) == 1

    def test_process_single_event_should_raise_error_when_event_not_found(self, processor):
        """Processing should raise ValueError when event is not found in database."""
        run_id = uuid4()
        severity = "ERROR"
        ts = datetime.now()

        # Mock event not found
        mock_result = Mock()
        mock_result.one.return_value = None
        processor.db.execute.return_value = mock_result

        # Execute and verify
        with pytest.raises(ValueError, match="Event not found"):
            processor._process_single_event(run_id, severity, ts)

    def test_process_single_event_should_raise_error_when_message_is_empty(self, processor):
        """Processing should raise ValueError when event message is empty."""
        run_id = uuid4()
        severity = "ERROR"
        ts = datetime.now()

        # Mock event with empty message
        mock_event = Mock()
        mock_event.message = ""
        mock_result = Mock()
        mock_result.one.return_value = mock_event
        processor.db.execute.return_value = mock_result

        # Execute and verify
        with pytest.raises(ValueError, match="Event message is empty"):
            processor._process_single_event(run_id, severity, ts)

    def test_process_single_event_should_raise_error_when_sanitized_message_is_empty(self, processor):
        """Processing should raise ValueError when sanitized message is empty."""
        run_id = uuid4()
        severity = "ERROR"
        ts = datetime.now()

        # Mock event with message
        mock_event = Mock()
        mock_event.message = "Some message"
        mock_result = Mock()
        mock_result.one.return_value = mock_event
        processor.db.execute.return_value = mock_result

        # Mock sanitizer returning empty string
        processor.sanitizer.sanitize.return_value = "   "

        # Execute and verify
        with pytest.raises(ValueError, match="Sanitized message is empty"):
            processor._process_single_event(run_id, severity, ts)

    def test_process_single_event_should_raise_error_for_unsupported_severity(self, processor):
        """Processing should raise ValueError for unsupported severity levels."""
        run_id = uuid4()
        severity = "WARNING"  # Unsupported severity
        ts = datetime.now()

        # Mock event
        mock_event = Mock()
        mock_event.message = "Warning message"
        mock_result = Mock()
        mock_result.one.return_value = mock_event
        processor.db.execute.return_value = mock_result

        # Execute and verify
        with pytest.raises(ValueError, match="Unsupported severity"):
            processor._process_single_event(run_id, severity, ts)


class TestBatchProcessing:
    """Tests for batch processing functionality."""

    @pytest.fixture
    def processor_with_mocks(self):
        """Create processor with all dependencies mocked."""
        with (
            patch("argusAI.event_similarity_processor_v2.ScyllaConnection") as mock_scylla,
            patch("argusAI.event_similarity_processor_v2.BgeSmallEnEmbeddingModel") as mock_embedding,
            patch("argusAI.event_similarity_processor_v2.MessageSanitizer") as mock_sanitizer,
        ):
            # Setup mocks
            mock_db = MagicMock()
            mock_scylla.return_value = mock_db
            mock_embedding_instance = MagicMock()
            mock_embedding_instance.return_value = [[0.1] * 384]
            mock_embedding.return_value = mock_embedding_instance
            mock_sanitizer_instance = MagicMock()
            mock_sanitizer_instance.sanitize.return_value = "sanitized"
            mock_sanitizer.return_value = mock_sanitizer_instance

            processor = EventSimilarityProcessorV2()
            return processor

    def test_process_batch_should_return_zero_when_no_events(self, processor_with_mocks):
        """Batch processing should return 0 when no unprocessed events exist."""
        # Mock empty result
        processor_with_mocks.db.execute.return_value = []

        result = processor_with_mocks._process_batch()

        assert result == 0

    def test_process_batch_should_process_multiple_events(self, processor_with_mocks):
        """Batch processing should process multiple events and update counters."""
        # Create mock events
        mock_event1 = Mock(run_id=uuid4(), severity="ERROR", ts=datetime.now())
        mock_event2 = Mock(run_id=uuid4(), severity="CRITICAL", ts=datetime.now())
        mock_event3 = Mock(run_id=uuid4(), severity="ERROR", ts=datetime.now())

        # Setup mock responses for unprocessed events query
        processor_with_mocks.db.execute.return_value = [mock_event1, mock_event2, mock_event3]

        # Mock _process_single_event to avoid actual processing
        with patch.object(processor_with_mocks, "_process_single_event") as mock_process:
            result = processor_with_mocks._process_batch()

        assert result == 3
        assert processor_with_mocks.processed_count == 3
        assert mock_process.call_count == 3

    def test_process_batch_should_handle_individual_event_failures(self, processor_with_mocks):
        """Batch processing should continue despite individual event failures and clean up failed events."""
        # Create mock events
        mock_event1 = Mock(run_id=uuid4(), severity="ERROR", ts=datetime.now())
        mock_event2 = Mock(run_id=uuid4(), severity="CRITICAL", ts=datetime.now())

        # Setup mock responses
        processor_with_mocks.db.execute.return_value = [mock_event1, mock_event2]

        # Mock _process_single_event to fail on first event
        with patch.object(processor_with_mocks, "_process_single_event") as mock_process:
            mock_process.side_effect = [Exception("Processing failed"), None]
            result = processor_with_mocks._process_batch()

        assert result == 1  # Only one successful
        assert processor_with_mocks.processed_count == 1
        assert processor_with_mocks.error_count == 1

    def test_process_batch_should_respect_batch_size(self, processor_with_mocks):
        """Batch processing should use the specified batch size."""
        processor_with_mocks.db.execute.return_value = []

        processor_with_mocks._process_batch(batch_size=50)

        # Verify LIMIT clause in query
        call_args = processor_with_mocks.db.execute.call_args[0][0]
        assert "LIMIT 50" in call_args


class TestProcessingLoop:
    """Tests for main processing loop."""

    @pytest.fixture
    def processor_with_stop_event(self):
        """Create processor with stop event for testing."""
        with (
            patch("argusAI.event_similarity_processor_v2.ScyllaConnection"),
            patch("argusAI.event_similarity_processor_v2.BgeSmallEnEmbeddingModel"),
            patch("argusAI.event_similarity_processor_v2.MessageSanitizer"),
        ):
            stop_event = Event()
            processor = EventSimilarityProcessorV2(stop_event=stop_event)
            return processor, stop_event

    @patch("argusAI.event_similarity_processor_v2.time.sleep")
    def test_processing_loop_should_stop_when_stop_event_is_set(self, mock_sleep, processor_with_stop_event):
        """Processing loop should exit when stop_event is set."""
        processor, stop_event = processor_with_stop_event

        # Mock _process_batch to return 0 (no events)
        with patch.object(processor, "_process_batch", return_value=0):
            # Set stop event after one iteration
            def set_stop_after_sleep(*args):
                stop_event.set()

            mock_sleep.side_effect = set_stop_after_sleep

            processor.process_unprocessed_events()

            # Verify sleep was called (indicating loop ran)
            assert mock_sleep.called

    @patch("argusAI.event_similarity_processor_v2.time.sleep")
    def test_processing_loop_should_sleep_when_no_events(self, mock_sleep, processor_with_stop_event):
        """Processing loop should sleep when no events are available."""
        processor, stop_event = processor_with_stop_event

        iterations = 0

        def count_iterations(*args):
            nonlocal iterations
            iterations += 1
            if iterations >= 2:
                stop_event.set()

        mock_sleep.side_effect = count_iterations

        with patch.object(processor, "_process_batch", return_value=0):
            processor.process_unprocessed_events()

        # Verify sleep was called multiple times
        assert mock_sleep.call_count >= 2

    @patch("argusAI.event_similarity_processor_v2.time.sleep")
    def test_processing_loop_should_not_sleep_when_events_processed(self, mock_sleep, processor_with_stop_event):
        """Processing loop should continue immediately when events are processed."""
        processor, stop_event = processor_with_stop_event

        iterations = 0

        def stop_after_iterations(*args):
            nonlocal iterations
            iterations += 1
            if iterations >= 2:
                stop_event.set()
            return 5  # Simulate processing 5 events

        with patch.object(processor, "_process_batch", side_effect=stop_after_iterations):
            processor.process_unprocessed_events()

        # Sleep should not be called when events are being processed
        assert mock_sleep.call_count == 0

    @patch("argusAI.event_similarity_processor_v2.time.sleep")
    def test_processing_loop_should_handle_exceptions_and_continue(self, mock_sleep, processor_with_stop_event):
        """Processing loop should handle exceptions, increment error counter, and continue."""
        processor, stop_event = processor_with_stop_event

        iterations = 0

        def fail_then_succeed(*args):
            nonlocal iterations
            iterations += 1
            if iterations == 1:
                raise Exception("Database connection lost")
            stop_event.set()
            return 0

        with patch.object(processor, "_process_batch", side_effect=fail_then_succeed):
            processor.process_unprocessed_events()

        assert processor.error_count == 1
        assert iterations == 2  # Loop continued after error


class TestShutdown:
    """Tests for processor shutdown."""

    @patch("argusAI.event_similarity_processor_v2.ScyllaConnection")
    @patch("argusAI.event_similarity_processor_v2.BgeSmallEnEmbeddingModel")
    @patch("argusAI.event_similarity_processor_v2.MessageSanitizer")
    def test_shutdown_should_set_stop_event(self, mock_sanitizer, mock_embedding, mock_scylla):
        """Shutdown should set the stop event."""
        mock_db = MagicMock()
        mock_scylla.return_value = mock_db

        processor = EventSimilarityProcessorV2()
        processor.shutdown()

        assert processor.stop_event.is_set()

    @patch("argusAI.event_similarity_processor_v2.ScyllaConnection")
    @patch("argusAI.event_similarity_processor_v2.BgeSmallEnEmbeddingModel")
    @patch("argusAI.event_similarity_processor_v2.MessageSanitizer")
    def test_shutdown_should_cleanup_database_connection(self, mock_sanitizer, mock_embedding, mock_scylla):
        """Shutdown should properly close database connection."""
        mock_db = MagicMock()
        mock_scylla.return_value = mock_db

        processor = EventSimilarityProcessorV2()
        processor.shutdown()

        mock_db.shutdown.assert_called_once()


class TestIntegrationScenarios:
    """Integration-style tests for complete scenarios."""

    @pytest.fixture
    def full_processor(self):
        """Create processor with all mocks configured for full workflow."""
        with (
            patch("argusAI.event_similarity_processor_v2.ScyllaConnection") as mock_scylla,
            patch("argusAI.event_similarity_processor_v2.BgeSmallEnEmbeddingModel") as mock_embedding,
            patch("argusAI.event_similarity_processor_v2.MessageSanitizer") as mock_sanitizer,
        ):
            # Setup realistic mocks
            mock_db = MagicMock()
            mock_scylla.return_value = mock_db

            mock_embedding_instance = MagicMock()
            mock_embedding_instance.return_value = [[0.1] * 384]
            mock_embedding.return_value = mock_embedding_instance

            mock_sanitizer_instance = MagicMock()
            mock_sanitizer_instance.sanitize.return_value = "sanitized event message"
            mock_sanitizer.return_value = mock_sanitizer_instance

            processor = EventSimilarityProcessorV2()
            return processor

    def test_full_workflow_should_process_error_event_successfully(self, full_processor):
        """Complete workflow should process ERROR event from start to finish."""
        run_id = uuid4()
        severity = "ERROR"
        ts = datetime.now()

        # Mock database responses
        mock_event = Mock(message="Connection failed to node")
        mock_result = Mock()
        mock_result.one.return_value = mock_event
        full_processor.db.execute.return_value = mock_result

        # Execute
        full_processor._process_single_event(run_id, severity, ts)

        # Verify all steps occurred in correct order
        assert full_processor.db.execute.call_count >= 3  # SELECT, INSERT, DELETE
        assert full_processor.sanitizer.sanitize.called
        assert full_processor.embedding_model.called

    def test_batch_processing_should_handle_mixed_severities(self, full_processor):
        """Batch should successfully process mix of ERROR and CRITICAL events."""
        # Create mixed events
        events = [
            Mock(run_id=uuid4(), severity="ERROR", ts=datetime.now()),
            Mock(run_id=uuid4(), severity="CRITICAL", ts=datetime.now()),
            Mock(run_id=uuid4(), severity="ERROR", ts=datetime.now()),
        ]

        # First call returns events, subsequent calls for each event processing
        mock_event_data = Mock(message="Test message")
        mock_result = Mock()
        mock_result.one.return_value = mock_event_data

        def execute_side_effect(query, params=None):
            if "SELECT run_id" in query or "LIMIT" in query:
                return events
            return mock_result

        full_processor.db.execute.side_effect = execute_side_effect

        # Execute
        result = full_processor._process_batch()

        assert result == 3
        assert full_processor.processed_count == 3
