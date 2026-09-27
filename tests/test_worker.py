import threading
import time

import pytest

from symple.engine.worker import EngineClient


@pytest.fixture(scope="module")
def client():
    c = EngineClient()
    c.start()
    yield c
    c.shutdown()


def test_run_and_state_persists(client):
    r = client.run("a := 21:")
    assert r.outputs == [] and "a" in r.names
    r = client.run("2*a;")
    assert [o.text for o in r.outputs] == ["42"]


def test_interrupt_restarts_session(client):
    client.run("keep := 1:")
    box = {}
    t = threading.Thread(target=lambda: box.setdefault("r", client.run("while true do od;")))
    t.start()
    time.sleep(1.0)
    client.interrupt()
    t.join(10)
    assert not t.is_alive()
    assert box["r"].interrupted
    assert "interrupted" in box["r"].outputs[0].text
    r = client.run("keep;")
    assert [o.text for o in r.outputs] == ["keep"]  # fresh session
