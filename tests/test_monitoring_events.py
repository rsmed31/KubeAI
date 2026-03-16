"""Unit tests for EventStreamHub: publication order, filtering, retention, and cursor semantics."""

from __future__ import annotations

import pytest

from KubeAI.monitoring import EventStreamHub


class TestEventStreamHub:
    def test_publish_assigns_incrementing_ids(self) -> None:
        hub = EventStreamHub()

        evt1 = hub.publish("agent.registered", {"agent_id": "a1"})
        evt2 = hub.publish("task.recorded", {"task_id": "t1"})

        assert evt1.event_id == "evt-1"
        assert evt2.event_id == "evt-2"
        assert hub.latest_event_id() == "evt-2"

    def test_publish_rejects_empty_event_type(self) -> None:
        hub = EventStreamHub()

        with pytest.raises(ValueError, match="event_type"):
            hub.publish("  ")

    def test_list_events_with_type_filter_and_limit(self) -> None:
        hub = EventStreamHub()
        hub.publish("agent.registered", {"agent_id": "a1"})
        hub.publish("task.recorded", {"task_id": "t1"})
        hub.publish("task.recorded", {"task_id": "t2"})

        filtered = hub.list_events(event_type="task.recorded", limit=1)

        assert len(filtered) == 1
        assert filtered[0].payload["task_id"] == "t2"

    def test_list_events_after_cursor(self) -> None:
        hub = EventStreamHub()
        hub.publish("x", {"n": 1})
        hub.publish("x", {"n": 2})
        hub.publish("x", {"n": 3})

        events = hub.list_events(after_event_id="evt-1")

        assert [event.payload["n"] for event in events] == [2, 3]

    def test_invalid_cursor_raises(self) -> None:
        hub = EventStreamHub()
        hub.publish("x")

        with pytest.raises(ValueError, match="Invalid event id"):
            hub.list_events(after_event_id="bad-id")

    def test_retention_keeps_only_latest(self) -> None:
        hub = EventStreamHub(max_events=2)
        hub.publish("x", {"n": 1})
        hub.publish("x", {"n": 2})
        hub.publish("x", {"n": 3})

        events = hub.list_events(limit=10)

        assert [event.payload["n"] for event in events] == [2, 3]
        assert hub.latest_event_id() == "evt-3"

    def test_repr_includes_bounds(self) -> None:
        hub = EventStreamHub(max_events=3)
        hub.publish("x")

        text = repr(hub)
        assert "max_events=3" in text
        assert "stored_events=1" in text
        assert "latest='evt-1'" in text
