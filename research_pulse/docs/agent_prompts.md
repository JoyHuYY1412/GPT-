# Research Pulse Agent Prompts

This file records the backend-facing prompt policy used by scheduled Research Pulse agents.

## Daily Research Agent

Generate the prompt with:

```bash
python agent_daily.py --print-prompt
```

Or save it for the next scheduled run:

```bash
python agent_daily.py --write-prompt
```

Core constraints:

- Do not create demo, placeholder, or example cards.
- Do not repeat papers, projects, profiles, or people already imported.
- Prefer fewer high-quality items over filling every quota.
- Every paper-like item must have at least one source link: paper, PDF, project, code, GitHub, DOI, or source.
- arXiv entries must come from real arXiv records.
- Weekend arXiv gaps should not create empty historical dates.
- Tags must be useful topical tags, not source labels or filler labels.
- Chinese summaries must explain the actual problem, method, result, and value.
- Chinese abstracts should faithfully track the English abstract rather than compressing it into a short comment.
- Contributions and framework fields must contain explanatory bullet points, not bare headings.
- Uncertain citations, titles, affiliations, lineage, or awards must be marked as pending verification.

## Quality Gate

`agent_daily.py` rejects low-quality imported items before writing to SQLite. It skips entries with:

- invalid kind
- weak title
- summary shorter than 60 characters
- missing source link for paper-like modules
- missing profile/homepage link for scholar cards
- very short Chinese abstract for arXiv/recent/science items
- missing contribution or framework lists for paper-like modules
- only filler tags such as `arxiv`, `daily`, `context`, `agent generated`, `demo`, `科学推理`, or `高影响力`

## User Isolation

- The global `items` table is the shared research feed.
- `user_settings`, `favorites`, `notes`, `chat_messages`, `inbox`, and `agent_tasks` are scoped by `user_id`.
- Local notes are saved under `notes_path/<username>/`.
- The repository preview for `notes` opens the current user's notes root, not the shared parent directory.
- QMem/wiki/papers paths come from each user's own settings.

## Bigshot Follow Agent

The monthly bigshot follow task is queued from the website. It should:

- update Google Scholar total citations when available
- detect whether the author has new papers this month
- collect the latest five Google Scholar papers by time
- collect up to five representative works with average yearly citations greater than 100
- link paper titles to Google Scholar detail pages when possible, otherwise to a Google Scholar title search
- update early focus, recent focus, title, institution, and homepage links
- never invent citations or Scholar URLs
