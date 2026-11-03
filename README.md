# recent proofs papers — proof systems, security proofs & formal verification

A tiny static site that lists recent papers on **cryptographic proof systems**,
**security proofs**, and **formal verification** of cryptography. It pulls
metadata from two sources, shows papers from *this week / this month / this year*,
and keeps the full history below, one collapsible section per year.

The design, scraper, and update workflow are adapted from Maher Mamah's
[recent post-quantum papers](https://github.com/MaherMamah7/Recent-post-quantum-papers)
([pqc-reference.org](https://pqc-reference.org/)), used with permission.

- **arXiv** — via the public [Atom API](https://info.arxiv.org/help/api/index.html)
  (categories `cs.CR`, `cs.CC`, `cs.LO`, `cs.PL`, `cs.IT`, `quant-ph`).
- **IACR Cryptology ePrint Archive** — via its
  [OAI-PMH](https://www.openarchives.org/pmh/) endpoint (metadata is CC0).

## How it works

```
scraper/scrape.py  ──>  data/eprint/<year>.txt
                   ──>  data/arxiv/<year>.txt
                   ──>  data/index.json      (which year files exist, and their sizes)
index.html  ──(fetch + render in the browser)──>  the page
```

The scraper classifies each paper by keyword matching over its title and abstract
(see `PROOFS_*`, `SECURITY_*`, `FORMAL_*` in `scraper/scrape.py`) and stores one line per paper,
newest first, in the file for the year of its date:

```
title;;;authors;;;id;;;repo;;;date;;;categories
```

| field        | meaning                                              |
|--------------|------------------------------------------------------|
| `title`      | paper title                                          |
| `authors`    | comma-separated author names                         |
| `id`         | arXiv id (`2501.01234`) or ePrint id (`2026/0421`)   |
| `repo`       | a github/gitlab/bitbucket URL if found, else `none`  |
| `date`       | `YYYY-MM-DD`                                          |
| `categories` | subset of `proofs`, `security`, `formal`             |

The page has a search box (titles, authors, IDs) and two filter rows:
**topic** (proof systems / security proofs / formal verification / all) and
**source** (ePrint / arXiv / both), plus a **year** box that takes a year (`2019`)
or a range (`2018-2021`, `2020-`, `-2005`) and shows just those years, expanded.
Every section (this week / month / year, and each older year) can be collapsed.
The page loads the last year first, then the older years in the background; once
they are loaded, search covers the whole history and opens every year that has matches.

Plain text is kept on purpose: GitHub Pages serves these files gzip-compressed,
which shrinks them about 3×, and per-year files mean the daily update only
changes the current year.

## Running the scraper

No third-party dependencies — standard library only (Python 3.8+).

```bash
python3 scraper/scrape.py            # merge the last 30 days into data/ (default)
python3 scraper/scrape.py --days 90  # merge a longer window
python3 scraper/scrape.py --full     # re-harvest the whole history and replace data/
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
updated `data/` files as `paper-bot`. Each run merges the last 30 days into the
stored history. Enable GitHub Pages (serving from the repo
root) to publish the site. You can also trigger a refresh on demand from the repo's
**Actions** tab (the workflow has `workflow_dispatch` enabled); tick **full** there to
re-harvest everything, e.g. after changing the keyword lists.
