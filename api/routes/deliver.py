"""POST /incidents/{id}/deliver: the verdict as a Slack card and a Linear issue, through OpenConnector (API.md).

Each target succeeds or fails on its own; the response is 200 with a per-target result and the UI retries the failed
one. The `Idempotency-Key` is scoped to env, incident run and target and includes a hash of the payload, so a retry
of the same message never posts twice and a different message never reuses a key.
"""

import json
import time

from fastapi import APIRouter, Request

from api.config import get_settings
from api.deliver.openconnector import UpstreamError, run_action
from api.models import DeliverIn, DeliverOut, DeliverResult, IncidentOut
from api.routes.deps import ApiError, Env, incident_or_404
from api.routes.incidents import get_incident

router = APIRouter()

DELIVERABLE = {"diagnosed", "delivered", "no_root_cause"}


def title(inc: IncidentOut) -> str:
    if inc.verdict:
        return f"[Epicenter] {inc.symptom}: root cause {inc.verdict.root_cause.target}"
    return f"[Epicenter] {inc.symptom}: nothing in the graph explains the alert"


def body_markdown(inc: IncidentOut) -> str:
    # no status here: it flips to `delivered` once one target succeeds, and the message must stay the same on a retry
    lines = [f"**Incident** `{inc.id}` · env `{inc.env}` · diagnosis run {inc.run}"]
    if inc.verdict:
        v = inc.verdict
        lines.append(f"**Root cause:** `{v.root_cause.target}` (confidence {v.confidence:.0%})")
        if v.second_root_cause:
            lines.append(f"**Second cause:** `{v.second_root_cause.target}`")
        lines.append(f"**Path:** {' → '.join(reversed(v.path))}")
    elif inc.no_root_cause:
        lines.append(inc.no_root_cause.summary)
    if inc.explanation and inc.explanation.claims:
        badge = "" if inc.explanation.source == "llm" else " (AI explanation unavailable: built from the evidence)"
        lines.append(f"\n**Why**{badge}")
        lines += [f"- {c.text} [{', '.join(c.cites)}]" for c in inc.explanation.claims]
    if inc.actions:
        lines.append("\n**Proposed actions**")
        lines += [f"{a.rank}. {a.name}" for a in inc.actions]
    return "\n".join(lines)


def slack(inc: IncidentOut, channel: str, key: str) -> str | None:
    text = body_markdown(inc).replace("**", "*")  # Slack mrkdwn bold is single *
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": title(inc)[:150]}},
        {"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}},
    ]
    posted = run_action("slack.post_message", {"channelId": channel, "text": title(inc), "blocks": blocks}, key)
    try:
        link = run_action(
            "slack.get_message_permalink", {"channelId": channel, "messageTs": posted["ts"]}, key + ":link"
        )
        return link.get("permalink")
    except (UpstreamError, KeyError):
        return None  # posted; only the link is missing


def linear(inc: IncidentOut, team_id: str, key: str) -> str | None:
    issue = run_action(
        "linear.create_linear_issue",
        {"title": title(inc)[:250], "team_id": team_id, "description": body_markdown(inc)},
        key,
    )
    return issue.get("ticket_url")


@router.post("/incidents/{incident_id}/deliver", response_model=DeliverOut)
def deliver(incident_id: str, body: DeliverIn, env: Env, request: Request) -> DeliverOut:
    raw = incident_or_404(env, incident_id)
    if raw["status"] not in DELIVERABLE:
        raise ApiError(409, "INCIDENT_STATE", f"Incident {incident_id!r} is {raw['status']}; nothing to deliver yet")
    inc = get_incident(incident_id, env, request)
    s = get_settings()
    results = []
    for target in dict.fromkeys(body.targets):  # dedupe, keep order
        key = f"{env.key}:{incident_id}:r{inc.run}:{target}"  # scope; run_action adds the payload hash
        try:
            if target == "slack":
                channel = body.slack_channel or s.slack_channel
                if not channel:
                    raise UpstreamError("no Slack channel: send slack_channel or set SLACK_CHANNEL")
                url = slack(inc, channel, key)
            else:
                if not s.linear_team_id:
                    raise UpstreamError("LINEAR_TEAM_ID not set")
                url = linear(inc, s.linear_team_id, key)
            results.append(DeliverResult(target=target, ok=True, url=url))
        except UpstreamError as e:
            results.append(DeliverResult(target=target, ok=False, error="UPSTREAM_ERROR", message=str(e)[:300]))
    record = json.loads(raw["delivery"]) if raw["delivery"] else {}
    for res in results:
        record[res.target] = res.model_dump(exclude={"target"}) | {"ts": int(time.time()), "run": inc.run}
    delivered = raw["status"] == "diagnosed" and any(r.ok for r in results)  # LLD §8: diagnosed → delivered
    env.rw("incident_delivery", inc=incident_id, delivery=json.dumps(record, sort_keys=True), delivered=delivered)
    return DeliverOut(results=results)
