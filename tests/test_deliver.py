"""POST /deliver through OpenConnector (offline fake): per-target results, idempotency, state rules."""

import httpx

from api.config import get_settings
from api.deliver import openconnector
from tests.conftest import API_ENV, diagnosed
from tests.fakes import FakeConnector

Q = {"env": API_ENV}


def _use(monkeypatch, fake: FakeConnector, slack: str | None = "C1", linear: str | None = "team-1"):
    monkeypatch.setattr(openconnector, "_transport", httpx.MockTransport(fake))
    s = get_settings()
    monkeypatch.setattr(s, "openconnector_url", "http://oc.test")
    monkeypatch.setattr(s, "slack_channel", slack)
    monkeypatch.setattr(s, "linear_team_id", linear)
    return fake


def test_deliver_posts_a_slack_card_and_a_linear_issue(client, monkeypatch):
    fake = _use(monkeypatch, FakeConnector())
    diagnosed(client)
    r = client.post("/api/v1/incidents/inc-1/deliver", params=Q, json={"targets": ["slack", "linear"]})
    assert r.status_code == 200
    assert r.json()["results"] == [
        {
            "target": "slack",
            "ok": True,
            "url": "https://slack.example/archives/C1/p17290001",
            "error": None,
            "message": None,
        },
        {"target": "linear", "ok": True, "url": "https://linear.example/OPS-7", "error": None, "message": None},
    ]
    post, link, issue = fake.requests
    assert post[0] == "slack.post_message" and post[1]["channelId"] == "C1" and "payment/Charge" in post[1]["text"]
    assert (
        post[2]["idempotency-key"].startswith(f"env:{API_ENV}:inc-1:r2:slack:")
        and link[0] == "slack.get_message_permalink"
    )
    assert link[2]["idempotency-key"] != post[2]["idempotency-key"]  # another action, another key
    assert issue[0] == "linear.create_linear_issue" and issue[1]["team_id"] == "team-1"
    assert "Proposed actions" in issue[1]["description"] and "**Why**" in issue[1]["description"]
    inc = client.get("/api/v1/incidents/inc-1", params=Q).json()
    assert inc["status"] == "delivered" and inc["delivery"]["linear"]["ok"] is True


def test_one_target_failing_is_reported_and_retryable(client, monkeypatch):
    fake = _use(monkeypatch, FakeConnector(fail={"linear.create_linear_issue"}))
    diagnosed(client)
    r = client.post("/api/v1/incidents/inc-1/deliver", params=Q, json={"targets": ["slack", "linear"]}).json()
    slack, linear = r["results"]
    assert slack["ok"] is True and (linear["ok"], linear["error"]) == (False, "UPSTREAM_ERROR")
    assert "connection_not_allowed" in linear["message"]
    inc = client.get("/api/v1/incidents/inc-1", params=Q).json()
    assert inc["status"] == "delivered" and inc["delivery"]["linear"]["ok"] is False
    fake.fail.clear()  # the user retries the failed target only; same idempotency key per target
    again = client.post("/api/v1/incidents/inc-1/deliver", params=Q, json={"targets": ["linear"]}).json()
    assert again["results"][0]["ok"] is True
    keys = [h["idempotency-key"] for a, _, h in fake.requests if a == "linear.create_linear_issue"]
    assert (
        len(keys) == 2 and keys[0] == keys[1] and keys[0].startswith(f"env:{API_ENV}:inc-1:r2:linear:")
    )  # same message


def test_idempotency_key_changes_with_the_message():
    from api.deliver.openconnector import idempotency_key

    a = idempotency_key("env:x:inc-1:r1:slack", "slack.post_message", {"channelId": "C1", "text": "one"})
    assert a == idempotency_key("env:x:inc-1:r1:slack", "slack.post_message", {"text": "one", "channelId": "C1"})
    assert a != idempotency_key("env:x:inc-1:r1:slack", "slack.post_message", {"channelId": "C1", "text": "two"})
    assert a != idempotency_key("env:y:inc-1:r1:slack", "slack.post_message", {"channelId": "C1", "text": "one"})


def test_missing_config_and_wrong_state(client, monkeypatch):
    _use(monkeypatch, FakeConnector(), slack=None, linear=None)
    r = client.post("/api/v1/incidents/inc-1/deliver", params=Q, json={"targets": ["slack"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INCIDENT_STATE"  # still diagnosing, nothing yet
    diagnosed(client)
    res = client.post("/api/v1/incidents/inc-1/deliver", params=Q, json={"targets": ["slack", "linear"]}).json()
    assert [x["ok"] for x in res["results"]] == [False, False]
    assert "SLACK_CHANNEL" in res["results"][0]["message"] and "LINEAR_TEAM_ID" in res["results"][1]["message"]
    assert client.get("/api/v1/incidents/inc-1", params=Q).json()["status"] == "diagnosed"  # nothing went out
    assert client.post("/api/v1/incidents/inc-1/deliver", params=Q, json={"targets": []}).status_code == 400
