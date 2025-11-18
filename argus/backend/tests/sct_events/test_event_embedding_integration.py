"""
Integration tests for Event Similarity Processor V2

These tests verify the complete flow from event creation to embedding storage.
"""

from dataclasses import asdict
from datetime import datetime, UTC
from uuid import uuid4

from argus.backend.models.argus_ai import SCTErrorEventEmbedding, SCTCriticalEventEmbedding
from argus.backend.models.web import ArgusTest
from argus.backend.plugins.sct.testrun import SCTEvent, SCTEventSeverity, SCTUnprocessedEvent
from argus.backend.service.client_service import ClientService
from argus.backend.plugins.sct.service import SCTService
from argus.backend.service.testrun import TestRunService
from argus.backend.tests.conftest import get_fake_test_run
from argus.common.sct_types import RawEventPayload
from argusAI.event_similarity_processor_v2 import EventSimilarityProcessorV2


def test_event_to_embedding_flow_should_create_embedding_for_error_event(
    client_service: ClientService,
    sct_service: SCTService,
    testrun_service: TestRunService,
    fake_test: ArgusTest,
    embedding_processor: EventSimilarityProcessorV2,
):
    """Test that ERROR event creates unprocessed entry and processor generates embedding in ERROR table"""
    # Step 1: Create a test run
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))

    # Step 2: Submit an ERROR event
    event_data: RawEventPayload = {
        "duration": 30.0,
        "event_type": "DatabaseEvent",
        "known_issue": None,
        "message": "Test error message - this is a sample error",
        "nemesis_name": None,
        "nemesis_status": None,
        "node": "test-node-1",
        "received_timestamp": None,
        "run_id": run_req.run_id,
        "severity": SCTEventSeverity.ERROR.value,
        "target_node": None,
        "ts": datetime.now(tz=UTC).timestamp()
    }

    sct_service.submit_event(str(run_req.run_id), event_data)

    # Step 3: Verify event was created in SCTEvent table
    events = SCTEvent.filter(run_id=run_req.run_id, severity=SCTEventSeverity.ERROR.value).all()
    assert len(list(events)) == 1, "Event should be created in SCTEvent table"

    # Step 4: Verify unprocessed event was created
    unprocessed_events = SCTUnprocessedEvent.filter(
        run_id=run_req.run_id,
        severity=SCTEventSeverity.ERROR.value
    ).all()
    unprocessed_list = list(unprocessed_events)
    assert len(unprocessed_list) == 1, "Unprocessed event should be created"

    # Step 5: Run processor to generate embedding
    processor = embedding_processor

    # Process batches until THIS test's unprocessed event is removed
    # (processor may process events from other tests first)
    max_attempts = 10
    for attempt in range(max_attempts):
        processor._process_batch()

        # Check if our specific event has been processed
        remaining = list(SCTUnprocessedEvent.filter(
            run_id=run_req.run_id,
            severity=SCTEventSeverity.ERROR.value
        ).all())

        if len(remaining) == 0:
            break
    else:
        raise AssertionError(f"Failed to process this test's event after {max_attempts} attempts")

    # Step 6: Verify embedding was stored in ERROR table for THIS test run
    embeddings = SCTErrorEventEmbedding.filter(run_id=run_req.run_id).all()
    embedding_list = list(embeddings)
    assert len(embedding_list) == 1, "Embedding should be stored in ERROR table"
    assert len(embedding_list[0].embedding) > 0, "Embedding should have values"

    # Step 7: Verify no embedding in CRITICAL table for THIS test run
    critical_embeddings = SCTCriticalEventEmbedding.filter(run_id=run_req.run_id).all()
    assert len(list(critical_embeddings)) == 0, "No embedding should be in CRITICAL table"

    # Step 8: Verify unprocessed event was removed for THIS test run
    unprocessed_events_after = SCTUnprocessedEvent.filter(
        run_id=run_req.run_id,
        severity=SCTEventSeverity.ERROR.value
    ).all()
    assert len(list(unprocessed_events_after)) == 0, "Unprocessed event should be removed"


def test_event_to_embedding_flow_should_create_embedding_for_critical_event(
    client_service: ClientService,
    sct_service: SCTService,
    testrun_service: TestRunService,
    fake_test: ArgusTest,
    embedding_processor: EventSimilarityProcessorV2,
):
    """Test that CRITICAL event creates unprocessed entry and processor generates embedding in CRITICAL table"""
    # Step 1: Create a test run
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))

    # Step 2: Submit a CRITICAL event
    event_data: RawEventPayload = {
        "message": "Critical error - node failure detected",
        "run_id": run_req.run_id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "ts": datetime.now(tz=UTC).timestamp(),
        "event_type": "NodeFailure"
    }

    sct_service.submit_event(str(run_req.run_id), event_data)

    # Step 3: Verify unprocessed event was created
    unprocessed_events = SCTUnprocessedEvent.filter(
        run_id=run_req.run_id,
        severity=SCTEventSeverity.CRITICAL.value
    ).all()
    assert len(list(unprocessed_events)) == 1, "Unprocessed event should be created"

    # Step 4: Run processor to generate embedding
    processor = embedding_processor

    # Process batches until THIS test's unprocessed event is removed
    max_attempts = 10
    for attempt in range(max_attempts):
        processor._process_batch()

        # Check if our specific event has been processed
        remaining = list(SCTUnprocessedEvent.filter(
            run_id=run_req.run_id,
            severity=SCTEventSeverity.CRITICAL.value
        ).all())

        if len(remaining) == 0:
            break
    else:
        raise AssertionError(f"Failed to process this test's event after {max_attempts} attempts")

    # Step 5: Verify embedding was stored in CRITICAL table for THIS test run
    embeddings = SCTCriticalEventEmbedding.filter(run_id=run_req.run_id).all()
    embedding_list = list(embeddings)
    assert len(embedding_list) == 1, "Embedding should be stored in CRITICAL table"
    assert len(embedding_list[0].embedding) > 0, "Embedding should have values"

    # Step 6: Verify no embedding in ERROR table for THIS test run
    error_embeddings = SCTErrorEventEmbedding.filter(run_id=run_req.run_id).all()
    assert len(list(error_embeddings)) == 0, "No embedding should be in ERROR table"


def test_event_to_embedding_flow_should_not_create_unprocessed_for_warning_event(
    client_service: ClientService,
    sct_service: SCTService,
    testrun_service: TestRunService,
    fake_test: ArgusTest,
    embedding_processor: EventSimilarityProcessorV2,
):
    """Test that WARNING events do NOT create unprocessed entries"""
    # Step 1: Create a test run
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))

    # Step 2: Submit a WARNING event
    event_data: RawEventPayload = {
        "message": "Warning - high latency detected",
        "run_id": run_req.run_id,
        "severity": SCTEventSeverity.WARNING.value,
        "ts": datetime.now(tz=UTC).timestamp(),
        "event_type": "PerformanceWarning"
    }

    sct_service.submit_event(str(run_req.run_id), event_data)

    # Step 3: Verify event was created in SCTEvent table
    events = SCTEvent.filter(run_id=run_req.run_id, severity=SCTEventSeverity.WARNING.value).all()
    assert len(list(events)) == 1, "Event should be created in SCTEvent table"

    # Step 4: Verify NO unprocessed event was created
    unprocessed_events = SCTUnprocessedEvent.filter(
        run_id=run_req.run_id,
        severity=SCTEventSeverity.WARNING.value
    ).all()
    assert len(list(unprocessed_events)) == 0, "Unprocessed event should NOT be created for WARNING"


def test_event_to_embedding_flow_should_process_multiple_events_into_separate_tables(
    client_service: ClientService,
    sct_service: SCTService,
    testrun_service: TestRunService,
    fake_test: ArgusTest,
    embedding_processor: EventSimilarityProcessorV2,
):
    """Test that processor handles multiple events and stores them in correct severity-specific tables"""
    # Step 1: Create a test run
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))

    # Step 2: Submit multiple ERROR events
    for i in range(3):
        event_data: RawEventPayload = {
            "message": f"Error event {i}",
            "run_id": run_req.run_id,
            "severity": SCTEventSeverity.ERROR.value,
            "ts": datetime.now(tz=UTC).timestamp() + i,
            "event_type": "DatabaseEvent"
        }
        sct_service.submit_event(str(run_req.run_id), event_data)

    # Step 3: Submit multiple CRITICAL events
    for i in range(2):
        event_data: RawEventPayload = {
            "message": f"Critical event {i}",
            "run_id": run_req.run_id,
            "severity": SCTEventSeverity.CRITICAL.value,
            "ts": datetime.now(tz=UTC).timestamp() + i + 100,
            "event_type": "CriticalFailure"
        }
        sct_service.submit_event(str(run_req.run_id), event_data)

    # Step 4: Verify 5 unprocessed events were created
    all_unprocessed = list(SCTUnprocessedEvent.filter(run_id=run_req.run_id).all())
    assert len(all_unprocessed) == 5, "Should have 5 unprocessed events"

    # Step 5: Run processor to process all events
    processor = embedding_processor

    # Process batches until THIS test's unprocessed events are removed
    max_attempts = 20
    for attempt in range(max_attempts):
        processor._process_batch(batch_size=100)

        # Check if our specific events have been processed
        remaining = list(SCTUnprocessedEvent.filter(run_id=run_req.run_id).all())

        if len(remaining) == 0:
            break
    else:
        raise AssertionError(f"Failed to process all of this test's events after {max_attempts} attempts")

    # Step 6: Verify embeddings were stored in correct tables for THIS test run
    error_embeddings = list(SCTErrorEventEmbedding.filter(run_id=run_req.run_id).all())
    critical_embeddings = list(SCTCriticalEventEmbedding.filter(run_id=run_req.run_id).all())

    assert len(error_embeddings) == 3, "Should have 3 ERROR embeddings in ERROR table"
    assert len(critical_embeddings) == 2, "Should have 2 CRITICAL embeddings in CRITICAL table"

    # Step 7: Verify all unprocessed events were removed for THIS test run
    remaining_unprocessed = list(SCTUnprocessedEvent.filter(run_id=run_req.run_id).all())
    assert len(remaining_unprocessed) == 0, "All unprocessed events should be removed"


def test_event_to_embedding_flow_should_handle_processing_errors_gracefully(
    client_service: ClientService,
    sct_service: SCTService,
    testrun_service: TestRunService,
    fake_test: ArgusTest,
    embedding_processor: EventSimilarityProcessorV2,
):
    """Test that processor handles errors gracefully and removes problematic events"""
    # Step 1: Create a test run
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))

    # Step 2: Submit an event
    event_data: RawEventPayload = {
        "message": "Test error",
        "run_id": run_req.run_id,
        "severity": SCTEventSeverity.ERROR.value,
        "ts": datetime.now(tz=UTC).timestamp(),
        "event_type": "TestEvent"
    }
    sct_service.submit_event(str(run_req.run_id), event_data)

    # Step 3: Manually create an unprocessed event that points to non-existent event
    fake_run_id = uuid4()
    fake_unprocessed = SCTUnprocessedEvent()
    fake_unprocessed.run_id = fake_run_id
    fake_unprocessed.severity = SCTEventSeverity.ERROR.value
    fake_unprocessed.ts = datetime.now(tz=UTC)
    fake_unprocessed.save()

    # Step 4: Run processor
    processor = embedding_processor
    processor._process_batch(batch_size=100)

    # Processor should handle 2 events: 1 success, 1 failure
    assert processor.processed_count >= 1, "Should process at least one event successfully"
    assert processor.error_count >= 1, "Should have at least one error"

    # Step 5: Verify the fake unprocessed event was still removed (to avoid infinite retries)
    fake_unprocessed_after = list(SCTUnprocessedEvent.filter(
        run_id=fake_run_id,
        severity=SCTEventSeverity.ERROR.value
    ).all())
    assert len(fake_unprocessed_after) == 0, "Problematic unprocessed event should be removed"
