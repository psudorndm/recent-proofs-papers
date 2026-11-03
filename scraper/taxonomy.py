#!/usr/bin/env python3
"""Load, check and apply the topic hierarchy in taxonomy.toml.

    python3 scraper/taxonomy.py --check    # validate the file and show how many
                                           # stored papers each topic gets

A paper's topics are stored as the deepest matching paths, comma-separated,
e.g. "proofs/pcs/lattice,proofs/snark,security". Every prefix of a path is
implied (proofs/pcs/lattice means proofs and proofs/pcs too).
"""

import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAXONOMY_FILE = ROOT / "taxonomy.toml"

ATTRIBUTES = {"label", "keywords", "case_sensitive", "requires_keywords",
              "requires_case_sensitive", "subgroups", "arxiv_terms", "tag_only"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_DEPTH = 8


class TaxonomyError(Exception):
    pass


class Node:
    def __init__(self, path, label, patterns, requires, children, arxiv_terms, tag_only):
        self.path = path            # e.g. "proofs/pcs/lattice"
        self.label = label
        self.arxiv_terms = arxiv_terms
        self.tag_only = tag_only    # only tags papers that another topic keeps
        self.patterns = patterns
        self.requires = requires
        self.children = children

    def matches(self, text):
        if not any(p.search(text) for p in self.patterns):
            return False
        return not self.requires or any(p.search(text) for p in self.requires)


def _patterns(where, table, key, flags):
    values = table.get(key, [])
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise TaxonomyError(f"{where}: '{key}' must be a list of strings in quotes")
    out = []
    for v in values:
        try:
            out.append(re.compile(v, flags))
        except re.error as e:
            raise TaxonomyError(f"{where}: '{key}' has an invalid pattern {v!r} ({e})") from None
        if out[-1].search(""):
            raise TaxonomyError(f"{where}: '{key}' pattern {v!r} matches empty text, so it would match every paper")
    return out


def _build(node_id, table, parent_path, shared, depth):
    path = f"{parent_path}/{node_id}" if parent_path else node_id
    where = f"[topics.{path.replace('/', '.')}]"
    if depth > MAX_DEPTH:
        raise TaxonomyError(f"{where}: nested more than {MAX_DEPTH} levels (is a shared group including itself?)")
    if not ID_RE.match(node_id):
        raise TaxonomyError(f"{where}: id '{node_id}' must use lowercase letters, digits and dashes only")
    for key, value in table.items():
        if not isinstance(value, dict) and key not in ATTRIBUTES:
            raise TaxonomyError(f"{where}: unknown setting '{key}' (allowed: {', '.join(sorted(ATTRIBUTES))})")
    label = table.get("label")
    if not isinstance(label, str) or not label.strip():
        raise TaxonomyError(f"{where}: needs a label, e.g. label = \"my topic\"")
    patterns = (_patterns(where, table, "keywords", re.IGNORECASE) +
                _patterns(where, table, "case_sensitive", 0))
    if not patterns:
        raise TaxonomyError(f"{where}: needs at least one entry in keywords or case_sensitive")
    requires = (_patterns(where, table, "requires_keywords", re.IGNORECASE) +
                _patterns(where, table, "requires_case_sensitive", 0))
    terms = table.get("arxiv_terms", [])
    if terms and depth > 1:
        raise TaxonomyError(f"{where}: arxiv_terms only works on top-level topics")
    if not isinstance(terms, list) or not all(isinstance(t, str) and t.strip() and '"' not in t for t in terms):
        raise TaxonomyError(f"{where}: arxiv_terms must be a list of phrases (without double quotes inside)")
    tag_only = table.get("tag_only", False)
    if not isinstance(tag_only, bool):
        raise TaxonomyError(f"{where}: tag_only must be true or false")
    if tag_only and depth > 1:
        raise TaxonomyError(f"{where}: tag_only only works on top-level topics")

    children = [(k, v) for k, v in table.items() if isinstance(v, dict)]
    groups = table.get("subgroups", [])
    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
        raise TaxonomyError(f"{where}: 'subgroups' must be a list of names, e.g. [\"assumptions\"]")
    for g in groups:
        if g not in shared:
            raise TaxonomyError(f"{where}: subgroup '{g}' is not defined (add a [shared.{g}.<id>] table)")
        children += list(shared[g].items())
    seen = set()
    nodes = []
    for child_id, child in children:
        if child_id in seen:
            raise TaxonomyError(f"{where}: sub-topic id '{child_id}' is used twice")
        seen.add(child_id)
        nodes.append(_build(child_id, child, path, shared, depth + 1))
    return Node(path, label.strip(), patterns, requires, nodes, [t.strip() for t in terms], tag_only)


def load(path=TAXONOMY_FILE):
    """Parse and check the taxonomy; returns the list of top-level nodes."""
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise TaxonomyError(f"{path.name} is not valid TOML: {e}") from None
    extra = set(data) - {"topics", "shared"}
    if extra:
        raise TaxonomyError(f"unexpected top-level section(s): {', '.join(sorted(extra))} "
                            "(use [topics.<id>] or [shared.<group>.<id>])")
    topics = data.get("topics", {})
    shared = data.get("shared", {})
    if not topics:
        raise TaxonomyError("no topics defined (add a [topics.<id>] table)")
    for g, entries in shared.items():
        if not all(isinstance(v, dict) for v in entries.values()):
            raise TaxonomyError(f"[shared.{g}]: put each entry in its own table, e.g. [shared.{g}.<id>]")
    roots = [_build(k, v, "", shared, 1) for k, v in topics.items()]
    if all(r.tag_only for r in roots):
        raise TaxonomyError("every top-level topic is tag_only, so no paper would be kept")
    return roots


def classify(roots, text):
    """Deepest matching topic paths for this text (empty set: no topic).
    tag_only topics are added only when some other topic matched."""
    found = set()

    def walk(node):
        if not node.matches(text):
            return False
        deeper = False
        for child in node.children:
            deeper = walk(child) or deeper
        if not deeper:
            found.add(node.path)
        return True

    for root in roots:
        if not root.tag_only:
            walk(root)
    if found:
        for root in roots:
            if root.tag_only:
                walk(root)
    return found


def export(roots):
    """The hierarchy without patterns, for the web page."""
    def node(n):
        out = {"id": n.path.rsplit("/", 1)[-1], "label": n.label}
        if n.children:
            out["children"] = [node(c) for c in n.children]
        return out
    return [node(r) for r in roots]


def _print_counts(roots):
    """Show how many stored papers each topic would get."""
    sys.path.insert(0, str(ROOT / "scraper"))
    import scrape  # noqa: E402 - only needed for the check

    data_dir = ROOT / "data"
    counts, total, untagged, no_abstract = {}, 0, 0, 0
    for source in scrape.SOURCES:
        for p in scrape.load_store(data_dir / source).values():
            total += 1
            abstract = scrape.read_abstract(data_dir, source, p["id"])
            if abstract is None:
                no_abstract += 1
                continue
            paths = classify(roots, p["title"] + " " + abstract)
            if not paths:
                untagged += 1
            implied = {"/".join(path.split("/")[:i + 1]) for path in paths
                       for i in range(path.count("/") + 1)}
            for path in implied:
                counts[path] = counts.get(path, 0) + 1

    def show(n, depth):
        print(f"  {'  ' * depth}{n.label:<{34 - 2 * depth}} {counts.get(n.path, 0):>6}")
        for c in n.children:
            show(c, depth + 1)

    print(f"\nstored papers: {total}")
    for r in roots:
        show(r, 0)
    if untagged:
        print(f"\n{untagged} stored papers would match no topic and be dropped on the next update.")
    if no_abstract:
        print(f"{no_abstract} stored papers have no abstract yet and keep their current topics.")


def main():
    if sys.argv[1:] != ["--check"]:
        print(__doc__)
        sys.exit(2)
    try:
        roots = load()
    except TaxonomyError as e:
        print(f"taxonomy.toml: {e}", file=sys.stderr)
        sys.exit(1)
    print("taxonomy.toml is valid.")
    _print_counts(roots)


if __name__ == "__main__":
    main()
