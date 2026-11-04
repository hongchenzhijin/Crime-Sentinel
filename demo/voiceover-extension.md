# Crime Sentinel demo: 50-second extension

This adds three slides to `crime-sentinel-demo.mp4`, between the **Evaluation** shot (1:20) and the **end card**. It is
about 122 words, read at the same pace as the main voiceover (roughly 145 words per minute). The new cut runs 2:19,
and the end card moves from 1:26 to 2:16.

Slides: the "Crime Sentinel: video extension" deck (3 slides; speaker notes hold these lines).

| Time | On screen | Voiceover |
|---|---|---|
| 1:26 | Slide 1: comparison table | Today's tools can't get in. Keyword filters and hash matching only see public posts, and miss context. User reports rely on members who won't report. Human undercover work is slow, costly, and exposes investigators to harm. Crime Sentinel gets inside, under governance. |
| 1:42 | Slide 2: Meta Muse roles | Meta Muse makes the judgement calls. It plans searches and writes the persona's replies. A separate Muse judge, never told the mission goal, audits every message. Muse vision reads the images, one long-context call rates the whole community, and Muse drafts the report. |
| 2:00 | Slide 3: block diagram (Observe → Reason → Verify → Decide, revise loop, foundation row) | Muse agents reason, while hard rules and an independent Muse judge check every message. Humans decide, on a foundation of GraphRAG, PDQ hashing and eighty-eight tests. |
| 2:16 | End card | Crime Sentinel: governed by code, analysed by Muse, decided by humans. |

## Fact check (all from this repo)

- Muse roles and models: `docs/sentinel-agent.md` ("Where Muse is used"). The judge is not told the persona's goal
  (`backend/app/agent/governor.py`).
- Long-context assessment: `Analyst.assess_group`, `reasoning_effort=high`, 1M-token window.
- Stack: `backend/requirements.txt` (FastAPI, pdqhash, networkx, fastembed), `frontend/package.json` (React 19,
  TypeScript, Vite, Tailwind, Cytoscape, Recharts).
- 88 backend tests: `pytest --collect-only` on 2026-11-04.
- The comparison slide makes no numeric claims about other tools. The 45% keyword false-positive rate is already
  said at 1:20, so it is not repeated here.
