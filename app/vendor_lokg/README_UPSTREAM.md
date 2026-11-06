# LOKG-IR

**LOKG-IR: An Open and Lightweight Knowledge Graph for Semantic Image Retrieval**

Reference implementation and reproducibility package for the MIWAI 2026 paper.

LOKG-IR represents each image as a human-readable Markdown + YAML document (an *Open Knowledge
Format*, OKF). Hyperlinks between documents form an **emergent, schema-free knowledge graph** stored
directly in a Git repository — no graph database, no fixed ontology. At query time a lightweight
retrieval controller selects entry points by embedding + entity linking and runs a bounded,
**specificity-aware, hub-avoiding traversal**, scoring candidates with a hybrid of embedding
similarity, entity-linked text overlap, and graph proximity.

On our multi-hop benchmark (VG-Multihop) LOKG-IR is **on par with a Personalized-PageRank graph
database at far lower operational cost** — the contribution is a knowledge-representation paradigm,
not a new search algorithm.

---

## Repository layout

```
lokg-ir/
├── src/
│   ├── vg_multihop.py        # benchmark + baselines + LOKG-IR; ablation / sweep / scaling / multiseed
│   ├── neo4j_graphrag.py     # real Neo4j (GDS Personalized PageRank) baseline
│   └── audit_vg_multihop.py  # ground-truth invariant audit + structural error-mode analysis
├── scripts/
│   ├── reproduce_all.sh      # every command that produces a paper table/figure
│   └── download_vg.sh        # helper to fetch Visual Genome scene graphs + images
├── results/                  # JSON metrics land here (git-ignored except .gitkeep)
├── figures/                  # figure sources
├── requirements.txt
├── CITATION.cff
├── LICENSE
└── README.md
```

> **Note.** If you are the author packaging this release, drop your working
> `vg_multihop.py`, `neo4j_graphrag.py`, and `audit_vg_multihop.py` into `src/` (the exact copies
> that produced the paper's numbers) so the released code reproduces the reported results verbatim.

---

## Installation

Python **3.10–3.13** (CUDA `torch` wheels are not yet published for 3.14).

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# GPU (recommended for real Visual Genome runs), CUDA 12.4 example:
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

A CPU-only machine is enough for the **synthetic** benchmark (no CLIP encoding required).

---

## Quickstart (no data, no GPU)

Runs the ring-structured synthetic benchmark end to end and prints the metric table:

```bash
python src/vg_multihop.py all --synthetic --n-images 3000 --n-queries 800 \
    --paraphrase lexicon --multihop --tune --out results/synthetic_demo
```

---

## Data: Visual Genome

```bash
bash scripts/download_vg.sh            # downloads scene graphs (+ optional images) into ./VG
```

`VG/` should contain the scene-graph JSON and (for CLIP encoding) an `images/` folder. The benchmark
uses Visual Genome's **gold scene-graph annotations** as entity nodes, so link precision on the
benchmark is exact by construction (LLM extraction is only needed to deploy OKF on un-annotated
corpora).

---

## Reproducing the paper

All commands are collected in `scripts/reproduce_all.sh`. Individually:

**Table 1 — main results (5 seeds, Holm–Bonferroni)**
```bash
python src/vg_multihop.py all --vg-dir VG --vg-img-dir VG/images \
    --n-images 5000 --n-queries 2000 --paraphrase wordnet --multihop --tune \
    --seeds 5 --device cuda --batch 32 --out results/main
```

**Table 3 — ablation of scoring components**
```bash
python src/vg_multihop.py all --vg-dir VG --vg-img-dir VG/images \
    --n-images 5000 --n-queries 2000 --paraphrase wordnet --multihop \
    --ablation --seeds 5 --device cuda --out results/ablation
```

**Sensitivity (depth T, hub cutoff, entry size N)**
```bash
python src/vg_multihop.py all --vg-dir VG --vg-img-dir VG/images \
    --n-images 5000 --n-queries 2000 --paraphrase wordnet --multihop \
    --sweep --device cuda --out results/sensitivity
```

**Scalability (latency vs corpus size)**
```bash
python src/vg_multihop.py all --vg-dir VG --paraphrase wordnet --multihop \
    --scaling --scaling-sizes 5000,10000,20000,50000,100000 \
    --n-queries 300 --device cuda --out results/scaling
```

**Ground-truth audit + error-mode analysis**
```bash
python src/audit_vg_multihop.py --vg-dir VG --n-images 5000 --n-queries 2000 \
    --paraphrase wordnet --multihop --seed 0 --sample 100 --out results/audit
```

**Table 4 — real Neo4j graph-database baseline**
Requires a running Neo4j 5.x/2025.x with the **Graph Data Science (GDS)** plugin enabled
(`RETURN gds.version()` should succeed).
```bash
pip install neo4j
python src/neo4j_graphrag.py --vg-dir VG --vg-img-dir VG/images \
    --n-images 5000 --n-queries 2000 --paraphrase wordnet --multihop \
    --uri bolt://localhost:7687 --user neo4j --password YOURPASS --out results/neo4j
# Without GDS, measure real ingest cost only:  add --no-gds
```

Each run writes a JSON file (e.g. `results/main/metrics_multiseed.json`) with means ± sd, the
Holm–Bonferroni outcomes, and per-complexity breakdowns.

---

## Method knobs (defaults match the paper)

`--entry-n 20` (top-N embedding entry) · `--depth 4` (traversal depth T) ·
`--hub-df-frac 0.05` (hub cutoff) · `--bridge-df-frac 0.02` (bridge specificity) ·
`--paraphrase {none,lexicon,wordnet}` (semantic gap) · `--multihop` (bridge/path ground-truth so the
graph term matters) · `--seeds R` (multi-seed + Holm–Bonferroni) · `--tune` (grid-search α,β,γ on a
30% validation split).

---

## Citation

If you use this code or benchmark, please cite:

```bibtex
@inproceedings{lokgir2026,
  title     = {LOKG-IR: A Lightweight, Open Knowledge Graph Framework for Semantic Image Retrieval},
  author    = {<Author, A. and Author, B.>},
  booktitle = {Proceedings of MIWAI},
  year      = {2026},
  publisher = {Springer},
  series    = {LNAI}
}
```

## License

Released under the MIT License — see [LICENSE](LICENSE).
Visual Genome is distributed under its own license by its original authors.
