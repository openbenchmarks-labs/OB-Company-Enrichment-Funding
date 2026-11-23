# data

This folder holds a 4-company public sample (`sample.jsonl`) for offline verification (`selftest`) and schema reference.

## Public vs. held-out evaluation sets

- **Public split:** 10 companies published on Hugging Face at [`openbenchmarks/OB-Company-Funding`](https://huggingface.co/datasets/openbenchmarks/OB-Company-Funding).
- **Public sample (`sample.jsonl`):** 4 well-known companies (`stripe.com`, `vercel.com`, `linear.app`, `supabase.com`) used to verify the CLI and grader without API keys.
- **Held-out split (private):** The Enrichment and Freshness cohorts used for the published leaderboard stay private so providers cannot train on it. Pass your own JSONL file with `--tasks <path>`.

## Files and schema

- `sample.jsonl` — One JSON object per line.

| Field | Type | Description |
|---|---|---|
| `domain` | string | Canonical company domain (for example, `stripe.com`). |
| `company` | string | Company name. |
| `latest_stage` | string | Latest funding round stage (for example, `Series C`). |
| `amount` | integer | Funding round amount, in USD unless `currency` names another. |
| `announced_on` | string | Announcement date (`YYYY-MM-DD`). |
