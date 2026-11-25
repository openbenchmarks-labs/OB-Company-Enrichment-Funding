# data

`sample.csv` holds the 10 public companies from [`openbenchmarks/OB-Company-Enrichment-Funding`](https://huggingface.co/datasets/openbenchmarks/OB-Company-Enrichment-Funding), one row per company. The runners and the judge read this format, or a Hugging Face dataset file (JSONL) as published; pass another file with `--input`. A Hugging Face row is read as the columns below: `case_id` as `candidate_id`, `input_name` as `company_name`, `input_domain` as `company_domain`, and `latest_stage`, `latest_announced_on`, `latest_amount` and `currency` as the four `answer_` columns.

| Column | Read by | Meaning |
|---|---|---|
| `candidate_id` | runners, judge | Stable id of the company row. |
| `company_name` | runners, judge | Company name. |
| `company_domain` | runners, judge | Company domain. Data APIs get only this. |
| `answer_stage` | judge | Latest funding stage in the answer key. |
| `answer_announced_on` | judge | Announcement date of that round (`YYYY-MM-DD`). |
| `answer_amount` | judge | Round amount in whole currency units. |
| `answer_currency` | none | Currency of the amount. |
