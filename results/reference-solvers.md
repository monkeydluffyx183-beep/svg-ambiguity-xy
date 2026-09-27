# xybench report

corpus `9344ea07056f` · 180 cases · 30 charts (clusters) · random-selection reference 0.1944 · CI = cluster bootstrap 95 %

## Arms

| variant | condition | solver / model | n | identification (exclusive) | inclusive | strict | NO_EDIT | ABSTAINED | REFUSED_PROSE | MALFORMED | multi-edit |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| masked | baseline | random | 180 | 0.1611 [0.1167, 0.2111] | 0.1611 | 0.1611 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| masked | enhanced | oracle | 180 | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| masked | enhanced | random | 180 | 0.1611 [0.1167, 0.2111] | 0.1611 | 0.1611 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| masked | permuted | random | 180 | 0.1611 [0.1167, 0.2111] | 0.1611 | 0.1611 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| real | baseline | first | 180 | 0.2444 [0.1944, 0.2944] | 0.2444 | 0.2444 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| real | baseline | random | 180 | 0.1611 [0.1167, 0.2111] | 0.1611 | 0.1611 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| real | enhanced | random | 180 | 0.1611 [0.1167, 0.2111] | 0.1611 | 0.1611 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| real | permuted | random | 180 | 0.1611 [0.1167, 0.2111] | 0.1611 | 0.1611 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## Pairwise differences (identification, exclusive) — paired cluster permutation

| variant | solver / model | comparison | difference | p | MDE | note |
|---|---|---|---:|---:|---:|---|
| masked | random | enhanced − permuted | +0.0000 | 1.000 | 0.0949 | MDE from unpaired SE (arms identical in every chart) |
| masked | random | permuted − baseline | +0.0000 | 1.000 | 0.0949 | MDE from unpaired SE (arms identical in every chart) |
| masked | random | enhanced − baseline | +0.0000 | 1.000 | 0.0949 | MDE from unpaired SE (arms identical in every chart) |
| real | random | enhanced − permuted | +0.0000 | 1.000 | 0.0949 | MDE from unpaired SE (arms identical in every chart) |
| real | random | permuted − baseline | +0.0000 | 1.000 | 0.0949 | MDE from unpaired SE (arms identical in every chart) |
| real | random | enhanced − baseline | +0.0000 | 1.000 | 0.0949 | MDE from unpaired SE (arms identical in every chart) |

## Cross-variant differences (real − masked), same condition and solver

| condition | solver / model | difference | p | MDE |
|---|---|---:|---:|---:|
| baseline | random | +0.0000 | 1.000 | 0.0949 |
| enhanced | random | +0.0000 | 1.000 | 0.0949 |
| permuted | random | +0.0000 | 1.000 | 0.0949 |

## Identification by predicate (exclusive)

| variant | condition | solver / model | leftmost | rightmost | topmost | bottommost | top_left | top_right | bottom_left | bottom_right |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| masked | baseline | random | 0.09 (n=22) | 0.15 (n=20) | 0.21 (n=24) | 0.17 (n=24) | 0.14 (n=21) | 0.23 (n=22) | 0.17 (n=23) | 0.12 (n=24) |
| masked | enhanced | oracle | 1.00 (n=22) | 1.00 (n=20) | 1.00 (n=24) | 1.00 (n=24) | 1.00 (n=21) | 1.00 (n=22) | 1.00 (n=23) | 1.00 (n=24) |
| masked | enhanced | random | 0.09 (n=22) | 0.15 (n=20) | 0.21 (n=24) | 0.17 (n=24) | 0.14 (n=21) | 0.23 (n=22) | 0.17 (n=23) | 0.12 (n=24) |
| masked | permuted | random | 0.09 (n=22) | 0.15 (n=20) | 0.21 (n=24) | 0.17 (n=24) | 0.14 (n=21) | 0.23 (n=22) | 0.17 (n=23) | 0.12 (n=24) |
| real | baseline | first | 0.14 (n=22) | 0.20 (n=20) | 0.38 (n=24) | 0.29 (n=24) | 0.19 (n=21) | 0.36 (n=22) | 0.26 (n=23) | 0.12 (n=24) |
| real | baseline | random | 0.09 (n=22) | 0.15 (n=20) | 0.21 (n=24) | 0.17 (n=24) | 0.14 (n=21) | 0.23 (n=22) | 0.17 (n=23) | 0.12 (n=24) |
| real | enhanced | random | 0.09 (n=22) | 0.15 (n=20) | 0.21 (n=24) | 0.17 (n=24) | 0.14 (n=21) | 0.23 (n=22) | 0.17 (n=23) | 0.12 (n=24) |
| real | permuted | random | 0.09 (n=22) | 0.15 (n=20) | 0.21 (n=24) | 0.17 (n=24) | 0.14 (n=21) | 0.23 (n=22) | 0.17 (n=23) | 0.12 (n=24) |

## Selection-position distribution

Document index of the single edited marker, among responses that edited exactly one. A uniform guess is flat; a fixed policy ('always the first') is a spike at 0 with the same mean.

| variant | condition | solver / model | n single-edit | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| masked | baseline | random | 180 | 0.19 | 0.19 | 0.14 | 0.25 | 0.13 | 0.07 | 0.03 |
| masked | enhanced | oracle | 180 | 0.24 | 0.19 | 0.19 | 0.21 | 0.08 | 0.06 | 0.03 |
| masked | enhanced | random | 180 | 0.19 | 0.19 | 0.14 | 0.25 | 0.13 | 0.07 | 0.03 |
| masked | permuted | random | 180 | 0.19 | 0.19 | 0.14 | 0.25 | 0.13 | 0.07 | 0.03 |
| real | baseline | first | 180 | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| real | baseline | random | 180 | 0.19 | 0.19 | 0.14 | 0.25 | 0.13 | 0.07 | 0.03 |
| real | enhanced | random | 180 | 0.19 | 0.19 | 0.14 | 0.25 | 0.13 | 0.07 | 0.03 |
| real | permuted | random | 180 | 0.19 | 0.19 | 0.14 | 0.25 | 0.13 | 0.07 | 0.03 |
