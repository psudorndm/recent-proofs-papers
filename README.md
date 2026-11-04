# recent proofs papers: archive for recent works on proof systems, security proofs & formal verification

A tiny static site that lists recent papers on **cryptographic proof systems**,
**security proofs**, and **formal verification** of cryptography. It pulls
metadata from two sources, shows papers from *this week / this month / this year*,
and keeps the full history below, one collapsible section per year. Topics form a
hierarchy (e.g. *proof systems › PCS › lattice-based*) defined in
[`taxonomy.toml`](taxonomy.toml), which anyone can extend — see
[CONTRIBUTING.md](CONTRIBUTING.md).

The design, scraper, and update workflow are adapted from Maher Mamah's
[recent post-quantum papers](https://github.com/MaherMamah7/Recent-post-quantum-papers)
([pqc-reference.org](https://pqc-reference.org/)), used with permission.

- **arXiv** — via the public [Atom API](https://info.arxiv.org/help/api/index.html)
  (categories `cs.CR`, `cs.CC`, `cs.LO`, `cs.PL`, `cs.IT`, `quant-ph`).
- **IACR Cryptology ePrint Archive** — via its
  [OAI-PMH](https://www.openarchives.org/pmh/) endpoint (metadata is CC0).

## How it works

```
taxonomy.toml ──┐
scraper/scrape.py  ──>  data/eprint/<year>.txt
                   ──>  data/arxiv/<year>.txt
                   ──>  data/abstracts/<source>/<id>.txt   (one abstract per paper)
                   ──>  data/index.json      (which year files exist, and their sizes)
                   ──>  data/taxonomy.json   (the topic tree, for the page)
index.html  ──(fetch + render in the browser)──>  the page
```

The scraper tags each paper by matching the patterns in `taxonomy.toml` against its
title and abstract, and stores one line per paper, newest first, in the file for the
year of its date. Every run re-tags all stored papers from their saved abstracts, so a
taxonomy edit applies to the whole history without re-downloading anything.

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
| `categories` | deepest matching topic paths, e.g. `proofs/pcs/lattice,security` |

The page has a search box (titles, authors, IDs); **topic** rows that drill down
the hierarchy (pick *proof systems*, then *PCS*, then *lattice-based*; clicking a tag on
any paper does the same); **source** (ePrint / arXiv / both); and a **year** box that takes a year (`2019`)
or a range (`2018-2021`, `2020-`, `-2005`) and shows just those years, expanded.
Every section (this week / month / year, and each older year) can be collapsed.
Clicking a paper's title shows its abstract (loaded only then, so the page stays light).
The page loads the last year first, then the older years in the background; once
they are loaded, search covers the whole history and opens every year that has matches.

Plain text is kept on purpose: GitHub Pages serves these files gzip-compressed,
which shrinks them about 3×, and per-year files mean the daily update only
changes the current year.

## Running the scraper

No third-party dependencies — standard library only (Python 3.11+, for `tomllib`).

```bash
python3 scraper/scrape.py            # merge the last 30 days into data/ (default)
python3 scraper/scrape.py --days 90  # merge a longer window
python3 scraper/scrape.py --full     # re-harvest the whole history and replace data/
python3 scraper/scrape.py --no-fetch # only re-tag stored papers with taxonomy.toml
python3 scraper/scrape.py --skip-arxiv   # only refresh ePrint
python3 scraper/taxonomy.py --check  # validate taxonomy.toml, count papers per topic
```

## Viewing locally

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

(A plain `file://` open will not work because the page fetches the `.txt`
files, which browsers block over `file://`.)

## Tuning what gets included

Everything is in [`taxonomy.toml`](taxonomy.toml): each topic's keywords, its
sub-topics, shared sub-topic lists such as the assumptions, and the phrases the arXiv
harvest searches for. [CONTRIBUTING.md](CONTRIBUTING.md) explains the format.
