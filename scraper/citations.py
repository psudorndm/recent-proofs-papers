#!/usr/bin/env python3
"""Fetch citation counts from OpenAlex into data/citations.json.

    OPENALEX_API_KEY=... python3 scraper/citations.py [--skip-eprint] [--skip-arxiv]

ePrint: OpenAlex lists every work that has a copy in the IACR ePrint archive
(source S2764847869), 100 per request; works are matched to our papers by the
ePrint number in that copy's URL. About 300 requests per run, roughly $0.03 of
a free key's $1 daily budget. Paging past the first page needs a key.

arXiv: each paper is looked up by its arXiv DOI (10.48550/arXiv.<id>).
Single-record lookups are free, with or without a key.

Only papers with at least one citation are written:

    {"updated": "YYYY-MM-DD", "source": "OpenAlex",
     "eprint": {"2019/953": 192, ...}, "arxiv": {"1906.07221": 31, ...}}

A skipped source keeps the counts already in the file.
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scrape  # noqa: E402  (store helpers)

API = "https://api.openalex.org"
EPRINT_SOURCE = "S2764847869"   # "IACR Cryptology ePrint Archive" in OpenAlex
USER_AGENT = "recent-proofs-papers (https://github.com/psudorndm/recent-proofs-papers)"
EPRINT_URL_RE = re.compile(r"eprint\.iacr\.org/(\d{4})/(\d+)")


def get_json(path, params, key, retries=6):
    """GET API+path. Returns parsed JSON, or None for 404 (no such record)."""
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"User-Agent": USER_AGENT}
    if key:
        headers["Authorization"] = "Bearer " + key   # a header keeps the key out of URLs and logs
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            body = e.read().decode("utf-8", errors="replace")[:300]
            if e.code == 429 and "budget" in body.lower():
                sys.exit(f"OpenAlex: daily budget used up ({body}). Try again after midnight UTC.")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = int(e.headers.get("Retry-After") or 0) or 2 ** attempt
                time.sleep(min(wait, 60))
                continue
            raise RuntimeError(f"OpenAlex {e.code} for {path}: {body}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"OpenAlex unreachable for {path}: {e}") from None


def eprint_key(year, number):
    """Compare ePrint numbers as numbers: 1996/014 and 1996/14 are the same paper."""
    return f"{int(year)}/{int(number)}"


def fetch_eprint(ids, key):
    """{our ePrint id: citations} from every OpenAlex work with an ePrint copy."""
    ours = {}
    for pid in ids:
        y, n = pid.split("/")
        ours[eprint_key(y, n)] = pid
    counts, cursor, pages = {}, "*", 0
    while cursor:
        data = get_json("/works", {
            "filter": f"locations.source.id:{EPRINT_SOURCE}",
            "select": "id,cited_by_count,locations",
            "per_page": 100,
            "cursor": cursor,
        }, key)
        pages += 1
        for work in data.get("results", []):
            c = work.get("cited_by_count") or 0
            for loc in work.get("locations") or []:
                for url in (loc.get("landing_page_url"), loc.get("pdf_url")):
                    m = EPRINT_URL_RE.search(url or "")
                    pid = m and ours.get(eprint_key(*m.groups()))
                    if pid:
                        # several OpenAlex records can point at one ePrint paper: keep the largest
                        counts[pid] = max(counts.get(pid, 0), c)
        cursor = (data.get("meta") or {}).get("next_cursor")
        if pages % 50 == 0:
            print(f"    ePrint: {pages} pages read", file=sys.stderr)
        time.sleep(0.2)
    return counts


def fetch_arxiv(ids, key):
    """{arXiv id: citations}, one free lookup per paper by its arXiv DOI."""
    counts = {}
    for i, pid in enumerate(sorted(ids), 1):
        work = get_json("/works/doi:10.48550/arXiv." + pid, {"select": "id,cited_by_count"}, key)
        if work and work.get("cited_by_count"):
            counts[pid] = work["cited_by_count"]
        if i % 500 == 0:
            print(f"    arXiv: {i} of {len(ids)} looked up", file=sys.stderr)
        time.sleep(0.12)
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="data", type=pathlib.Path)
    ap.add_argument("--skip-eprint", action="store_true")
    ap.add_argument("--skip-arxiv", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    out_path = args.data_dir / "citations.json"
    try:
        result = json.loads(out_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        result = {}

    for source, fetch in (("eprint", fetch_eprint), ("arxiv", fetch_arxiv)):
        if getattr(args, f"skip_{source}"):
            continue
        if source == "eprint" and not key:
            sys.exit("ePrint citations need OPENALEX_API_KEY (paging through results requires a key).")
        ids = list(scrape.load_store(args.data_dir / source))
        print(f"OpenAlex citations for {len(ids)} {source} papers...", file=sys.stderr)
        counts = fetch(ids, key)
        result[source] = dict(sorted(counts.items()))
        print(f"  {source}: {len(counts)} papers have citations", file=sys.stderr)

    result["updated"] = dt.date.today().isoformat()
    result["source"] = "OpenAlex"
    ordered = {k: result[k] for k in ("updated", "source", "eprint", "arxiv") if k in result}
    out_path.write_text(json.dumps(ordered, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
