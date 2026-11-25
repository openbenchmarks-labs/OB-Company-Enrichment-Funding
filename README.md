# OB-Company-Funding

Open, independent benchmark of company funding data APIs. Each provider gets a company and returns the company's latest funding round. The board scores the latest funding stage against a reviewed answer key.

**Live leaderboard:** [openbenchmarks.com/company-funding](https://openbenchmarks.com/company-funding) · **Public dataset:** [`openbenchmarks/OB-Company-Funding`](https://huggingface.co/datasets/openbenchmarks/OB-Company-Funding)

Published and maintained by **[OpenBenchmarks Labs](https://openbenchmarks.com)**.

## How it works

1. **Run.** Each provider is called once per company. Data APIs get the company domain. Research APIs get the same instruction and the same output schema (`harness/run_research.py`, `instruction()` and `OUTPUT_SCHEMA`). Every response is saved as one JSON file per company under `runs/raw/<provider>/`.
2. **Judge.** GPT-5.6 at medium reasoning effort compares each provider's latest stage with the answer key, 50 records per call (`judge/judge.py`). The rules are in the prompt: Series letters are strict, a fixed list of seed, private equity and crowdfunding labels are equivalent, Seed and Pre-Seed differ, a blank answer-key stage passes every answer, and for other stages an exactly equal date or amount also counts.
3. **Board.** Stage correct over every company in the cohort (`judge/board.py`).

Amount and date are not scored on their own. The judge reads them only for rule 7. Before the judge sees a provider's amount, `usd_amount()` reads it as US dollars ("9M", "$4.35M", "9000000 USD"); an amount written with another currency, such as "5M EUR", is passed as empty. The judge does not see the `currency` field of the answer or of the key, so a bare number in another currency is compared as it is.

## Providers

| Kind | Providers | Code |
|---|---|---|
| Data APIs | `fiber`, `predictleads`, `apollo`, `people-data-labs`, `ocean`, `explorium`, `company-enrich`, `fundable` | `harness/data_apis.py`, `harness/run_data_apis.py` |
| Research APIs | `exa`, `exa-instant`, `exa-agent`, `parallel`, `parallel-responses-medium`, `firecrawl`, `firecrawl-spark-2`, `seltz-companies`, `seltz-news`, `nimble-lite`, `nimble-standard`, `nimble-agents` | `harness/run_research.py`, `harness/nimble*.py` |
| Batch APIs | `crustdata`, `zoominfo` | `harness/run_crustdata.py`, `harness/run_zoominfo.py` |

## Dataset

- `data/sample.csv`: the 10 public companies from Hugging Face, in the input format the runners read.
- The companies behind the published board stay private, so providers cannot train on them.

See [`data/README.md`](data/README.md) for the columns.

## Run it

```sh
uv venv && uv pip install -r requirements.txt
cp .env.example .env   # add the keys for the providers you run
```

Calls below are billed by each provider. `--dry-run` shows the plan and calls nothing.

```sh
.venv/bin/python -m harness.run_research exa --dry-run
.venv/bin/python -m harness.run_research exa
.venv/bin/python -m harness.run_data_apis --only apollo,fundable
.venv/bin/python -m harness.run_crustdata
.venv/bin/python -m harness.run_zoominfo --run      # needs the ZoomInfo gtm CLI
.venv/bin/python -m judge.judge                     # needs OPENAI_API_KEY
.venv/bin/python -m judge.board
```

## Related benchmarks

- [OB-Company-Enrichment](https://github.com/openbenchmarks-labs/OB-Company-Enrichment): firmographic enrichment
- [OB-Company-News](https://github.com/openbenchmarks-labs/OB-Company-News): company news search
- [OB-Company-Search-Lookalikes](https://github.com/openbenchmarks-labs/OB-Company-Search-Lookalikes): company lookalike discovery
- [All OpenBenchmarks leaderboards](https://openbenchmarks.com)

## License

MIT. See [LICENSE](LICENSE).
