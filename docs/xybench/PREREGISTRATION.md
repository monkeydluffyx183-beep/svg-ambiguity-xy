# xybench — pre-registration (draft, awaiting the freeze tag)

**Status: written before any model output exists.** No model has been run against this
corpus anywhere: the sandbox that built it has no model, and the only responses ever
generated were by the deterministic solvers in `results/reference-solvers.md`. That claim
is an author assertion in the same three-layer sense upstream spells out — the frozen tree
verifiably contains no model outputs; the tag message will say none were observed; commit
timestamps prove nothing. The freeze becomes binding when the tag below is pushed.

## Frozen identity

| item | value |
|---|---|
| corpus | `data/frozen/9344ea07056f508eb719705ac7c12e1fc5e6a20eaf3966d5c2c6c8709974cc80` |
| corpus config hash | `eb4fdbf5958f0fc77b96480cb47e5c9f5a56e622dc6cb3bd6810092f0ef7ad00` (seed 20260926) |
| generator / XY | `1.0` / `xy==0.0.7` |
| template | `edit_xy_v1` 1.0 — masked `ea243aca0626a4fc…`, real `094432ee797681fc…` |
| scoring / abstention rule | `1.0` / `2.0` |
| permutation | `fmtcontrol_xy` (spec 1.0, Level 2), seed 4093, key = chart id |
| analysis | this document, §Analysis |

`python -m xybench status` prints these from the code; `python -m xybench verify` checks
the corpus certificate.

**Freeze procedure.** `git tag -a xybench-freeze-v1 -m "xybench instrument freeze. NO MODEL
OUTPUTS HAVE BEEN OBSERVED. dataset 9344ea07…"` on the commit that contains this file, then
push the tag. After the tag, changes to the corpus, template, scoring or this analysis plan
are **amendments**: disclosed in the results document, with the pre-change number retained,
and admissible only if they would have been made identically had the arms come out the
other way around (upstream's `RESULTS.md` test).

## Questions

**Q1 (masked — upstream's question, on real markup).** Does supplying marker geometry
improve reference resolution, and if so is the gain information or format?

**Q2 (real — the question this corpus adds).** When coordinates are legible in the source,
do models use them? And does a table that *restates* them change anything?

**Q3 (cross-variant).** What are legible coordinates worth, per condition?

**Q4 (execution).** Can the models perform the edits at all when the target is named?

## Hypotheses

| id | statement | tested by |
|---|---|---|
| H1 | In `masked`, `baseline` identification is at the reference (0.194): the corpus is genuinely under-determined | `baseline` CI contains 0.194 |
| H2 | In `masked`, `enhanced − permuted > 0`: supplied geometry carries an **information** effect | primary comparison |
| H3 | In `masked`, `permuted − baseline` is the **format** component; no directional prediction | secondary |
| H4 | In `real`, `baseline` identification exceeds the reference: models read `cx`/`cy` | `baseline` CI excludes 0.194 from above |
| H5 | `real/baseline − masked/baseline > 0` | cross-variant paired test |
| H6 | `named_id` identification is high (> 0.6) in both variants: execution is not the limit | per-arm CI |

H2 is the hypothesis the format-matched control exists to test. Upstream has run it three
times on four models and never had a positive effect to decompose. This corpus is a
different place to look, not a claim that the answer will differ.

## Primary outcome and comparison

* **Outcome:** exclusive identification accuracy (target marker changed, no other marker
  changed), unconditional on well-formedness. Inclusive identification is reported
  alongside; strict accuracy and all outcome-class rates are secondary.
* **Primary comparison:** paired Δ identification, `enhanced − permuted`, within `masked`,
  pooled over predicates. Everything else is secondary or exploratory and will be labelled
  so.
* **Per-predicate** numbers are reported for every arm; a family average is a summary,
  per-predicate is the finding.

## Analysis

As implemented in `xybench.stats` and `xybench.report`, both frozen with the tag:

* Clusters are charts (30). Intervals: cluster bootstrap, 2000 draws, seed 0, percentile.
* Tests: paired cluster permutation, 10 000 sign flips, seed 0, case-weighted mean of
  per-chart differences.
* MDE = 2.80 × cluster-bootstrap SE of the paired difference; unpaired fallback when the
  arms are identical in every cluster (flagged). **Reported before results**, for each
  comparison, from the arms as run.
* Decoding: temperature 0, seed 0 where the API accepts one, one replicate (upstream
  ADR-0010: replicates at temperature 0 imply a robustness that does not exist).
* Denominators are fixed at 180 per arm; `ABSTAINED`, `REFUSED_PROSE` and `MALFORMED`
  are scored, never dropped.

## Falsifiers and data-quality rules (fixed now)

1. **Instrument falsifier.** If `masked/baseline` identification is *above* 0.30 (its CI
   excludes the reference from above) for any model, the masked corpus leaks position
   somewhere and Q1 is not testable on it. The selection-position table is the first place
   to look.
2. **Data-quality exclusion.** A model is excluded from confirmatory analysis of H2 if
   `MALFORMED` exceeds **20 %** in any of its `masked` arms. Because `REFUSED_PROSE` is a
   separate class under rule 2.0, refusal style cannot trigger this rule — that is the
   FA-013 correction, and it is the reason the threshold can be set lower than upstream's.
3. **Refusal reporting.** `REFUSED_PROSE + ABSTAINED` above **50 %** in an arm does not
   exclude the model, but the arm's identification is then reported *both* unconditionally
   and conditional on a document being returned, and H2 is stated for both.
4. **Policy detection.** If more than 60 % of a model's single-edit responses in an arm fall
   on one document index, the arm is flagged as a fixed policy and its identification is not
   interpreted as evidence about reference resolution in either direction.
5. **Truncation.** Arms with > 10 % truncated responses are re-run once with a larger
   `max_tokens`; if truncation persists, the arm is reported with the rate and excluded from
   H2.

## Models

Not fixed by this document. Whoever runs the instrument records the model name, backend
and options in the experiment manifest (`xybench run` does this), and the results document
lists every model attempted, including any excluded by the rules above.

## What would change our minds

* H2 supported in `masked` and not in `real` would say the information effect exists only
  when the source lacks the information — the expected pattern, and the first time the
  control would have had something to decompose.
* H2 supported in *neither* variant while `named_id` is high would replicate upstream's
  dissociation on real markup: models execute but do not resolve, even with geometry
  legible or supplied.
* H4 false — `real/baseline` at the reference — would say models do not read coordinates
  from attributes at all in this setting, which bounds "context augmentation" claims from
  the other side: the information was present and unused.
* Falsifier 1 firing would say the masking is incomplete and would send the corpus back to
  the generator, not to the results section.
