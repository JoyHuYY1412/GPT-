# Feishu webhook setup

The daily brief workflow already supports Feishu group notification through a GitHub Actions secret named `FEISHU_WEBHOOK`.

Do not commit the webhook URL into this public repository. Treat the webhook as a secret because anyone with the URL can send messages to the group.

## Setup steps

1. Open this repository on GitHub.
2. Go to `Settings` -> `Secrets and variables` -> `Actions`.
3. Click `New repository secret`.
4. Name: `FEISHU_WEBHOOK`.
5. Value: paste the Feishu custom bot webhook URL.
6. Save.

## Test

After the secret is added, open `Actions` -> `Daily Briefs` -> `Run workflow`. The workflow will generate the three daily Markdown files, commit them, and send a Feishu group notification with links.

## Generated files

- `daily-briefs/paper-radar/YYYY-MM-DD.md`
- `daily-briefs/academic-map/YYYY-MM-DD.md`
- `daily-briefs/related_paper-radar/YYYY-MM-DD.md`
