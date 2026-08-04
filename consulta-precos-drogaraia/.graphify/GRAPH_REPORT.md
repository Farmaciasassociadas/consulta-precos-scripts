# Graph Report - .  (2026-07-29)

## Corpus Check
- Corpus is ~3.012 words - fits in a single context window. You may not need a graph.

## Summary
- 35 nodes · 35 edges · 2 communities detected
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output
- Edge kinds: contains: 34 · calls: 1


## Input Scope
- Requested: auto
- Resolved: committed (source: default-auto)
- Included files: 3 · Candidates: 4
- Excluded: 0 untracked · 0 ignored · 0 sensitive · 0 missing committed
- Recommendation: Use --scope all or graphify.yaml inputs.corpus for a knowledge-base folder.

## Graph Freshness
- Built from Git commit: `9376b08`
- Compare this hash to `git rev-parse HEAD` before trusting freshness-sensitive graph output.
## God Nodes (most connected - your core abstractions)
1. `money()` - 2 edges
2. `priceCell()` - 2 edges
3. `PHARMACIES` - 1 edges
4. `PRODUCTS` - 1 edges
5. `STATUS_LABEL` - 1 edges
6. `tbody` - 1 edges
7. `themeToggle` - 1 edges
8. `iconSun` - 1 edges
9. `iconMoon` - 1 edges
10. `savedTheme` - 1 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (24): btnPause, btnStart, btnStop, chipRow, collectDot, collectState, COLUMN_INDEX, emptyState (+16 more)

### Community 1 - "Community 1"
Cohesion: 1.00
Nodes (2): money(), priceCell()

## Knowledge Gaps
- **24 isolated node(s):** `PHARMACIES`, `PRODUCTS`, `STATUS_LABEL`, `tbody`, `themeToggle` (+19 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 1`** (2 nodes): `money()`, `priceCell()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `PHARMACIES`, `PRODUCTS`, `STATUS_LABEL` to the rest of the system?**
  _24 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06060606060606061 - nodes in this community are weakly interconnected._