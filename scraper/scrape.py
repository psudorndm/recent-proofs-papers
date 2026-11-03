#!/usr/bin/env python3
"""
Harvest recent papers on cryptographic proof systems, security proofs, and
formal verification of cryptography from arXiv (Atom API) and the IACR
Cryptology ePrint Archive (OAI-PMH), and write them into the flat text files
consumed by index.html.

Adapted from MaherMamah7/Recent-post-quantum-papers (used with permission).

Storage: data/<source>/<year>.txt (source = eprint or arxiv), one paper per
line, newest first, plus data/index.json listing the files:

    title;;;authors;;;id;;;repo;;;date;;;categories

  - title       paper title (single line)
  - authors     comma-separated author names
  - id          arXiv id (e.g. 2501.01234) or ePrint id (e.g. 2026/0421)
  - repo        source-code URL if we could find one, else "none"
  - date        YYYY-MM-DD (announced / submitted date)
  - categories  comma-separated topic paths from taxonomy.toml, deepest
                matches only, e.g. proofs/pcs/lattice,security

Abstracts are kept one per file: data/abstracts/<source>/<id>.txt (an arXiv id
2611.02819 is stored as 2611/02819.txt). data/taxonomy.json is the topic tree
for the page. Every run re-tags all stored papers with taxonomy.toml.

Run:  python scrape.py            # merge the last 30 days into data/
      python scrape.py --full     # re-harvest everything and replace data/
      python scrape.py --no-fetch # only re-tag stored papers (after editing taxonomy.toml)
"""

import argparse
import datetime as dt
import html
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

ARXIV_API = "https://export.arxiv.org/api/query"
EPRINT_OAI = "https://eprint.iacr.org/oai"

# arXiv subject classes where proof-system, security-proof, and
# verification work appears.
ARXIV_CATEGORIES = ["cs.CR", "cs.CC", "cs.LO", "cs.PL", "cs.IT", "quant-ph"]

USER_AGENT = "proofs-papers/1.0 (recent proof systems, security proofs & formal verification index)"

# Daily update window, in days. Updates are merged into the stored history,
# so this only has to cover the gap since the last successful run.
DEFAULT_LOOKBACK_DAYS = 30

# --------------------------------------------------------------------------
# Topic matching: the hierarchy and its keywords live in taxonomy.toml
# (loaded and applied by scraper/taxonomy.py).
# --------------------------------------------------------------------------

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import taxonomy  # noqa: E402

_TOPICS = None


def topics():
    global _TOPICS
    if _TOPICS is None:
        _TOPICS = taxonomy.load()
    return _TOPICS


def classify(text):
    """Deepest matching topic paths, e.g. {"proofs/pcs/lattice", "security"}."""
    return taxonomy.classify(topics(), text)


GITHUB_RE = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/[^\s)\]\}<>\"']+",
                       re.IGNORECASE)


def find_repo(text):
    m = GITHUB_RE.search(text or "")
    if not m:
        return "none"
    # strip common trailing punctuation
    return m.group(0).rstrip(".,);]")


def clean(text):
    """Collapse whitespace and strip; remove the ;;; delimiter if present."""
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace(";;;", "; ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


# --------------------------------------------------------------------------
# HTTP helper
# --------------------------------------------------------------------------

def http_get(url, retries=4):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001 - network flakiness, retry
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} tries: {url}\n{last_err}")


# --------------------------------------------------------------------------
# arXiv
# --------------------------------------------------------------------------

ATOM_NS = {"a": "http://www.w3.org/2005/Atom",
           "arxiv": "http://arxiv.org/schemas/atom"}
OS_NS = {"os": "http://a9.com/-/spec/opensearch/1.1/"}


def arxiv_query_string():
    """Build the OR-joined keyword query, scoped to relevant categories."""
    # Phrases arXiv matches server-side (arxiv_terms in taxonomy.toml). They are
    # a little broader than the patterns, which re-filter the results.
    terms = [t for topic in topics() for t in topic.arxiv_terms]
    abs_q = " OR ".join(f'abs:"{t}"' for t in terms)
    cat_q = " OR ".join(f"cat:{c}" for c in ARXIV_CATEGORIES)
    return f"({cat_q}) AND ({abs_q})"


ARXIV_FIRST_YEAR = 1991  # arXiv's first year


def _arxiv_page(search, start, page):
    """One page of results (entries, total). arXiv sometimes returns an empty
    page by mistake, so retry a couple of times before believing it."""
    params = {
        "search_query": search,
        "start": start,
        "max_results": page,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = ARXIV_API + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        root = ET.fromstring(http_get(url))
        entries = root.findall("a:entry", ATOM_NS)
        total = int(root.findtext("os:totalResults", default="0", namespaces=OS_NS) or 0)
        if entries or start >= total:
            return entries, total
        time.sleep(5 * (attempt + 1))
    return entries, total


def fetch_arxiv(now, lookback_days=None):
    """Recent papers (newest first, stop at the cutoff), or, with
    lookback_days=None, the full history, one submission year at a time so
    each query stays well inside the API's paging limits."""
    if lookback_days is None:
        papers = {}
        for year in range(ARXIV_FIRST_YEAR, now.year + 1):
            search = (f"({arxiv_query_string()}) AND "
                      f"submittedDate:[{year}01010000 TO {year}12312359]")
            got = _fetch_arxiv_query(search, cutoff=None)
            print(f"    arXiv {year}: {len(got)} papers", file=sys.stderr)
            papers.update(got)
        return list(papers.values())
    cutoff = now - dt.timedelta(days=lookback_days)
    return list(_fetch_arxiv_query(arxiv_query_string(), cutoff).values())


def _fetch_arxiv_query(search, cutoff):
    papers = {}
    start = 0
    page = 200
    while True:
        entries, total = _arxiv_page(search, start, page)
        if not entries:
            break
        oldest_on_page = None
        for e in entries:
            pub = e.findtext("a:published", default="", namespaces=ATOM_NS)
            try:
                pdate = dt.datetime.strptime(pub[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            oldest_on_page = pdate if oldest_on_page is None else min(oldest_on_page, pdate)

            raw_id = e.findtext("a:id", default="", namespaces=ATOM_NS)
            # e.g. http://arxiv.org/abs/2501.01234v2  ->  2501.01234
            m = re.search(r"abs/(.+?)(v\d+)?$", raw_id)
            if not m:
                continue
            aid = m.group(1)

            title = clean(e.findtext("a:title", default="", namespaces=ATOM_NS))
            summary = clean(e.findtext("a:summary", default="", namespaces=ATOM_NS))
            comment = clean(e.findtext("arxiv:comment", default="", namespaces=ATOM_NS))

            cats = classify(title + " " + summary)
            if not cats:
                continue

            repo = find_repo(summary + " " + comment)
            authors = [clean(a.findtext("a:name", default="", namespaces=ATOM_NS))
                       for a in e.findall("a:author", ATOM_NS)]

            papers[aid] = {
                "title": title,
                "authors": [a for a in authors if a],
                "id": aid,
                "repo": repo,
                "date": pdate,
                "cats": cats,
                "abstract": summary,
            }

        start += page
        if cutoff is not None and oldest_on_page is not None and oldest_on_page < cutoff:
            break
        if start >= total or start >= 25000:  # end of results / safety valve
            break
        time.sleep(3)  # arXiv asks for 3 seconds between API calls
    return papers


# --------------------------------------------------------------------------
# IACR ePrint (OAI-PMH)
# --------------------------------------------------------------------------

OAI_NS = {"oai": "http://www.openarchives.org/OAI/2.0/",
          "dc": "http://purl.org/dc/elements/1.1/",
          "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/"}


def fetch_eprint(now, lookback_days=None):
    """Records changed in the window (lookback_days=None: the whole archive)."""
    base = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
    if lookback_days is not None:
        base["from"] = (now - dt.timedelta(days=lookback_days)).isoformat()
    url = EPRINT_OAI + "?" + urllib.parse.urlencode(base)
    papers = {}
    while True:
        xml = http_get(url)
        root = ET.fromstring(xml)
        for rec in root.findall(".//oai:record", OAI_NS):
            header = rec.find("oai:header", OAI_NS)
            if header is not None and header.get("status") == "deleted":
                continue
            md = rec.find(".//oai_dc:dc", OAI_NS)
            if md is None:
                continue

            identifier = ""
            for ident in md.findall("dc:identifier", OAI_NS):
                if ident.text and "eprint.iacr.org" in ident.text:
                    identifier = ident.text
                    break
            m = re.search(r"(\d{4}/\d+)", identifier)
            if not m:
                continue
            eid = m.group(1)

            title = clean(md.findtext("dc:title", default="", namespaces=OAI_NS))
            abstract = clean(md.findtext("dc:description", default="", namespaces=OAI_NS))
            authors = [clean(c.text) for c in md.findall("dc:creator", OAI_NS) if c.text]

            dates = [d.text for d in md.findall("dc:date", OAI_NS) if d.text]
            pdate = None
            for d in dates:
                try:
                    pdate = dt.datetime.strptime(d[:10], "%Y-%m-%d").date()
                    break
                except ValueError:
                    continue
            if pdate is None:
                continue

            cats = classify(title + " " + abstract)
            if not cats:
                continue

            repo = find_repo(abstract)
            papers[eid] = {
                "title": title,
                "authors": authors,
                "id": eid,
                "repo": repo,
                "date": pdate,
                "cats": cats,
                "abstract": abstract,
            }

        token_el = root.find(".//oai:resumptionToken", OAI_NS)
        token = token_el.text if token_el is not None else None
        if not token:
            break
        url = EPRINT_OAI + "?" + urllib.parse.urlencode(
            {"verb": "ListRecords", "resumptionToken": token})
        time.sleep(1)
    return list(papers.values())


# --------------------------------------------------------------------------
# Storage: data/<source>/<year>.txt plus data/index.json
# --------------------------------------------------------------------------

def to_line(p):
    fields = [
        p["title"],
        ", ".join(p["authors"]),
        p["id"],
        p["repo"],
        p["date"].isoformat(),
        ",".join(sorted(p["cats"])),
    ]
    return ";;;".join(fields)


def from_line(line):
    v = line.rstrip("\n").split(";;;")
    if len(v) != 6:
        return None
    return {
        "title": v[0],
        "authors": [a.strip() for a in v[1].split(",") if a.strip()],
        "id": v[2],
        "repo": v[3],
        "date": dt.date.fromisoformat(v[4]),
        "cats": set(c for c in v[5].split(",") if c),
    }


def load_store(source_dir):
    """All stored papers of one source, keyed by id."""
    papers = {}
    for path in sorted(source_dir.glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            p = from_line(line)
            if p:
                papers[p["id"]] = p
    return papers


def save_store(source_dir, papers):
    """Write one file per year (newest first) and return {year: count}."""
    source_dir.mkdir(parents=True, exist_ok=True)
    by_year = {}
    for p in papers.values():
        by_year.setdefault(p["date"].year, []).append(p)
    for old in source_dir.glob("*.txt"):
        if int(old.stem) not in by_year:
            old.unlink()
    counts = {}
    for year, items in by_year.items():
        items.sort(key=lambda p: (p["date"], p["id"]), reverse=True)
        (source_dir / f"{year}.txt").write_text(
            "".join(to_line(p) + "\n" for p in items), encoding="utf-8")
        counts[year] = len(items)
    return counts


def abstract_path(data_dir, source, pid):
    """data/abstracts/eprint/2026/2683.txt, data/abstracts/arxiv/2611/02819.txt
    (old-style arXiv ids such as cs/0101001 already contain a slash)."""
    rel = pid if "/" in pid else pid.replace(".", "/", 1)
    return data_dir / "abstracts" / source / (rel + ".txt")


def read_abstract(data_dir, source, pid):
    """The stored abstract ("" if the paper has none), or None if not stored."""
    try:
        return abstract_path(data_dir, source, pid).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None


def write_abstract(data_dir, source, pid, text):
    path = abstract_path(data_dir, source, pid)
    content = text + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def prune_abstracts(data_dir, source, keep_ids):
    """Delete abstracts of papers that are no longer stored."""
    base = data_dir / "abstracts" / source
    if not base.exists():
        return
    keep = {abstract_path(data_dir, source, pid) for pid in keep_ids}
    for f in base.rglob("*.txt"):
        if f not in keep:
            f.unlink()
    for d in sorted((d for d in base.rglob("*") if d.is_dir()), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()


def write_index(data_dir, now):
    """data/index.json lists the year files of each source and their sizes."""
    index = {"updated": now.isoformat()}
    for source in SOURCES:
        files = sorted((data_dir / source).glob("*.txt"), reverse=True)
        index[source] = {f.stem: sum(1 for _ in f.open(encoding="utf-8")) for f in files}
    (data_dir / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")


SOURCES = ("eprint", "arxiv")


def retag(data_dir, source, papers):
    """Apply the current taxonomy to every paper. Returns (kept, dropped ids).
    Papers whose abstract was never stored keep their current topics."""
    kept, dropped = {}, []
    for pid, p in papers.items():
        abstract = p.get("abstract")
        if abstract is None:
            abstract = read_abstract(data_dir, source, pid)
        if abstract is None:
            kept[pid] = p
            continue
        cats = classify(p["title"] + " " + abstract)
        if cats:
            p["cats"] = cats
            kept[pid] = p
        else:
            dropped.append(pid)
    return kept, dropped


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                    help="update window in days (default: %(default)s)")
    ap.add_argument("--full", action="store_true",
                    help="harvest the whole history and replace the stored data")
    ap.add_argument("--no-fetch", action="store_true",
                    help="harvest nothing; only re-tag stored papers with taxonomy.toml")
    ap.add_argument("--allow-drop", action="store_true",
                    help="allow a re-tag to drop more than 20%% of a source's papers")
    ap.add_argument("--data-dir", default="data", type=pathlib.Path)
    ap.add_argument("--skip-arxiv", action="store_true")
    ap.add_argument("--skip-eprint", action="store_true")
    args = ap.parse_args()

    try:
        topics()
    except taxonomy.TaxonomyError as e:
        sys.exit(f"taxonomy.toml: {e}")

    now = dt.date.today()
    window = None if args.full else args.days
    fetchers = {"eprint": ("IACR ePrint (OAI-PMH)", fetch_eprint),
                "arxiv": ("arXiv (Atom API)", fetch_arxiv)}

    # Work out every source's result first, so a bad taxonomy edit writes nothing.
    results = {}
    for source in SOURCES:
        stored = load_store(args.data_dir / source)
        fetched = {}
        harvest = not args.no_fetch and not getattr(args, f"skip_{source}")
        if harvest:
            label, fetch = fetchers[source]
            print(f"Harvesting {label}{' - full history' if args.full else ''}...", file=sys.stderr)
            fetched = {p["id"]: p for p in fetch(now, window)}
        papers = {} if (args.full and harvest) else dict(stored)
        papers.update(fetched)
        kept, dropped = retag(args.data_dir, source, papers)
        if dropped and not args.full and not args.allow_drop and len(dropped) > 0.2 * len(papers):
            sys.exit(f"{source}: the current taxonomy.toml would drop {len(dropped)} of {len(papers)} "
                     "stored papers (they match no topic). Nothing was written. If that is intended, "
                     "re-run with --allow-drop.")
        results[source] = (stored, fetched, kept, dropped)

    for source, (stored, fetched, kept, dropped) in results.items():
        for pid, p in fetched.items():
            if pid in kept:
                write_abstract(args.data_dir, source, pid, p["abstract"])
        counts = save_store(args.data_dir / source, kept)
        prune_abstracts(args.data_dir, source, kept)
        print(f"  {source}: fetched {len(fetched)}, stored {sum(counts.values())} "
              f"({sum(counts.values()) - len(stored):+d}), dropped {len(dropped)} "
              f"that match no topic", file=sys.stderr)

    write_index(args.data_dir, now)
    (args.data_dir / "taxonomy.json").write_text(
        json.dumps({"topics": taxonomy.export(topics())}, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
