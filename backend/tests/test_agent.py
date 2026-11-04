import json

import httpx
import pytest

from app import config
from app.agent import mission as M
from app.agent.governor import SafetyGovernor, rule_check
from app.agent.muse import MuseClient, MuseError, extract_json
from app.db import database
from app.sandbox import platform as sb
from app.sandbox import store


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    conn = database.connect()
    M.init(conn)
    store.reset(conn)
    yield conn
    conn.close()


@pytest.mark.parametrize("text, rule", [
    ("honestly he's kind of a legend to me", "R1"),
    ("yeah i'm in for friday", "R2"),
    ("who's next? can't wait", "R2"),
    ("im 16 and bored lol", "R4"),
    ("text me on +60 12 345 6789", "R5"),
    ("what weapon did he use", "R7"),
    ("i'm a journalist actually", "R9"),
])
def test_governor_blocks_rule_violations(text, rule):
    v = rule_check(text)
    assert not v.allowed and rule in v.violations


@pytest.mark.parametrize("text", [
    "i'd like to see the chat. still figuring stuff out, mostly just reading",
    "i've read everything about him. i want to understand why, not judge",
    "no. just a guy who works nights",
])
def test_governor_allows_low_key_observation(text):
    assert rule_check(text).allowed


def test_governor_blocks_support_spaces(sandbox):
    g = sb.group_view(sandbox, "g_support", "u_persona")
    assert not SafetyGovernor.check_join(g).allowed


def test_platform_privacy(sandbox):
    assert "g_ann" not in [g["id"] for g in sb.search_groups(sandbox, "", "u_persona")]
    with pytest.raises(sb.PlatformError):
        sb.feed(sandbox, "g_rip", "u_persona")
    with pytest.raises(sb.PlatformError):
        sb.group_view(sandbox, "g_ann", "u_persona")
    with pytest.raises(sb.PlatformError):
        sb.accept_invite(sandbox, "fx7-r1", "u_persona")  # not issued to this user


def test_gatekeeper_screens_answers(sandbox):
    declined = sb.request_join(sandbox, "g_rip", "u_viewer", ["for my study", "i am researching him for a paper", "yes"])
    assert declined["status"] == "declined"
    ok = sb.request_join(sandbox, "g_rip", "u_persona", ["been following the case", "i want to understand why it happened", "no"])
    assert ok["status"] == "approved"


def test_offline_mission_end_to_end(sandbox):
    mid = M.start_mission("test brief for mission", auto_approve="all", pace=0, force_offline=True,
                          reset_sandbox=False, background=False)
    m = M.get_mission(sandbox, mid)
    assert m["status"] == "completed", m["events"][-1]
    s = m["summary"]
    assert s["assessments"]["friday."] == "imminent_threat"
    assert s["assessments"]["Ridgeview Case Files"] in ("benign", "monitor")
    assert s["assessments"]["True Crime Talk MY"] in ("benign", "monitor")

    verdicts = [e for e in m["events"] if e["kind"] == "verdict"]
    assert any("R1" in e["detail"]["violations"] for e in verdicts)
    assert any("R2" in e["detail"]["violations"] for e in verdicts)

    reports = sb.reports(sandbox)
    assert {r["severity"] for r in reports} == {"urgent", "normal"}
    urgent = next(r for r in reports if r["severity"] == "urgent")
    assert "sp_503" in [e["post_id"] for e in urgent["body"]["evidence"]]

    # Boundaries held: never joined the support space, never posted, every DM passes the rules.
    assert not sandbox.execute("SELECT 1 FROM sb_join_requests WHERE group_id = 'g_support'").fetchone()
    assert not sandbox.execute("SELECT 1 FROM sb_posts WHERE author = 'u_persona'").fetchone()
    for (text,) in sandbox.execute("SELECT text FROM sb_messages WHERE sender = 'u_persona'"):
        assert rule_check(text).allowed

    # Evidence handed to the human review queue.
    assert sandbox.execute("SELECT COUNT(*) FROM posts WHERE id LIKE ?", (f"{mid}_%",)).fetchone()[0] >= 10


def test_edited_message_must_pass_governor(sandbox):
    sandbox.execute(
        "INSERT INTO mission_approvals (mission_id, created_at, kind, title, payload, status) VALUES ('m_x', 'now', 'message', 't', ?, 'pending')",
        (json.dumps({"to": "u_nightlight", "text": "ok"}),))
    sandbox.commit()
    with pytest.raises(ValueError):
        M.decide_approval(sandbox, 1, True, "r1", None, edited_text="count me in for friday")
    assert M.decide_approval(sandbox, 1, True, "r1", None, edited_text="just reading for now")


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"b": [1, 2]} done') == {"b": [1, 2]}
    with pytest.raises(MuseError):
        extract_json("no json here")


def test_muse_client_offline_raises():
    with pytest.raises(MuseError):
        MuseClient(api_key="").chat("x", "s", "u")


def test_muse_client_drops_unsupported_params_and_tracks_cost(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(dict(json))
        if "response_format" in json:
            return httpx.Response(400, text="unknown parameter response_format", request=httpx.Request("POST", url))
        return httpx.Response(200, json={
            "model": "muse-spark-1.3",
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
        }, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    client = MuseClient(api_key="test-key")
    r = client.chat("governor", "sys", "hello")
    assert r.data == {"ok": True}
    assert "response_format" not in calls[-1]
    assert r.cost_usd == pytest.approx((1000 * 1.25 + 200 * 4.25) / 1e6)
    assert client.ledger.calls == 1 and client.ledger.by_purpose == {"governor": 1}
    client.chat("governor", "sys", "again")
    assert "response_format" not in calls[-1] and len(calls) == 3  # not retried again
