# Contributing to the topic hierarchy

The topics on the site, their sub-topics and the keywords that decide which
papers land where all live in one file: [`taxonomy.toml`](taxonomy.toml). You do
not need to touch any code to add or refine a topic.

## Quick start

1. Edit `taxonomy.toml` (on GitHub: open the file, click the pencil icon).
2. Open a pull request. The **check taxonomy** job validates the file and its log
   shows how many stored papers each topic would get.
3. Once merged, the stored papers are re-tagged automatically within a few minutes.

To check locally instead: `python3 scraper/taxonomy.py --check` (Python 3.11+).

## Adding a sub-topic

Sub-topics are nested tables. This adds *proof systems › lookup arguments*:

```toml
[topics.proofs.lookups]
label = "lookup arguments"
keywords = ['lookup arguments?', 'lookup tables?']
case_sensitive = ['\bLasso\b', '\bCaulk\b']
```

A sub-topic is only checked for papers that already matched its parent, so its
keywords can be short. Nest further with `[topics.proofs.lookups.<id>]`.

## Reusing a list of sub-topics

Lists that apply in several places (like the assumptions) are written once under
`[shared.<group>.<id>]` and pulled in with `subgroups`:

```toml
[shared.assumptions.isogeny]          # now appears under every topic that has
label = "isogeny-based"               # subgroups = ["assumptions"]
keywords = ['isogen']
```

To give another topic the same list, add `subgroups = ["assumptions"]` inside its
existing table (a table can only appear once in the file).

## Adding a top-level topic

Top-level keywords must be specific on their own, because they decide which papers
are kept at all. Also give it `arxiv_terms`, the phrases the arXiv harvest searches
abstracts for:

```toml
[topics.mpc]
label = "multi-party computation"
keywords = ['multi[- ]?party computation', 'secure computation']
case_sensitive = ['\bMPC\b']
arxiv_terms = ["multi-party computation", "secure computation"]
```

A top-level topic with `tag_only = true` (like *post-quantum*) never adds papers by
itself: it only tags papers that another topic already keeps, so it needs no
`arxiv_terms`.

Only papers already stored are re-tagged automatically. To search the archives for
papers that match the new topic but nothing else, a maintainer runs the
**refresh papers** workflow with **full** ticked (Actions tab).

## Pattern rules

- `keywords` are case-insensitive regular expressions; `case_sensitive` ones match
  exact case (for acronyms and tool names such as `STARK` or `Coq`).
- Write patterns in single quotes (`'...'`) so backslashes need no escaping; use
  `\b` for word boundaries.
- `requires_keywords` / `requires_case_sensitive`: the paper must also match one of
  these (used so formal verification only covers cryptography).
- ids are lowercase letters, digits and dashes. They are part of the stored data, so
  rename them only if you mean to.

## Safety net

If an edit would drop more than 20% of a source's stored papers (for example, a
top-level topic was deleted by mistake), the update stops without writing anything.
If the drop is intended, a maintainer runs the workflow with **allow_drop** ticked.
