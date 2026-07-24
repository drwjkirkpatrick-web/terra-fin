"""Tests for event bus."""

import sys
import os
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.event_bus import EventBus


class TestEventBus:
    def test_subscribe_publish(self):
        bus = EventBus()
        received = []
        sub_id = bus.subscribe("TEST_EVENT", lambda data: received.append(data))
        bus.publish("TEST_EVENT", {"msg": "hello"})
        assert len(received) == 1
        assert received[0]["msg"] == "hello"

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        sub_id = bus.subscribe("TEST", lambda d: received.append(d))
        bus.publish("TEST", {"x": 1})
        assert len(received) == 1
        assert bus.unsubscribe(sub_id) is True
        bus.publish("TEST", {"x": 2})
        assert len(received) == 1  # no new messages

    def test_multiple_subscribers(self):
        bus = EventBus()
        r1, r2 = [], []
        bus.subscribe("E", lambda d: r1.append(d))
        bus.subscribe("E", lambda d: r2.append(d))
        count = bus.publish("E", {"v": 1})
        assert count == 2
        assert len(r1) == 1
        assert len(r2) == 1

    def test_unknown_event_type(self):
        bus = EventBus()
        count = bus.publish("UNKNOWN", {"x": 1})
        assert count == 0

    def test_callback_exception_isolated(self):
        bus = EventBus()
        good_results = []

        def bad_callback(data):
            raise RuntimeError("boom")

        def good_callback(data):
            good_results.append(data)

        bus.subscribe("E", bad_callback)
        bus.subscribe("E", good_callback)
        count = bus.publish("E", {"v": 1})
        # bad callback failed, but good callback still got it
        assert count == 1
        assert len(good_results) == 1

    def test_subscriber_count(self):
        bus = EventBus()
        assert bus.subscriber_count("E") == 0
        bus.subscribe("E", lambda d: None)
        assert bus.subscriber_count("E") == 1
        bus.subscribe("E", lambda d: None)
        assert bus.subscriber_count("E") == 2

    def test_thread_safety(self):
        bus = EventBus()
        received = []

        def subscriber(d):
            received.append(d)

        bus.subscribe("E", subscriber)

        def publisher():
            for i in range(50):
                bus.publish("E", {"i": i})

        threads = [threading.Thread(target=publisher) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(received) == 200

    def test_clear(self):
        bus = EventBus()
        bus.subscribe("E", lambda d: None)
        bus.subscribe("E2", lambda d: None)
        bus.clear()
        assert bus.subscriber_count("E") == 0
        assert bus.subscriber_count("E2") == 0