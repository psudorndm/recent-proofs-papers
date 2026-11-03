# recent proofs papers — proof systems, security proofs & formal verification

A tiny static site that lists recent papers on **cryptographic proof systems**,
**security proofs**, and **formal verification** of cryptography. It pulls
metadata from two sources and buckets papers into *this week / this month / this year*.

The design, scraper, and update workflow are adapted from Maher Mamah's
[recent post-quantum papers](https://github.com/MaherMamah7/Recent-post-quantum-papers)
([pqc-reference.org](https://pqc-reference.org/)), used with permission.

- **arXiv** — via the public [Atom API](https://info.arxiv.org/help/api/index.html)
  (categories `cs.CR`, `cs.CC`, `cs.LO`, `cs.PL`, `cs.IT`, `quant-ph`).
- **IACR Cryptology ePrint Archive** — via its
  [OAI-PMH](https://www.openarchives.org/pmh/) endpoint (metadata is CC0).

## How it works

```
scraper/scrape.py  ──>  papers_arxiv.txt
                   ──>  papers_eprint.txt
index.html  ──(fetch + render in the browser)──>  the page
```

The scraper classifies each paper by keyword matching over its title and abstract
(see `PROOFS_*`, `SECURITY_*`, `FORMAL_*` in `scraper/scrape.py`) and emits one line per paper:

```
title;;;authors;;;id;;;date_class;;;repo;;;date;;;categories
```

| field        | meaning                                              |
|--------------|------------------------------------------------------|
| `title`      | paper title                                          |
| `authors`    | comma-separated author names                         |
| `id`         | arXiv id (`2501.01234`) or ePrint id (`2026/0421`)   |
| `date_class` | `last_week` / `last_month` / `last_year`             |
| `repo`       | a github/gitlab/bitbucket URL if found, else `none`  |
| `date`       | `YYYY-MM-DD`                                          |
| `categories` | subset of `proofs`, `security`, `formal`             |

The page has a search box (titles, authors, IDs) and two filter rows:
**topic** (proof systems / security proofs / formal verification / all) and
**source** (ePrint / arXiv / both).

## Running the scraper

No third-party dependencies — standard library only (Python 3.8+).

```bash
python3 scraper/scrape.py            # 400-day lookback (default)
python3 scraper/scrape.py --days 180 # shorter window
python3 scraper/scrape.py --skip-arxiv   # only refresh ePrint
```

## Viewing locally

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

(A plain `file://` open will not work because the page fetches the `.txt`
files, which browsers block over `file://`.)

## Tuning what gets included

Precision/recall is governed entirely by the keyword lists in
`scraper/scrape.py`:

- `*_CI` — case-insensitive descriptive phrases (e.g. `zero-knowledge`,
  `security proof`, `formal verification`).
- `*_CS` — **case-sensitive** acronyms and tool names (e.g. `STARK`, `NIZK`,
  `Tamarin`, `Coq`) so they don't collide with ordinary words.
- Formal-verification matches also need a cryptographic context phrase
  (`CRYPTO_CONTEXT`), so general program-verification papers are not swept in.

## Automatic updates

`.github/workflows/update.yml` re-runs the scraper once a day and commits the
refreshed `.txt` files as `paper-bot`. Enable GitHub Pages (serving from the repo
root) to publish the site. You can also trigger a refresh on demand from the repo's
**Actions** tab (the workflow has `workflow_dispatch` enabled).
