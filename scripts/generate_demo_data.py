"""Generate the SYNTHETIC Crime Sentinel demo dataset.

All posts, events ("Ridgeview", "Harlow Station"), accounts, and trends are
fictional. The timeline is deliberately constructed so that one topic
("anniversary countdown") emerges in the final weeks, for demonstration only.

Usage: python scripts/generate_demo_data.py [--seed 2]
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic"
SOURCE_NAME = "Crime Sentinel Synthetic Demo Dataset"
START = datetime(2026, 8, 31, tzinfo=timezone.utc)  # Monday
WEEKS = 8

TOPICS = [
    {"id": "topic_01", "label": "Ridgeview incident coverage", "description": "Discussion of the fictional Ridgeview attack."},
    {"id": "topic_02", "label": "Fan-edit & tribute culture", "description": "Edits, tributes, and fandom aesthetics around perpetrators."},
    {"id": "topic_03", "label": "Prevention & support", "description": "Support resources, counter-speech, and safeguarding advice."},
    {"id": "topic_04", "label": "Research & policy", "description": "Academic and policy discussion of online true-crime communities."},
    {"id": "topic_05", "label": "True-crime media", "description": "Podcasts, documentaries, and books."},
    {"id": "topic_06", "label": "Anniversary countdown trend", "description": "SIMULATED emerging trend counting down to an event anniversary."},
    {"id": "topic_07", "label": "Harlow Station case", "description": "Discussion of the fictional Harlow Station incident."},
]
for t in TOPICS:
    t["is_synthetic"] = True

EVENTS = [("the Ridgeview attack", "Ridgeview", "topic_01", "ridgeview"),
          ("the Harlow Station incident", "Harlow Station", "topic_07", "harlowstation")]

# (template, extra_topics, hashtags). {event}/{short}/{tag}/{n} are filled in.
TEMPLATES: dict[str, list[tuple[str, list[str], list[str]]]] = {
    "NEWS_REPORTING": [
        ("Police said the investigation into {event} is ongoing, according to a statement released this morning.", [], ["news"]),
        ("Court update: the trial linked to {event} has been adjourned, officials said.", [], ["news", "{tag}"]),
        ("Breaking: authorities confirmed a memorial for victims of {event} will be held this weekend.", [], ["{tag}"]),
        ("Investigators reported no further suspects in {event}, a spokesperson said.", [], ["news"]),
        ("Reporters at the press conference asked officials about school safety funding after {event}.", ["topic_04"], ["news", "schoolsafety"]),
    ],
    "ACADEMIC_OR_RESEARCH": [
        ("New peer-reviewed study on how online fandoms form around attackers after events like {event}. Thread on the methodology.", ["topic_04"], ["research", "tcc"]),
        ("Researchers found hashtag communities around {event} grew fastest in the first week. Paper in the journal this month.", ["topic_04"], ["research", "{tag}"]),
        ("Seminar today: criminology perspectives on copycat risk and media contagion.", ["topic_04"], ["criminology"]),
        ("Our survey of 1,200 students suggests most true-crime viewers reject glorification. Findings below.", ["topic_04", "topic_05"], ["research", "truecrime"]),
        ("Literature review: guidelines on not naming perpetrators reduce attention-seeking. Useful dataset for journalism students.", ["topic_04"], ["nonotoriety", "research"]),
    ],
    "PREVENTION_OR_SUPPORT": [
        ("Stop calling the {short} attacker a hero. Remember the victims and their families.", ["topic_03"], ["nonotoriety", "{tag}"]),
        ("If you or someone you know is struggling, please reach out. You are not alone. Email help@example.org", ["topic_03"], ["mentalhealth"]),
        ("Teachers: warning signs can be subtle. Talk to a trusted colleague or counsellor and report concerns early.", ["topic_03"], ["schoolsafety"]),
        ("Don't share fan edits of the perpetrator. Say the victims' names instead.", ["topic_03", "topic_02"], ["nonotoriety", "tcc"]),
        ("Check in on your friends this week. Crisis line volunteers are available 24/7.", ["topic_03"], ["mentalhealth"]),
    ],
    "NEUTRAL_DISCUSSION": [
        ("Just watched the new documentary about {event}. The timeline section was confusing, anyone else?", ["topic_05"], ["truecrime", "{tag}"]),
        ("Podcast episode on {event} dropped today. Curious what people think about the case files they released.", ["topic_05"], ["truecrime", "podcast"]),
        ("Thoughts on the book about {event}? Halfway through and it goes deep on the investigation failures.", ["topic_05"], ["truecrime", "booktok"]),
        ("Anyone know if the series covers the {short} case too? cc @casefan_22", ["topic_05"], ["truecrime"]),
        ("Listening to a true crime podcast on my commute, this week's case is from the 1990s.", ["topic_05"], ["truecrime", "podcast"]),
    ],
    "GLORIFICATION_OR_PRAISE": [
        ("The {short} attacker is a legend honestly. Deserves respect #{tag}", ["topic_02"], ["tcc", "{tag}"]),
        ("New fan edit of him dropped, so iconic", ["topic_02"], ["tcc", "fanedit", "{tag}"]),
        ("Rest in power to the king of {short}. Never forget the legend.", ["topic_02"], ["tcc", "{tag}"]),
        ("People don't get it, he did what he had to. Absolute icon.", ["topic_02"], ["tcc"]),
        ("Made a little shrine for him in my room lol, idol forever", ["topic_02"], ["tcc", "fanedit"]),
        ("Still think he was right tbh. Showed them all.", [], ["tcc", "{tag}"]),
    ],
    "ENCOURAGEMENT_OR_RECRUITMENT": [
        ("{n} days until the anniversary. Who's next?", [], ["anniversarycountdown", "tcc"]),
        ("Someone needs to finish what he started.", [], ["anniversarycountdown"]),
        ("Join our private server for real fans, DM for the link", ["topic_02"], ["tcc", "anniversarycountdown"]),
        ("Follow his example, be the next one people remember.", [], ["anniversarycountdown", "tcc"]),
    ],
    "EXPLICIT_THREAT_OR_INTENT": [
        ("I'm going to do what he did at my school. They'll all regret it.", [], ["anniversarycountdown"]),
        ("Finished my manifesto. I'm going to make them pay on the anniversary.", [], ["anniversarycountdown"]),
        ("I will be the next one, at my school, mark the date.", [], ["anniversarycountdown", "tcc"]),
    ],
    # Deliberately ambiguous: keywords without clear context, sarcasm, reported speech.
    "AMBIGUOUS": [
        ("the {short} attack changed everything", [], ["{tag}"]),
        ("lol the {short} shooter memes are getting out of hand", ["topic_02"], ["tcc", "{tag}"]),
        ("honestly can't stop thinking about the attacker. not sure how i feel.", [], ["tcc"]),
        ("Saying he was a hero is a joke right? right??", ["topic_02"], ["tcc"]),
        ("Researchers call him an icon of the online subculture, which worries me", ["topic_04"], ["research", "tcc"]),
    ],
}

# Bahasa Malaysia posts (classifier is not validated for 'ms'; these should be routed to review).
MALAY = [
    ("Jangan sebarkan video serangan itu. Ingat mangsa dan keluarga mereka.", ["topic_03"], ["nonotoriety"]),
    ("Dia memang legenda, hormat #{tag}", ["topic_02"], ["tcc", "{tag}"]),
    ("Ada sesiapa tonton dokumentari tentang kes {short}?", ["topic_05"], ["truecrime"]),
]

BASE_MIX = {
    "NEWS_REPORTING": 0.17, "ACADEMIC_OR_RESEARCH": 0.12, "PREVENTION_OR_SUPPORT": 0.14,
    "NEUTRAL_DISCUSSION": 0.24, "GLORIFICATION_OR_PRAISE": 0.17, "ENCOURAGEMENT_OR_RECRUITMENT": 0.02,
    "AMBIGUOUS": 0.10, "MALAY": 0.04,
}
TREND_MIX = {  # posts in the emerging "anniversary countdown" topic
    "GLORIFICATION_OR_PRAISE": 0.38, "ENCOURAGEMENT_OR_RECRUITMENT": 0.27, "AMBIGUOUS": 0.12,
    "PREVENTION_OR_SUPPORT": 0.15, "EXPLICIT_THREAT_OR_INTENT": 0.08,
}
BASE_PER_WEEK = [24, 26, 23, 27, 25, 26, 24, 25]
TREND_PER_WEEK = [0, 1, 0, 2, 1, 7, 13, 21]


def _fill(s: str, event: tuple, n: int) -> str:
    return s.format(event=event[0], short=event[1], tag=event[3], n=n)


def generate(seed: int) -> list[dict]:
    rng = random.Random(seed)
    authors = [f"synthetic_account_{i:03d}" for i in range(70)]
    posts: list[dict] = []

    def make(kind: str, ts: datetime, trend: bool) -> dict:
        pool = MALAY if kind == "MALAY" else TEMPLATES[kind]
        text, extra_topics, tags = rng.choice(pool)
        event = rng.choices(EVENTS, weights=[0.75, 0.25])[0]
        days_left = max(1, (START + timedelta(weeks=WEEKS, days=6) - ts).days)
        hashtags = {_fill(t, event, days_left) for t in tags}
        if trend:
            # Trend posts belong to the event and the trend only, so that the
            # simulated growth stays in one topic.
            topics = {event[2], "topic_06"}
            hashtags.add("anniversarycountdown")
        else:
            topics = {event[2], *extra_topics}
        if kind == "MALAY":
            lang = "ms"
        else:
            lang = "en"
        refs = []
        if posts and rng.random() < 0.15:
            refs = [rng.choice(posts[-40:])["id"]]
        return {
            "source_type": "synthetic",
            "source_name": SOURCE_NAME,
            "source_url": None,
            "published_at": ts.isoformat().replace("+00:00", "Z"),
            "text": _fill(text, event, days_left),
            "language": lang,
            "hashtags": sorted(hashtags),
            "public_topic_ids": sorted(topics),
            "author_reference": rng.choice(authors),
            "interaction_reference_ids": refs,
            "is_synthetic": True,
            "_generator_kind": kind,
        }

    batch: list[tuple[datetime, str, bool]] = []
    for week in range(WEEKS):
        week_start = START + timedelta(weeks=week)
        for mix, count, trend in ((BASE_MIX, BASE_PER_WEEK[week], False), (TREND_MIX, TREND_PER_WEEK[week], True)):
            kinds = rng.choices(list(mix), weights=list(mix.values()), k=count)
            for kind in kinds:
                ts = week_start + timedelta(seconds=rng.randrange(7 * 24 * 3600))
                batch.append((ts, kind, trend))
    for ts, kind, trend in sorted(batch):
        record = make(kind, ts, trend)
        record["id"] = f"post_{len(posts) + 1:04d}"
        posts.append(record)
    return [{"id": p.pop("id"), **p} for p in posts]


def write(seed: int = 2) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    posts = generate(seed)
    (OUT_DIR / "posts.json").write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "topics.json").write_text(json.dumps(TOPICS, indent=2), encoding="utf-8")
    print(f"Wrote {len(posts)} synthetic posts and {len(TOPICS)} topics to {OUT_DIR}")
    return len(posts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=2)
    write(parser.parse_args().seed)


if __name__ == "__main__":
    main()
