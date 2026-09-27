# xybench — design

The SVG reference-resolution study of [svg-ambiguity-bench](https://github.com/NITISH-R-G/svg-ambiguity-bench),
rebuilt on **real chart SVGs exported by the [XY](https://github.com/reflex-dev/xy) charting
library**, with the format-matched control supplied by this repository's own
[`fmtcontrol_xy`](../../src/fmtcontrol_xy).

Upstream's own limitations list opens with: *"One synthetic corpus. Opaque geometry tokens
that do not occur in real SVGs."* This instrument addresses that sentence and nothing
else. It keeps upstream's design wherever the design was the point — three arms, one
template, one context slot, identification as the outcome, cluster inference — and
changes it only where real markup forces a change or where a recorded failure (FA-013)
showed the rule was wrong.

## 1. The question, and what real markup does to it

Upstream created its information gap by construction: every `<path d>` was replaced by a
token, so the source text provably did not encode position. XY's exports are the opposite:
a marker is `<circle cx="136.74" cy="157.28" r="3.5" …/>` — position is *in* the text.
"Make the top-left marker blue" is therefore a different task on real markup: not "resolve
a reference the document cannot support" but "read two numbers per element and compare
them".

Rather than choose, the corpus is written in two renderings of the *same* charts:

| variant | what the model sees | question it asks |
|---|---|---|
| `masked` | `cx="{{GEOM_23810120}}" cy="{{GEOM_32405f3c}}"` | upstream's question on real markup: does supplied geometry help, and is it information or format? |
| `real` | `cx="80.23" cy="51.26"` | does the model *use* coordinates that are already in the source, and does restating them in a table change anything? |

Everything else is byte-identical between the variants: ids, order, radius, fill, grid,
ticks, title, the instruction, the context tables, the permutation. The prompt differs in
one preamble sentence (§4). So `real − masked`, per condition, is a clean estimate of what
legible coordinates are worth to a model, on cases it has otherwise seen identically.

## 2. Corpus

30 charts × 6 cases = **180 cases per variant**, one cluster per chart — upstream's shape.

**Charts.** Single-series XY scatter plots, `xy.scatter_chart(xy.scatter(xs, ys, color, size=7))`,
720×480, title "Observations", K ∈ {4, 5, 6, 7} points with coordinates drawn uniformly
from a fixed generator. XY emits one `<circle>` per point in data order with a shared
radius (3.5), fill and opacity: an ambiguity set in which nothing but geometry
distinguishes markers. There are **no distractor series**, so the random-selection
reference is exactly `mean(1/K)` = 0.1944 on this corpus and nothing has to be argued
about which elements a guess ranges over.

**Ids.** XY writes no ids on marks. A deterministic, hash-shaped id (`e` + 8 hex of
SHA-256(seed, chart, index)) is inserted as the first attribute of each marker. Hash-shaped
rather than ordinal so the id carries no position hint. This is the only edit to XY's
output in the `real` variant.

**Masking.** In `masked`, each marker's `cx` and `cy` *values* are replaced by distinct
`{{GEOM_xxxxxxxx}}` tokens (SHA-256 of seed, chart, id, attribute). Attribute names and
every other byte are unchanged; the audit proves `unmask(masked) == real` for every chart.
Gridlines and tick labels keep their coordinates — they do not co-vary with marker
positions, and stripping them would make the document less like an XY export.

**Ground truth** is computed from the *rendered pixel geometry parsed out of the SVG*, not
from the data values that produced it, because the instruction refers to the picture. SVG
`y` grows downward; "topmost" is the smallest `cy`.

**Predicates.** The eight spatial ones: `leftmost`, `rightmost`, `topmost`, `bottommost`
(one-dimensional argmin) and `top_left`, `top_right`, `bottom_left`, `bottom_right`
(Euclidean distance to the corner of the plot area, taken from XY's clipPath rectangle).
Upstream's size family is dropped: all markers share `r`, and making sizes differ would
put the answer to "largest" in the source text of both variants.

**Uniqueness with margin.** A predicate is admitted for a chart only if the best marker
beats the runner-up by ≥ **24 px** on the predicate's score. A chart is accepted only if
≥ 6 of the 8 predicates are admissible; otherwise it is regenerated and the rejection
logged (`rejections.json`: 3 rejections for the frozen corpus). Six predicates are then
chosen with a cap of two cases per target marker, because a corner marker is often also
an extreme.

**Operations.** `recolor_fill` (to one of four colours absent from the palette),
`add_stroke` (2 or 3 px, black or white), `delete`, and `resize` — *double the radius*.
Upstream's `rotate` is meaningless for a circle about its own centre. Each is checkable by
attribute comparison after canonicalisation (§5).

**Instructions.** Two target registers × two operation registers per case (upstream's
CanItEdit argument). A lint rejects any instruction containing a marker id, a token, a
coordinate string present in the document, or the document fill.

**Determinism and provenance.** The corpus directory is named by its dataset hash (SHA-256
over every file's path and hash); `manifest.json` lists every file with its hash, the
config, the generator version and the **XY version**, because the corpus is a function of
XY's serialisation. `xybench verify` checks the certificate; `--regenerate` rebuilds from
the seed and compares hashes. The frozen hash has reproduced on the machine that built it,
on a fresh sandbox, and on GitHub-hosted Ubuntu runners under Python 3.11, 3.12 and 3.13
from a clean `pip install xy==0.0.7` (CI run 36258808572); CI repeats that check on every
push. Tampering with one byte is detected; that is the only sense in which "frozen" is
verifiable from the outside.

## 3. Arms

| condition | context slot | instruction |
|---|---|---|
| `baseline` | empty | descriptive ("the top-left marker") |
| `enhanced` | fixed-width table: `id  centre_x  centre_y`, document order | descriptive |
| `permuted` | the same table with `(cx, cy)` pairs moved between ids by `fmtcontrol_xy.permute(facts, key=chart_id, seed=4093)` | descriptive |
| `named_id` | empty | `the marker with id "e2ee9009d"` — upstream's V2 execution check |

The permutation is keyed by chart id alone, so the same chart receives the same shuffle in
both variants. The permutation seed (4093) is a constant unrelated to the corpus seed
(SPEC I7). `check_control` passes on every chart with a token delta of exactly 0.

The `enhanced` table carries **primitive facts only** — no ranks, no labels — in document
order. Sorting it would be the trap SPEC §6b describes and this repository's example
demonstrates.

## 4. Prompt

One template (`edit_xy_v1`, version 1.0, hashed per variant), one context slot. The audit
asserts that within a variant the arms' prompts differ only inside that slot. The variants
differ in exactly one preamble sentence:

> *masked:* "The cx and cy attributes of every `<circle>` marker have been redacted and replaced with an opaque placeholder such as `{{GEOM_1234abcd}}`. This is intentional. Copy every placeholder through …"
> *real:* "Each `<circle>` marker carries its rendered position in its cx and cy attributes."

Both name `cx`/`cy`, so neither variant has a paragraph the other lacks; the residual
difference is recorded here because it is part of what `real − masked` measures. Prompts
are assembled with `str.replace` on unique placeholders — upstream's template 1.0 rendered
`{{GEOM_…}}` as `{GEOM_…}` because `str.format` collapses braces; a test asserts tokens
reach the prompt verbatim. Prompts are 3.7–6.7 k characters.

## 5. Scoring

Frozen with the corpus (`scoring_version 1.0`, `abstention_rule_version 2.0`).

**Classes.** `CORRECT_STRICT`, `CORRECT_LOOSE`, `WRONG_TARGET`, `NO_EDIT`, `ABSTAINED`,
`MALFORMED` as upstream defines them, plus one:

> **`REFUSED_PROSE`** — no SVG document in the response and no explicit abstention
> signal. Upstream's FA-013: their abstention regexes were calibrated on one model's
> refusal style, so models that declined differently were scored `MALFORMED` and tripped
> a data-quality falsifier. Here the regexes still award `ABSTAINED` (and were widened to
> clarifying-question forms), but their failure to match no longer converts a refusal into
> a parse error. `MALFORMED` is reserved for responses that contain `<svg` and fail to
> parse or to align (≥ 2 marker ids missing).

Precedence: extract the **last** `<svg>…</svg>` block → parse → align markers by id → diff
→ if the requested edit was performed on the target: `CORRECT_STRICT`/`_LOOSE`; else if any
marker changed: `WRONG_TARGET`; else `ABSTAINED` if the signal is present, otherwise
`NO_EDIT`.

**Identification** is reported two ways and both are in every evaluation row:

* **exclusive** — the target marker changed and no other marker did. *Primary here.* This
  is the literal reading of "which element it identified"; a response that edits every
  marker identifies nothing, and upstream's own diagnostic ("mean elements modified, the
  hedging measure") exists because their inclusive definition can be gamed that way.
* **inclusive** — the target changed regardless of collateral. Upstream's primary; kept
  for comparability of *design*, not of numbers (different corpora).

**Canonicalisation.** Colours: `#rgb`, `#rrggbb(aa)`, `rgb()/rgba()`, CSS names →
lowercase hex; `style="fill: …"` declarations are merged into attributes (style wins).
Numbers in `cx cy r stroke-width fill-opacity opacity`: tolerance 1e-6, `px` stripped.
`resize` passes at 0.1 % relative tolerance on `r`.

**Truncation** is recorded from the backend's finish reason (`length` / `max_tokens`)
independently of the class.

## 6. Inference

Cluster = chart. Cluster bootstrap (2000 draws, seeded) for intervals; paired cluster
permutation test (10 000 sign flips) for arm differences; and a **minimum detectable
effect fixed in advance**:

    MDE = (z₀.₉₇₅ + z₀.₈₀) × SE_paired = 2.80 × SE_paired

with `SE_paired` the cluster-bootstrap SE of the paired difference. If the arms are
identical in every chart that SE is 0 and says nothing; the rule then falls back to the
unpaired `sqrt(SE_A² + SE_B²)` and the report says so. Read the MDE, not the p-value, when
the difference is zero.

Reported per arm: exclusive and inclusive identification, strict, `NO_EDIT`, `ABSTAINED`,
`REFUSED_PROSE`, `MALFORMED`, multi-edit rate; per predicate; and the **selection-position
distribution** — the document index of the single edited marker — because a model that
always edits the first marker scores `mean(1/K)` in every arm without guessing at all.
On this corpus that policy scores 0.244 (44 of 180 targets sit at index 0, against 0.194
expected; a 1.7 σ fluctuation of a uniform draw, not a generator bias — the audit checks
it and the report shows the distribution).

## 7. Validation without a model

`xybench audit` runs 23 checks: the integrity certificate; K, ids and files; ground truth
recomputed with margin; instruction lint; masking completeness and `unmask == real`;
`check_control` on every chart; arm prompts differing only in the slot; tokens verbatim;
the target-position distribution; and seven deterministic solvers through the full scorer
in both variants — `oracle` (must be `CORRECT_STRICT` on all 180), `echo` (`NO_EDIT`),
`abstain`, `prose` (`REFUSED_PROSE`), `truncated` (`MALFORMED`), `random` and `first`
(≈ reference). `results/audit.txt` and `results/reference-solvers.md` are the outputs at
freeze.

## 8. What differs from upstream, in one table

| | upstream (svg-ambiguity-bench) | xybench |
|---|---|---|
| markup | synthetic `<path>`s, opaque `d` tokens | XY exports, `<circle>` markers; `masked` and `real` renderings |
| ambiguity set | K ∈ 4..7 same-fill among distractors | K ∈ 4..7, single series, no distractors |
| predicates | 12 (spatial + size) | 8 (spatial); size family not an information gap here |
| operations | recolor, stroke, delete, rotate | recolor, stroke, delete, **resize** |
| facts in context | centroid x, y, area | centre x, y |
| abstention rule | regex only (1.0) | regex + `REFUSED_PROSE` (2.0) |
| primary metric | inclusive identification | **exclusive** identification (inclusive reported) |
| MDE | their formula | fixed here, §6 |
| control | `fmtcontrol` (reference) | `fmtcontrol_xy` (this repo's clean-room implementation, Level 2 conformant) |

## 9. Threats specific to this instrument

1. **XY version drift.** The corpus is a function of XY 0.0.7's serialiser. A later XY may
   change decimal formatting, attribute order or structure and the seed will no longer
   reproduce the hash. The manifest records the version; `pyproject` pins it; the hash, not
   the seed, is the identity of the frozen corpus.
2. **Inserted ids.** Real XY output has no marker ids; the scorer needs them. `named_id`
   and the structural diff both depend on this edit, which real-world users of XY would not
   have. A pure-XY setting would need alignment by position instead.
3. **Single mark type.** Only circles. Bars, lines and areas render differently and are not
   covered; the instrument says nothing about them.
4. **The `real/permuted` arm contradicts the source.** In `real`, the table's numbers
   disagree with the `cx`/`cy` a model can read. That is the open condition C4 in SPEC §6a:
   a model may be actively misled rather than merely uninformed. It is a feature of the
   design — the point of the variant is to see whether models use what the source says —
   but the contrast in `real` should be read with it in mind.
5. **Preamble sentence.** One sentence differs between variants (§4). It is small, it names
   the same attributes, and it is unavoidable, but it is not nothing.
6. **Target-position share at index 0 is 0.244**, above the 0.194 reference by chance. It
   cancels in within-variant arm differences, which are paired, and it is visible in the
   selection-position table for any solver that exploits it.
7. **Lenient parsing.** The scorer uses the standard-library XML parser; models emitting
   HTML-ish SVG (unclosed tags, unquoted attributes) will be `MALFORMED` even when a
   browser would render them. Upstream had the same property.
8. **Colour names.** Only common CSS names are canonicalised. An exotic name for an edit
   colour would score as a wrong edit on the right target — visible as `WRONG_TARGET` with
   `identified = true`.

## 10. What this cannot show

The same list as upstream's §9, with one change: item 2 ("nothing about real-world SVG
editing — opaque `d` tokens do not occur in the wild") is replaced by "nothing about
markup other than XY scatter exports". The rest stand: nothing about models in general,
nothing about generality beyond these predicates, nothing about whether an LLM is the
right tool (the `oracle` solver scores 1.0 in 0.1 s), and corpus difficulty is filtered by
the 24 px margin.
