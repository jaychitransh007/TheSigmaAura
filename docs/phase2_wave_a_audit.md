# Phase 2 Wave A — Ontology-Surgery Audit

Generated: `2026-05-11 06:08 UTC` against `catalog_enriched` (N = 14,242 rows).

Each Wave A surgical PR should link this report as its evidence — no cut ships unless the data here supports the OPEN_TASKS claim for that axis. Wave B (4 deferred ShapeArchitecture axes) is gated separately on Phase 4.6 eval data, not this report.


## 1. Redundancy correlations

For each `(candidate_for_removal, claimed_redundant_with)` pair, we compute the conditional-entropy ratio H(B|A) / H(B): how much knowing A's value reduces uncertainty about B. **Lower = more redundant**. `dominant_pair_ratio` is the share of populated rows covered by the single most-common (A, B) value combination — near 1 means A nearly determines B.

**Surgical-decision rule of thumb**: entropy_ratio < 0.35 OR dominant_pair_ratio > 0.70 → strong support for removing the candidate. Between those bounds → review the top_pairs to see whether the residual signal is meaningful.

| Candidate | Kept | non-null N | distinct pairs | dominant pair ratio | entropy ratio H(B\|A)/H(B) | Surgical-decision |
|---|---|---:|---:|---:|---:|---|
| `FitEase` | `FitType` | 12,869 | 14 | 0.592 | 0.359 | ⚠️ Review |
| `SilhouetteContour` | `SilhouetteType` | 12,733 | 63 | 0.340 | 0.449 | ⚠️ Review |
| `VolumeProfile` | `VolumePlacement` | 13,306 | 31 | 0.581 | 0.845 | ❌ Keep |
| `HipDefinition` | `WaistDefinition` | 13,068 | 27 | 0.389 | 0.885 | ❌ Keep |

### Top value-pairs per redundancy candidate

#### `FitEase` × `FitType`

| Pair | Count | Share |
|---|---:|---:|
| `regular` → `regular` | 7,614 | 59.2% |
| `relaxed` → `relaxed` | 1,742 | 13.5% |
| `relaxed` → `loose` | 1,011 | 7.9% |
| `slim` → `slim` | 859 | 6.7% |
| `regular` → `tailored` | 809 | 6.3% |
| `slim` → `tailored` | 501 | 3.9% |
| `oversized` → `loose` | 227 | 1.8% |
| `oversized` → `boxy` | 67 | 0.5% |
| `relaxed` → `boxy` | 21 | 0.2% |
| `relaxed` → `tailored` | 5 | 0.0% |

#### `SilhouetteContour` × `SilhouetteType`

| Pair | Count | Share |
|---|---:|---:|
| `straight` → `straight` | 4,329 | 34.0% |
| `straight` → `relaxed` | 1,786 | 14.0% |
| `a_line` → `a_line` | 1,259 | 9.9% |
| `flared` → `flared` | 1,092 | 8.6% |
| `box` → `boxy` | 639 | 5.0% |
| `fitted` → `fitted` | 611 | 4.8% |
| `tapered` → `tapered` | 601 | 4.7% |
| `straight` → `fitted` | 380 | 3.0% |
| `straight` → `relaxed_tailored` | 371 | 2.9% |
| `wrap` → `wrap` | 208 | 1.6% |

#### `VolumeProfile` × `VolumePlacement`

| Pair | Count | Share |
|---|---:|---:|
| `moderate` → `none` | 7,734 | 58.1% |
| `moderate` → `hem` | 1,430 | 10.7% |
| `voluminous` → `hem` | 1,067 | 8.0% |
| `flat` → `none` | 639 | 4.8% |
| `moderate` → `global` | 505 | 3.8% |
| `voluminous` → `global` | 443 | 3.3% |
| `moderate` → `back` | 360 | 2.7% |
| `moderate` → `hip` | 270 | 2.0% |
| `moderate` → `waist` | 231 | 1.7% |
| `moderate` → `sleeve` | 191 | 1.4% |

#### `HipDefinition` × `WaistDefinition`

| Pair | Count | Share |
|---|---:|---:|
| `undefined` → `undefined` | 5,079 | 38.9% |
| `undefined` → `natural` | 1,402 | 10.7% |
| `shaped` → `natural` | 1,129 | 8.6% |
| `undefined` → `defined` | 1,008 | 7.7% |
| `undefined` → `cinched` | 828 | 6.3% |
| `shaped` → `defined` | 782 | 6.0% |
| `flared` → `defined` | 659 | 5.0% |
| `flared` → `empire` | 312 | 2.4% |
| `undefined` → `empire` | 257 | 2.0% |
| `flared` → `cinched` | 250 | 1.9% |


## 2. Vision-extractability per candidate axis

For each axis OPEN_TASKS proposes removing on extractability grounds, the null rate and the confidence distribution on non-null values. **High null rate (>30%) AND/OR low p10 confidence (<0.55) supports removal**: the vision model wasn't able to commit to an answer for many rows, suggesting the signal isn't reliably visible.

| Axis | null rate | confidence mean | median | p10 | distinct values | Surgical-decision |
|---|---:|---:|---:|---:|---:|---|
| `StretchLevel` | 0.0% | 0.865 | 0.900 | 0.700 | 4 | ❌ Keep |
| `OccasionFit` | 0.0% | 0.800 | 0.800 | 0.700 | 11 | ❌ Keep |
| `OccasionSignal` | 0.0% | 0.789 | 0.800 | 0.600 | 7 | ⚠️ Review |

### Top values per extractability candidate

#### `StretchLevel` (top values across 14,239 non-null rows)

| Value | Count | Share of populated |
|---|---:|---:|
| `none` | 12,316 | 86.5% |
| `moderate` | 1,034 | 7.3% |
| `low` | 805 | 5.7% |
| `high` | 84 | 0.6% |

#### `OccasionFit` (top values across 14,241 non-null rows)

| Value | Count | Share of populated |
|---|---:|---:|
| `festive` | 5,479 | 38.5% |
| `casual` | 3,696 | 26.0% |
| `smart_casual` | 2,549 | 17.9% |
| `traditional` | 1,080 | 7.6% |
| `very_casual` | 458 | 3.2% |
| `party` | 433 | 3.0% |
| `workwear` | 303 | 2.1% |
| `semi_formal` | 115 | 0.8% |
| `active` | 58 | 0.4% |
| `travel` | 40 | 0.3% |

#### `OccasionSignal` (top values across 14,241 non-null rows)

| Value | Count | Share of populated |
|---|---:|---:|
| `festive` | 6,358 | 44.6% |
| `daily` | 5,965 | 41.9% |
| `office` | 1,151 | 8.1% |
| `party` | 486 | 3.4% |
| `evening` | 177 | 1.2% |
| `athletic` | 58 | 0.4% |
| `travel` | 46 | 0.3% |


## 3. Code / YAML / SQL consumers per axis

Each candidate axis's downstream consumers (first 80 hits from `git grep`). Before any surgical PR, every reference must be either removed (drop site) or migrated to the kept axis (derive-from site). A short consumer list = a safer cut; a long one signals that the cleanup PR will be wider than it looks.


### `FitEase` (55 hits)

```
knowledge/style_graph/body_frame/female.yaml:23:      FitEase:             [regular, slim]
knowledge/style_graph/body_frame/female.yaml:34:      FitEase:             [oversized]
knowledge/style_graph/body_frame/female.yaml:395:      FitEase:             [regular, slim]                # at sleeves
knowledge/style_graph/body_frame/female.yaml:404:      FitEase:             [regular]
knowledge/style_graph/body_frame/female.yaml:411:      FitEase:             [relaxed]                      # at sleeve
knowledge/style_graph/body_frame/female.yaml:416:      FitEase:             [slim]                         # at sleeve
knowledge/style_graph/body_frame/male.yaml:20:      FitEase:             [regular, slim]
knowledge/style_graph/body_frame/male.yaml:28:      FitEase:             [oversized]
knowledge/style_graph/body_frame/male.yaml:315:      FitEase:             [regular, slim]                 # at sleeve
knowledge/style_graph/body_frame/male.yaml:317:      FitEase:             [oversized]                     # at sleeve — flaps on slim arm
knowledge/style_graph/body_frame/male.yaml:323:      FitEase:             [regular]
knowledge/style_graph/body_frame/male.yaml:330:      FitEase:             [regular, relaxed]              # at sleeve
knowledge/style_graph/body_frame/male.yaml:334:      FitEase:             [slim]                          # at sleeve
knowledge/style_graph/weather.yaml:37:      FitEase:             [regular, relaxed]
modules/agentic_application/src/agentic_application/composition/composer_engine.py:172:        fit_ease=get_str("FitEase"),
modules/agentic_application/src/agentic_application/composition/pairing.py:142:    "FitEase": "fit_ease",
modules/agentic_application/src/agentic_application/composition/render.py:62:    "FitEase",
modules/catalog/src/catalog/enrichment/audit.py:13:    ("FitEase", "FitType"),
modules/catalog/src/catalog/enrichment/audit.py:19:    "FitEase",
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:51:FitEase rules:
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:52:FitEase describes closeness to the body only. It does NOT describe contour shape, silhouette geometry, or volume scale.
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:60:- do not use silhouette terms in FitEase reasoning.
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:330:- FitEase and FitType should agree on body closeness (for example slim aligns with slim/tailored, oversized aligns with loose/boxy when applicable).
modules/catalog/src/catalog/retrieval/document_builder.py:32:    ("SILHOUETTE_AND_FIT", ["SilhouetteContour", "SilhouetteType", "VolumeProfile", "FitEase", "FitType", "ShoulderStructure", "WaistDefinition", "HipDefinition"]),
modules/style_engine/configs/config/garment_attributes.json:102:    "FitEase": [
modules/style_engine/configs/config/tier2_ranked_attributes.json:164:    "FitEase": [],
supabase/migrations/20260312160000_catalog_enriched.sql:20:  "FitEase" text null,
supabase/migrations/20260312160000_catalog_enriched.sql:67:  "FitEase_confidence" double precision null,
tests/eval/eval_set_5x.jsonl:9:{"id": "multi_neckline_fit", "user_message": "A v-neck top, fitted but not tight", "expected_extracted_preferences": {"NecklineType": ["v_neck"], "FitEase": ["fitted", "regular"]}, "notes": "multi-axis: neckline + fit"}
tests/test_agentic_application.py:3232:                            "FitEase": "fitted",
tests/test_catalog_retrieval.py:55:            "FitEase": "Relaxed",
tests/test_catalog_retrieval.py:56:            "FitEase_confidence": "0.82",
tests/test_catalog_search_rerank.py:164:                    "FitEase": "oversized",
tests/test_catalog_search_rerank.py:176:                "FitEase": ["fitted"],
tests/test_observability_5x_4a.py:64:            "PatternType": "abstract", "FitEase": "oversized",
tests/test_observability_5x_4a.py:69:            "PatternType": ["solid"], "FitEase": ["fitted"],
tests/test_observability_5x_4a.py:90:        # 5 violations on a paired tuple via FitEase + 4 other axes.
tests/test_observability_5x_4a.py:109:                "FitEase": frozenset({"fitted"}),
tests/test_open_axis_eval.py:103:            {"NecklineType": ["v_neck"], "FitEase": ["fitted"]},
tests/test_open_axis_eval.py:107:        self.assertEqual(r.missing_axes, ["FitEase"])
tests/test_open_axis_eval.py:127:            # case 1: NecklineType TP, FitEase TP
tests/test_open_axis_eval.py:129:                {"NecklineType": ["v_neck"], "FitEase": ["fitted"]},
tests/test_open_axis_eval.py:130:                {"NecklineType": ["v_neck"], "FitEase": ["fitted"]},
tests/test_open_axis_eval.py:139:            # case 3: NecklineType TP, FitEase FN (under-extraction)
tests/test_open_axis_eval.py:141:                {"NecklineType": ["v_neck"], "FitEase": ["fitted"]},
tests/test_open_axis_eval.py:164:        # FitEase: 1 TP, 0 FP, 1 FN → precision 1.0, recall 0.5
tests/test_open_axis_eval.py:165:        fe = agg.by_axis["FitEase"]
tests/test_user_preferences_end_to_end.py:116:        # User says: "I want fitted, not loose." Use FitEase as the
tests/test_user_preferences_end_to_end.py:123:            plan, {"FitEase": ["fitted", "regular"]},
tests/test_user_preferences_end_to_end.py:126:            self.assertEqual(q.hard_attrs["FitEase"], ["fitted", "regular"])
tests/test_user_preferences_end_to_end.py:130:                PrimaryColor="navy", FitEase="oversized",
tests/test_user_preferences_end_to_end.py:133:                PrimaryColor="navy", FitEase="fitted",
tests/test_user_preferences_end_to_end.py:138:                PrimaryColor="cream", FitEase="oversized",
tests/test_user_preferences_end_to_end.py:141:                PrimaryColor="cream", FitEase="fitted",
tests/test_user_preferences_end_to_end.py:159:        # hard_attr penalty for FitEase violations.
```

### `FitType` (80 hits)

```
knowledge/style_graph/archetype.yaml:34:      FitType:               [tailored, slim, regular]
knowledge/style_graph/archetype.yaml:46:      FitType:               [boxy, loose]
knowledge/style_graph/archetype.yaml:72:      FitType:               [tailored, slim, regular, relaxed]
knowledge/style_graph/archetype.yaml:106:      FitType:               [tailored, slim, regular]
knowledge/style_graph/archetype.yaml:139:      FitType:               [regular, slim, tailored]
knowledge/style_graph/archetype.yaml:171:      FitType:               [tailored, slim]
knowledge/style_graph/archetype.yaml:202:      FitType:               [tailored, slim]
knowledge/style_graph/archetype.yaml:235:      FitType:               [regular, relaxed]
knowledge/style_graph/archetype.yaml:267:      FitType:               [regular, relaxed]
knowledge/style_graph/archetype.yaml:298:      FitType:               [regular, slim, relaxed]
knowledge/style_graph/archetype.yaml:329:      FitType:               [tailored, slim]
knowledge/style_graph/archetype.yaml:339:      FitType:               [regular]
knowledge/style_graph/archetype.yaml:360:      FitType:               [regular, relaxed]
knowledge/style_graph/archetype.yaml:394:      FitType:               [slim, tailored]
knowledge/style_graph/archetype.yaml:455:      FitType:               [tailored, slim, regular]
knowledge/style_graph/archetype.yaml:473:      FitType:               [tailored, slim, regular, relaxed]
knowledge/style_graph/archetype.yaml:505:      FitType:               [regular, relaxed, slim]
knowledge/style_graph/archetype.yaml:522:      FitType:               [tailored, slim, regular]
knowledge/style_graph/archetype.yaml:534:      FitType:               [tailored, slim]
knowledge/style_graph/archetype.yaml:541:      FitType:               [boxy, loose]
knowledge/style_graph/archetype.yaml:636:      FitType:               [slim, regular, relaxed]
knowledge/style_graph/archetype.yaml:647:      FitType:               [tailored, slim, regular]
knowledge/style_graph/archetype.yaml:658:      FitType:               [tailored, slim]
knowledge/style_graph/archetype.yaml:663:      FitType:               []
knowledge/style_graph/archetype.yaml:680:      FitType:               [tailored, slim]
knowledge/style_graph/archetype.yaml:709:      FitType:               [tailored, slim]
knowledge/style_graph/archetype.yaml:719:      FitType:               [slim, regular, relaxed]
knowledge/style_graph/archetype.yaml:729:      FitType:               [regular, relaxed]
knowledge/style_graph/archetype.yaml:741:      FitType:               [regular, relaxed, tailored]
knowledge/style_graph/archetype.yaml:765:      FitType:               [regular, relaxed]
knowledge/style_graph/body_frame/female.yaml:22:      FitType:             [slim, tailored]
knowledge/style_graph/body_frame/female.yaml:33:      FitType:             [boxy, loose]
knowledge/style_graph/body_frame/female.yaml:48:      FitType:             [slim, tailored]              # for tops
knowledge/style_graph/body_frame/female.yaml:62:      FitType:             [boxy]                         # at top — masks shoulders
knowledge/style_graph/body_frame/female.yaml:121:      FitType:             [boxy, loose]
knowledge/style_graph/body_frame/female.yaml:431:      FitType:             [tailored]                     # at bust if too rigid
knowledge/style_graph/body_frame/female.yaml:451:      FitType:             [tailored, slim]
knowledge/style_graph/body_frame/female.yaml:465:      FitType:             [tailored]
knowledge/style_graph/body_frame/female.yaml:479:      FitType:             [slim, tailored]
knowledge/style_graph/body_frame/female.yaml:489:      FitType:             [regular, relaxed]
knowledge/style_graph/body_frame/female.yaml:502:      FitType:             [regular, relaxed]
knowledge/style_graph/body_frame/female.yaml:511:      FitType:             [slim, tailored]
knowledge/style_graph/body_frame/female.yaml:809:      FitType:             [tailored, slim]
knowledge/style_graph/body_frame/female.yaml:817:      FitType:             [slim, tailored, regular]
knowledge/style_graph/body_frame/female.yaml:824:      FitType:             [regular, slim]
knowledge/style_graph/body_frame/female.yaml:831:      FitType:             [regular, relaxed]
knowledge/style_graph/body_frame/female.yaml:842:      FitType:             [relaxed, regular]
knowledge/style_graph/body_frame/female.yaml:847:      FitType:             [slim, tailored]
knowledge/style_graph/body_frame/male.yaml:19:      FitType:             [tailored, slim, regular]
knowledge/style_graph/body_frame/male.yaml:27:      FitType:             [boxy, loose]
knowledge/style_graph/body_frame/male.yaml:41:      FitType:             [tailored, regular]
knowledge/style_graph/body_frame/male.yaml:47:      FitType:             [slim]                          # at bottom — emphasises shoulder
knowledge/style_graph/body_frame/male.yaml:60:      FitType:             [tailored, slim, regular]
knowledge/style_graph/body_frame/male.yaml:92:      FitType:             [slim]                          # at bottom
knowledge/style_graph/body_frame/male.yaml:105:      FitType:             [regular, relaxed]
knowledge/style_graph/body_frame/male.yaml:115:      FitType:             [slim, tailored]                # at midsection
knowledge/style_graph/body_frame/male.yaml:145:      FitType:             [tailored, slim]
knowledge/style_graph/body_frame/male.yaml:157:      FitType:             [regular]                       # at bottom
knowledge/style_graph/body_frame/male.yaml:160:      FitType:             [slim]                          # at bottom
knowledge/style_graph/body_frame/male.yaml:167:      FitType:             [tailored, regular]
knowledge/style_graph/body_frame/male.yaml:175:      FitType:             [tailored, slim, regular]
knowledge/style_graph/body_frame/male.yaml:195:      FitType:             [slim]                          # at bottom
knowledge/style_graph/body_frame/male.yaml:358:      FitType:             [tailored]
knowledge/style_graph/body_frame/male.yaml:362:      FitType:             [slim]                          # at chest if too tight
knowledge/style_graph/body_frame/male.yaml:371:      FitType:             [tailored, regular]
knowledge/style_graph/body_frame/male.yaml:376:      FitType:             [slim]
knowledge/style_graph/body_frame/male.yaml:387:      FitType:             [tailored, slim]
knowledge/style_graph/body_frame/male.yaml:394:      FitType:             [regular]
knowledge/style_graph/body_frame/male.yaml:398:      FitType:             [slim, tailored]                # at midsection
knowledge/style_graph/body_frame/male.yaml:406:      FitType:             [regular, relaxed]
knowledge/style_graph/body_frame/male.yaml:413:      FitType:             [slim, tailored]
knowledge/style_graph/body_frame/male.yaml:688:      FitType:             [tailored, slim]
knowledge/style_graph/body_frame/male.yaml:695:      FitType:             [slim, tailored, regular]
knowledge/style_graph/body_frame/male.yaml:702:      FitType:             [regular, slim]
knowledge/style_graph/body_frame/male.yaml:709:      FitType:             [regular, relaxed]
knowledge/style_graph/body_frame/male.yaml:712:      FitType:             [slim, tailored]                # at midsection
knowledge/style_graph/body_frame/male.yaml:719:      FitType:             [relaxed, regular]
knowledge/style_graph/body_frame/male.yaml:724:      FitType:             [slim, tailored]
knowledge/style_graph/occasion.yaml:140:      FitType:               [tailored, slim]
knowledge/style_graph/occasion.yaml:145:      FitType:               [boxy, loose, relaxed]
```

### `HipDefinition` (18 hits)

```
knowledge/style_graph/body_frame/female.yaml:50:      HipDefinition:       [undefined, flared]            # flow over hips, don't cup
knowledge/style_graph/body_frame/female.yaml:63:      HipDefinition:       [tapered, shaped]              # cups bigger hips
knowledge/style_graph/body_frame/female.yaml:86:      HipDefinition:       [flared, shaped]
knowledge/style_graph/body_frame/female.yaml:111:      HipDefinition:       [shaped, flared]
knowledge/style_graph/body_frame/female.yaml:193:      HipDefinition:       [flared, shaped]
knowledge/style_graph/body_frame/female.yaml:246:      HipDefinition:       [undefined, flared]            # flow over hips
knowledge/style_graph/body_frame/female.yaml:248:      HipDefinition:       [tapered, shaped]
knowledge/style_graph/body_frame/female.yaml:260:      HipDefinition:       [tapered, shaped]
modules/agentic_application/src/agentic_application/composition/engine.py:665:#       WaistDefinition, HipDefinition, BodyFocusZone. Without it
modules/agentic_application/src/agentic_application/composition/render.py:65:    "HipDefinition",
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:270:HipDefinition rules:
modules/catalog/src/catalog/retrieval/document_builder.py:32:    ("SILHOUETTE_AND_FIT", ["SilhouetteContour", "SilhouetteType", "VolumeProfile", "FitEase", "FitType", "ShoulderStructure", "WaistDefinition", "HipDefinition"]),
modules/style_engine/configs/config/garment_attributes.json:169:    "HipDefinition": [
modules/style_engine/configs/config/tier2_ranked_attributes.json:203:    "HipDefinition": [],
supabase/migrations/20260312160000_catalog_enriched.sql:28:  "HipDefinition" text null,
supabase/migrations/20260312160000_catalog_enriched.sql:75:  "HipDefinition_confidence" double precision null,
tests/test_catalog_retrieval.py:63:            "HipDefinition": "Skimming",
tests/test_catalog_retrieval.py:64:            "HipDefinition_confidence": "0.83",
```

### `OccasionFit` (80 hits)

```
knowledge/style_graph/occasion.yaml:38:      OccasionFit:           [smart_casual, workwear, formal]
knowledge/style_graph/occasion.yaml:50:      OccasionFit:           [very_casual, festive, traditional, party, active]
knowledge/style_graph/occasion.yaml:79:      OccasionFit:           [smart_casual, workwear, traditional]
knowledge/style_graph/occasion.yaml:89:      OccasionFit:           [very_casual, festive, party]
knowledge/style_graph/occasion.yaml:108:      OccasionFit:           [casual, smart_casual, workwear]
knowledge/style_graph/occasion.yaml:116:      OccasionFit:           [festive, traditional]
knowledge/style_graph/occasion.yaml:132:      OccasionFit:           [formal, workwear]
knowledge/style_graph/occasion.yaml:143:      OccasionFit:           [casual, very_casual, festive, party]
knowledge/style_graph/occasion.yaml:160:      OccasionFit:           [smart_casual, formal, workwear]
knowledge/style_graph/occasion.yaml:168:      OccasionFit:           [festive, traditional, party]
knowledge/style_graph/occasion.yaml:183:      OccasionFit:           [formal, workwear]
knowledge/style_graph/occasion.yaml:193:      OccasionFit:           [festive, traditional, party, very_casual]
knowledge/style_graph/occasion.yaml:210:      OccasionFit:           [smart_casual, semi_formal, party]
knowledge/style_graph/occasion.yaml:218:      OccasionFit:           [very_casual]
knowledge/style_graph/occasion.yaml:236:      OccasionFit:           [semi_formal, formal]
knowledge/style_graph/occasion.yaml:245:      OccasionFit:           [casual, festive]
knowledge/style_graph/occasion.yaml:266:      OccasionFit:           [casual, smart_casual]
knowledge/style_graph/occasion.yaml:274:      OccasionFit:           [formal, traditional]
knowledge/style_graph/occasion.yaml:289:      OccasionFit:           [casual, smart_casual]
knowledge/style_graph/occasion.yaml:308:      OccasionFit:           [casual]
knowledge/style_graph/occasion.yaml:313:      OccasionFit:           [festive, traditional, party]
knowledge/style_graph/occasion.yaml:324:      OccasionFit:           [very_casual, casual]
knowledge/style_graph/occasion.yaml:340:      OccasionFit:           [travel, casual]
knowledge/style_graph/occasion.yaml:369:      OccasionFit:           [semi_formal, party]
knowledge/style_graph/occasion.yaml:378:      OccasionFit:           [casual, very_casual]
knowledge/style_graph/occasion.yaml:393:      OccasionFit:           [smart_casual, semi_formal, party]
knowledge/style_graph/occasion.yaml:401:      OccasionFit:           [formal, traditional]
knowledge/style_graph/occasion.yaml:416:      OccasionFit:           [smart_casual, semi_formal]
knowledge/style_graph/occasion.yaml:424:      OccasionFit:           [very_casual, festive]
knowledge/style_graph/occasion.yaml:437:      OccasionFit:           [semi_formal, formal]
knowledge/style_graph/occasion.yaml:446:      OccasionFit:           [casual, very_casual]
knowledge/style_graph/occasion.yaml:466:      OccasionFit:           [formal, festive, party]
knowledge/style_graph/occasion.yaml:476:      OccasionFit:           [casual, smart_casual, very_casual]
knowledge/style_graph/occasion.yaml:491:      OccasionFit:           [formal, festive]
knowledge/style_graph/occasion.yaml:516:      OccasionFit:           [festive, traditional, formal]
knowledge/style_graph/occasion.yaml:528:      OccasionFit:           [casual, very_casual, workwear]
knowledge/style_graph/occasion.yaml:545:      OccasionFit:           [traditional, festive]
knowledge/style_graph/occasion.yaml:556:      OccasionFit:           [casual, workwear]
knowledge/style_graph/occasion.yaml:574:      OccasionFit:           [festive, traditional]
knowledge/style_graph/occasion.yaml:583:      OccasionFit:           [casual, workwear]
knowledge/style_graph/occasion.yaml:600:      OccasionFit:           [casual, festive]
knowledge/style_graph/occasion.yaml:610:      OccasionFit:           [formal, traditional]
knowledge/style_graph/occasion.yaml:627:      OccasionFit:           [festive, traditional, smart_casual]
knowledge/style_graph/occasion.yaml:635:      OccasionFit:           [casual, very_casual, party]
knowledge/style_graph/occasion.yaml:649:      OccasionFit:           [traditional, festive, formal]
knowledge/style_graph/occasion.yaml:657:      OccasionFit:           [casual, very_casual, workwear]
knowledge/style_graph/occasion.yaml:672:      OccasionFit:           [smart_casual, semi_formal, festive]
knowledge/style_graph/occasion.yaml:693:      OccasionFit:           [traditional, festive]
knowledge/style_graph/occasion.yaml:697:      OccasionFit:           [casual, very_casual]
knowledge/style_graph/occasion.yaml:709:      OccasionFit:           [traditional, festive, smart_casual]
knowledge/style_graph/occasion.yaml:713:      OccasionFit:           [casual]
knowledge/style_graph/occasion.yaml:731:      OccasionFit:           [smart_casual, semi_formal, traditional]
knowledge/style_graph/occasion.yaml:754:      OccasionFit:           [traditional, festive]
knowledge/style_graph/occasion.yaml:765:      OccasionFit:           [casual, workwear]
knowledge/style_graph/occasion.yaml:779:      OccasionFit:           [traditional, festive]
knowledge/style_graph/occasion.yaml:803:      OccasionFit:           [traditional, festive]
knowledge/style_graph/occasion.yaml:828:      OccasionFit:           [festive, traditional, party]
knowledge/style_graph/occasion.yaml:839:      OccasionFit:           [casual, workwear]
knowledge/style_graph/occasion.yaml:856:      OccasionFit:           [traditional, festive]
knowledge/style_graph/occasion.yaml:866:      OccasionFit:           [casual, workwear]
knowledge/style_graph/occasion.yaml:882:      OccasionFit:           [traditional, festive]
knowledge/style_graph/occasion.yaml:909:      OccasionFit:           [festive, traditional, formal, party]
knowledge/style_graph/occasion.yaml:940:      OccasionFit:           [smart_casual, semi_formal]
knowledge/style_graph/occasion.yaml:947:      OccasionFit:           [festive]                       # festive too much for first impression; traditional kept available for intentional Indo-Western fusion
knowledge/style_graph/occasion.yaml:964:      OccasionFit:           [smart_casual, semi_formal, party]
knowledge/style_graph/occasion.yaml:971:      OccasionFit:           [traditional]
knowledge/style_graph/occasion.yaml:984:      OccasionFit:           [semi_formal, formal]
knowledge/style_graph/occasion.yaml:991:      OccasionFit:           [casual, very_casual]
knowledge/style_graph/occasion.yaml:1008:      OccasionFit:           [casual, very_casual, travel]
knowledge/style_graph/occasion.yaml:1017:      OccasionFit:           [formal, traditional, festive]
knowledge/style_graph/occasion.yaml:1033:      OccasionFit:           [smart_casual, casual]
knowledge/style_graph/occasion.yaml:1059:      OccasionFit:           [traditional, smart_casual, festive]
knowledge/style_graph/occasion.yaml:1078:      OccasionFit:           [smart_casual, traditional]
knowledge/style_graph/occasion.yaml:1087:      OccasionFit:           [festive, very_casual]         # too eager / too casual
knowledge/style_graph/occasion.yaml:1105:      OccasionFit:           [smart_casual, semi_formal, festive]
knowledge/style_graph/pairing_rules.yaml:629:          OccasionFit: [traditional, festive]
knowledge/style_graph/pairing_rules.yaml:633:          OccasionFit: [casual, smart_casual, workwear, active, travel]
knowledge/style_graph/pairing_rules.yaml:648:          OccasionFit: [traditional, festive, formal]
knowledge/style_graph/pairing_rules.yaml:651:          OccasionFit: [casual, smart_casual, very_casual]
knowledge/style_graph/pairing_rules.yaml:665:          OccasionFit: [traditional, festive]
```

### `OccasionSignal` (52 hits)

```
knowledge/style_graph/occasion.yaml:39:      OccasionSignal:        [office, daily]
knowledge/style_graph/occasion.yaml:80:      OccasionSignal:        [office, daily]
knowledge/style_graph/occasion.yaml:109:      OccasionSignal:        [daily, office]
knowledge/style_graph/occasion.yaml:133:      OccasionSignal:        [office]
knowledge/style_graph/occasion.yaml:161:      OccasionSignal:        [office]
knowledge/style_graph/occasion.yaml:184:      OccasionSignal:        [office]
knowledge/style_graph/occasion.yaml:211:      OccasionSignal:        [evening, party]
knowledge/style_graph/occasion.yaml:237:      OccasionSignal:        [evening]
knowledge/style_graph/occasion.yaml:267:      OccasionSignal:        [daily]
knowledge/style_graph/occasion.yaml:290:      OccasionSignal:        [daily]
knowledge/style_graph/occasion.yaml:341:      OccasionSignal:        [travel]
knowledge/style_graph/occasion.yaml:370:      OccasionSignal:        [evening, party]
knowledge/style_graph/occasion.yaml:394:      OccasionSignal:        [evening]
knowledge/style_graph/occasion.yaml:417:      OccasionSignal:        [evening]
knowledge/style_graph/occasion.yaml:438:      OccasionSignal:        [evening]
knowledge/style_graph/occasion.yaml:517:      OccasionSignal:        [festive, evening]
knowledge/style_graph/occasion.yaml:546:      OccasionSignal:        [festive, evening]
knowledge/style_graph/occasion.yaml:575:      OccasionSignal:        [festive, evening]
knowledge/style_graph/occasion.yaml:601:      OccasionSignal:        [festive, daily]
knowledge/style_graph/occasion.yaml:628:      OccasionSignal:        [festive, daily]
knowledge/style_graph/occasion.yaml:650:      OccasionSignal:        [festive]
knowledge/style_graph/occasion.yaml:673:      OccasionSignal:        [festive, evening]
knowledge/style_graph/occasion.yaml:694:      OccasionSignal:        [festive, daily]
knowledge/style_graph/occasion.yaml:710:      OccasionSignal:        [festive, daily]
knowledge/style_graph/occasion.yaml:732:      OccasionSignal:        [festive, daily]
knowledge/style_graph/occasion.yaml:755:      OccasionSignal:        [festive, evening]
knowledge/style_graph/occasion.yaml:780:      OccasionSignal:        [festive, daily]
knowledge/style_graph/occasion.yaml:804:      OccasionSignal:        [festive, daily]              # daytime — consistent with haldi/raksha_bandhan
knowledge/style_graph/occasion.yaml:829:      OccasionSignal:        [festive, evening, party]
knowledge/style_graph/occasion.yaml:857:      OccasionSignal:        [festive]
knowledge/style_graph/occasion.yaml:883:      OccasionSignal:        [festive]
knowledge/style_graph/occasion.yaml:910:      OccasionSignal:        [festive, evening, party]     # consistent with sangeet
knowledge/style_graph/occasion.yaml:941:      OccasionSignal:        [evening]
knowledge/style_graph/occasion.yaml:1009:      OccasionSignal:        [daily, travel]
knowledge/style_graph/occasion.yaml:1034:      OccasionSignal:        [evening, travel]
knowledge/style_graph/occasion.yaml:1060:      OccasionSignal:        [festive, daily]
knowledge/style_graph/occasion.yaml:1079:      OccasionSignal:        [daily]
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:37:- Semantic / styling attributes (OccasionFit, OccasionSignal, FormalityLevel, FormalitySignalStrength, TimeOfDay) should be inferred primarily from garment construction and styling language visible in the image, NOT from assumed marketing intent or stereotyped categories.
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:294:OccasionSignal rules:
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:333:- OccasionFit should be coherent with OccasionSignal.
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:337:Some attributes are interpretive (for example FormalityLevel, OccasionSignal, StructuralFocus, VerticalWeightBias).
modules/catalog/src/catalog/retrieval/document_builder.py:13:# `OccasionFit`, `OccasionSignal`, `FormalitySignalStrength` are dropped
modules/style_engine/configs/config/garment_attributes.json:387:    "OccasionSignal": [
modules/style_engine/configs/config/intent_policy_v1.json:26:          "OccasionSignal": ["office"],
modules/style_engine/configs/config/intent_policy_v1.json:62:          {"attribute": "OccasionSignal", "values": ["office"], "weight": 0.030},
modules/style_engine/configs/config/intent_policy_v1.json:73:          {"attribute": "OccasionSignal", "values": ["daily"], "weight": -0.020}
modules/style_engine/configs/config/tier1_ranked_attributes.json:14:      "OccasionSignal",
modules/style_engine/configs/config/tier2_ranked_attributes.json:300:    "OccasionSignal": [],
supabase/migrations/20260312160000_catalog_enriched.sql:54:  "OccasionSignal" text null,
supabase/migrations/20260312160000_catalog_enriched.sql:101:  "OccasionSignal_confidence" double precision null,
tests/test_catalog_retrieval.py:127:            "OccasionSignal": "Day Event",
tests/test_catalog_retrieval.py:128:            "OccasionSignal_confidence": "0.8",
```

### `SilhouetteContour` (50 hits)

```
knowledge/style_graph/body_frame/female.yaml:20:      SilhouetteContour:   [fitted, wrap, peplum, mermaid]
knowledge/style_graph/body_frame/female.yaml:31:      SilhouetteContour:   [box]
knowledge/style_graph/body_frame/female.yaml:46:      SilhouetteContour:   [a_line, fitted, wrap, peplum, empire]
knowledge/style_graph/body_frame/female.yaml:60:      SilhouetteContour:   [tapered]
knowledge/style_graph/body_frame/female.yaml:71:      SilhouetteContour:   [mermaid]
knowledge/style_graph/body_frame/female.yaml:82:      SilhouetteContour:   [a_line, flared, empire, asymmetrical]
knowledge/style_graph/body_frame/female.yaml:94:      SilhouetteContour:   [box, peplum]                 # peplum at hip widens
knowledge/style_graph/body_frame/female.yaml:108:      SilhouetteContour:   [peplum, wrap, fitted, a_line, empire]
knowledge/style_graph/body_frame/female.yaml:119:      SilhouetteContour:   [straight, box, tapered]
knowledge/style_graph/body_frame/female.yaml:133:      SilhouetteContour:   [a_line, empire, asymmetrical, flared]
knowledge/style_graph/body_frame/female.yaml:147:      SilhouetteContour:   [fitted, peplum, wrap]         # cinches midsection
knowledge/style_graph/body_frame/female.yaml:163:      SilhouetteContour:   [a_line, empire, asymmetrical]
knowledge/style_graph/body_frame/female.yaml:175:      SilhouetteContour:   [fitted, peplum, mermaid, tapered]
knowledge/style_graph/body_frame/female.yaml:190:      SilhouetteContour:   [a_line, fitted, wrap, flared]
knowledge/style_graph/body_frame/female.yaml:198:      SilhouetteContour:   [box, mermaid]
knowledge/style_graph/body_frame/female.yaml:256:      SilhouetteContour:   [a_line, empire]
knowledge/style_graph/body_frame/female.yaml:503:      SilhouetteContour:   [a_line, empire, asymmetrical]
knowledge/style_graph/body_frame/female.yaml:509:      SilhouetteContour:   [fitted, peplum, mermaid]
knowledge/style_graph/body_frame/female.yaml:843:      SilhouetteContour:   [a_line, empire]
knowledge/style_graph/body_frame/female.yaml:848:      SilhouetteContour:   [fitted, peplum, mermaid]
knowledge/style_graph/body_frame/male.yaml:17:      SilhouetteContour:   [fitted, straight, tapered]
knowledge/style_graph/body_frame/male.yaml:39:      SilhouetteContour:   [fitted, straight]
knowledge/style_graph/body_frame/male.yaml:58:      SilhouetteContour:   [straight, fitted]
knowledge/style_graph/body_frame/male.yaml:91:      SilhouetteContour:   [tapered]                       # cups bigger lower body
knowledge/style_graph/body_frame/male.yaml:103:      SilhouetteContour:   [straight, a_line]
knowledge/style_graph/body_frame/male.yaml:113:      SilhouetteContour:   [fitted, tapered]
knowledge/style_graph/body_frame/male.yaml:125:      SilhouetteContour:   [straight, a_line]
knowledge/style_graph/body_frame/male.yaml:133:      SilhouetteContour:   [fitted]                        # at midsection
knowledge/style_graph/body_frame/male.yaml:144:      SilhouetteContour:   [fitted, tapered]
knowledge/style_graph/body_frame/male.yaml:405:      SilhouetteContour:   [a_line, straight]
knowledge/style_graph/body_frame/male.yaml:411:      SilhouetteContour:   [fitted, tapered]
knowledge/style_graph/body_frame/male.yaml:720:      SilhouetteContour:   [a_line, straight]
knowledge/style_graph/body_frame/male.yaml:725:      SilhouetteContour:   [fitted, tapered]
modules/agentic_application/src/agentic_application/composition/composer_engine.py:173:        silhouette_contour=get_str("SilhouetteContour"),
modules/agentic_application/src/agentic_application/composition/engine.py:663:#     - body_shape: drives FitType, SilhouetteContour,
modules/agentic_application/src/agentic_application/composition/pairing.py:143:    "SilhouetteContour": "silhouette_contour",
modules/agentic_application/src/agentic_application/composition/render.py:11:    - SilhouetteContour: ...
modules/agentic_application/src/agentic_application/composition/render.py:45:    "SilhouetteContour",
modules/catalog/src/catalog/enrichment/audit.py:12:    ("SilhouetteContour", "SilhouetteType"),
modules/catalog/src/catalog/enrichment/audit.py:21:    "SilhouetteContour",
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:107:SilhouetteContour rules:
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:329:- SilhouetteContour and SilhouetteType should describe compatible shape behavior.
modules/catalog/src/catalog/retrieval/document_builder.py:32:    ("SILHOUETTE_AND_FIT", ["SilhouetteContour", "SilhouetteType", "VolumeProfile", "FitEase", "FitType", "ShoulderStructure", "WaistDefinition", "HipDefinition"]),
modules/style_engine/configs/config/garment_attributes.json:65:    "SilhouetteContour": [
modules/style_engine/configs/config/tier2_ranked_attributes.json:153:    "SilhouetteContour": [],
supabase/migrations/20260312160000_catalog_enriched.sql:17:  "SilhouetteContour" text null,
supabase/migrations/20260312160000_catalog_enriched.sql:64:  "SilhouetteContour_confidence" double precision null,
tests/test_catalog_retrieval.py:49:            "SilhouetteContour": "Soft",
tests/test_catalog_retrieval.py:50:            "SilhouetteContour_confidence": "0.54",
tests/test_catalog_retrieval.py:138:        self.assertIn("- SilhouetteContour: Uncertain(Soft) [confidence=0.54]", doc.document_text)
```

### `SilhouetteType` (78 hits)

```
knowledge/style_graph/archetype.yaml:33:      SilhouetteType:        [fitted, straight, a_line, tapered, wrap]
knowledge/style_graph/archetype.yaml:45:      SilhouetteType:        [oversized]
knowledge/style_graph/archetype.yaml:71:      SilhouetteType:        [straight, fitted, a_line, relaxed]
knowledge/style_graph/archetype.yaml:105:      SilhouetteType:        [fitted, straight, relaxed_tailored]
knowledge/style_graph/archetype.yaml:116:      SilhouetteType:        [oversized, peplum, mermaid]
knowledge/style_graph/archetype.yaml:138:      SilhouetteType:        [a_line, wrap, peplum, empire, fitted, flared]
knowledge/style_graph/archetype.yaml:150:      SilhouetteType:        [oversized, boxy]
knowledge/style_graph/archetype.yaml:170:      SilhouetteType:        [fitted, mermaid, peplum, a_line, wrap]
knowledge/style_graph/archetype.yaml:201:      SilhouetteType:        [fitted, oversized, mermaid]
knowledge/style_graph/archetype.yaml:215:      SilhouetteType:        [relaxed]
knowledge/style_graph/archetype.yaml:234:      SilhouetteType:        [relaxed, a_line, oversized, layered]
knowledge/style_graph/archetype.yaml:266:      SilhouetteType:        [relaxed, straight, a_line, wrap]
knowledge/style_graph/archetype.yaml:297:      SilhouetteType:        [relaxed, straight, fitted, a_line]
knowledge/style_graph/archetype.yaml:308:      SilhouetteType:        [mermaid, peplum]
knowledge/style_graph/archetype.yaml:328:      SilhouetteType:        [oversized, mermaid, peplum, sculptural]
knowledge/style_graph/archetype.yaml:338:      SilhouetteType:        [straight, tapered]
knowledge/style_graph/archetype.yaml:359:      SilhouetteType:        [relaxed, oversized, flared, a_line, wrap]
knowledge/style_graph/archetype.yaml:371:      SilhouetteType:        [fitted, straight]
knowledge/style_graph/archetype.yaml:393:      SilhouetteType:        [fitted, tapered, oversized]
knowledge/style_graph/archetype.yaml:405:      SilhouetteType:        [a_line, wrap, peplum, empire]
knowledge/style_graph/archetype.yaml:454:      SilhouetteType:        [fitted, straight, a_line, tapered]
knowledge/style_graph/archetype.yaml:461:      SilhouetteType:        [oversized]
knowledge/style_graph/archetype.yaml:488:      SilhouetteType:        [oversized, mermaid, peplum]
knowledge/style_graph/archetype.yaml:638:      SilhouetteType:        [oversized, mermaid, peplum, fitted, a_line]
knowledge/style_graph/archetype.yaml:742:      SilhouetteType:        [straight, relaxed_tailored, oversized]
knowledge/style_graph/archetype.yaml:756:      SilhouetteType:        [fitted, oversized, sculptural]
knowledge/style_graph/body_frame/female.yaml:21:      SilhouetteType:      [fitted, wrap, mermaid]
knowledge/style_graph/body_frame/female.yaml:32:      SilhouetteType:      [boxy, oversized]
knowledge/style_graph/body_frame/female.yaml:47:      SilhouetteType:      [fitted, a_line, wrap, peplum, empire]
knowledge/style_graph/body_frame/female.yaml:61:      SilhouetteType:      [tapered]
knowledge/style_graph/body_frame/female.yaml:83:      SilhouetteType:      [a_line, flared, empire, relaxed]
knowledge/style_graph/body_frame/female.yaml:109:      SilhouetteType:      [peplum, wrap, fitted, a_line, empire]
knowledge/style_graph/body_frame/female.yaml:120:      SilhouetteType:      [straight, boxy, oversized]
knowledge/style_graph/body_frame/female.yaml:134:      SilhouetteType:      [a_line, empire, flared, relaxed]
knowledge/style_graph/body_frame/female.yaml:164:      SilhouetteType:      [a_line, empire, relaxed]
knowledge/style_graph/body_frame/female.yaml:191:      SilhouetteType:      [fitted, a_line, wrap, flared]
knowledge/style_graph/body_frame/male.yaml:18:      SilhouetteType:      [fitted, straight, tapered]
knowledge/style_graph/body_frame/male.yaml:26:      SilhouetteType:      [oversized, boxy]
knowledge/style_graph/body_frame/male.yaml:40:      SilhouetteType:      [fitted, straight, relaxed]
knowledge/style_graph/body_frame/male.yaml:59:      SilhouetteType:      [straight, fitted]
knowledge/style_graph/body_frame/male.yaml:66:      SilhouetteType:      [oversized, boxy]
knowledge/style_graph/body_frame/male.yaml:85:      SilhouetteType:      [straight, relaxed]
knowledge/style_graph/body_frame/male.yaml:104:      SilhouetteType:      [straight, relaxed]
knowledge/style_graph/body_frame/male.yaml:126:      SilhouetteType:      [straight, relaxed]
modules/agentic_application/src/agentic_application/composition/pairing.py:336:            continue  # attr not on Item; skip (e.g., SilhouetteType)
modules/agentic_application/src/agentic_application/composition/render.py:15:    - SilhouetteType: ...
modules/agentic_application/src/agentic_application/composition/render.py:60:    "SilhouetteType",
modules/agentic_application/src/agentic_application/orchestrator.py:191:        "silhouette_type": str(enriched.get("silhouette_type") or metadata.get("SilhouetteType") or ""),
modules/agentic_application/src/agentic_application/orchestrator.py:4139:            "silhouette_type": str(item.get("silhouette_type") or catalog_attrs.get("SilhouetteType") or ""),
modules/agentic_application/src/agentic_application/services/onboarding_gateway.py:79:                row["silhouette_type"] = str(row.get("silhouette_type") or catalog_attrs.get("SilhouetteType") or "")
modules/catalog/src/catalog/enrichment/audit.py:12:    ("SilhouetteContour", "SilhouetteType"),
modules/catalog/src/catalog/enrichment/audit.py:27:    "SilhouetteType",
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:193:SilhouetteType rules:
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:329:- SilhouetteContour and SilhouetteType should describe compatible shape behavior.
modules/catalog/src/catalog/retrieval/document_builder.py:32:    ("SILHOUETTE_AND_FIT", ["SilhouetteContour", "SilhouetteType", "VolumeProfile", "FitEase", "FitType", "ShoulderStructure", "WaistDefinition", "HipDefinition"]),
modules/platform_core/src/platform_core/repositories.py:481:        "silhouette_type":     "SilhouetteType",
modules/style_engine/configs/config/garment_attributes.json:78:    "SilhouetteType": [
modules/style_engine/configs/config/tier1_ranked_attributes.json:19:      "SilhouetteType",
modules/style_engine/configs/config/tier2_ranked_attributes.json:37:      "SilhouetteType"
modules/style_engine/configs/config/tier2_ranked_attributes.json:40:      "SilhouetteType",
modules/style_engine/configs/config/tier2_ranked_attributes.json:54:      "SilhouetteType",
modules/style_engine/configs/config/tier2_ranked_attributes.json:68:      "SilhouetteType"
modules/style_engine/configs/config/tier2_ranked_attributes.json:81:      "SilhouetteType",
modules/style_engine/configs/config/tier2_ranked_attributes.json:93:      "SilhouetteType",
modules/style_engine/configs/config/tier2_ranked_attributes.json:101:      "SilhouetteType",
modules/style_engine/configs/config/tier2_ranked_attributes.json:154:    "SilhouetteType": [
modules/user/src/user/service.py:188:                self._clean_attr(attrs.get("SilhouetteType")).replace("_", " "),
supabase/migrations/20260312160000_catalog_enriched.sql:18:  "SilhouetteType" text null,
supabase/migrations/20260312160000_catalog_enriched.sql:65:  "SilhouetteType_confidence" double precision null,
tests/test_catalog_retrieval.py:51:            "SilhouetteType": "",
tests/test_catalog_retrieval.py:52:            "SilhouetteType_confidence": "0.0",
tests/test_composition_reduction.py:61:            "SilhouetteType",
tests/test_composition_render.py:61:                "SilhouetteType": ("a_line",),       # GARMENT_REQUIREMENTS
tests/test_onboarding.py:419:                "SilhouetteType": "straight",
tests/test_onboarding.py:420:                "SilhouetteType_confidence": 0.88,
tests/test_platform_core.py:152:                     "SilhouetteType": "structured", "EmbellishmentLevel": "none",
tests/test_platform_core.py:157:                     "SilhouetteType": "soft", "EmbellishmentLevel": "none",
tests/test_platform_core.py:259:                     "SilhouetteType": "structured", "EmbellishmentLevel": "none",
```

### `StretchLevel` (15 hits)

```
knowledge/style_graph/archetype.yaml:299:      StretchLevel:          [moderate, high]
knowledge/style_graph/occasion.yaml:343:      StretchLevel:          [moderate, high]
knowledge/style_graph/weather.yaml:35:      StretchLevel:        [low, moderate]
knowledge/style_graph/weather.yaml:91:      StretchLevel:        [low, moderate, high]
knowledge/style_graph/weather.yaml:112:      StretchLevel:        [low, moderate]
modules/agentic_application/src/agentic_application/composition/render.py:86:    "StretchLevel",
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:94:StretchLevel rules:
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:95:StretchLevel refers only to visible elasticity cues.
modules/catalog/src/catalog/retrieval/document_builder.py:34:    ("FABRIC_AND_BUILD", ["FabricDrape", "FabricWeight", "FabricTexture", "StretchLevel", "EdgeSharpness", "ConstructionDetail"]),
modules/style_engine/configs/config/garment_attributes.json:204:    "StretchLevel": [
modules/style_engine/configs/config/tier2_ranked_attributes.json:223:    "StretchLevel": [],
supabase/migrations/20260312160000_catalog_enriched.sql:32:  "StretchLevel" text null,
supabase/migrations/20260312160000_catalog_enriched.sql:79:  "StretchLevel_confidence" double precision null,
tests/test_catalog_retrieval.py:79:            "StretchLevel": "Low Stretch",
tests/test_catalog_retrieval.py:80:            "StretchLevel_confidence": "0.73",
```

### `VolumePlacement` (9 hits)

```
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:44:- Many garments in this catalog are Indian (saree, kurta, anarkali, lehenga, sherwani, salwar suit, dupatta). Apply the Indian-context attribute rules below for axes that have them (ShoulderExposure, SleeveVolume, BlouseLength, BorderContrast, FabricTransparency, SurfaceFinish, LayeringVisibility, VolumePlacement, AsymmetryType, AttachmentStructure, MotionBehavior).
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:397:VolumePlacement rules:
modules/style_engine/configs/config/garment_attributes.json:456:    "VolumePlacement": [
supabase/migrations/20260516000000_catalog_enriched_path_b_rationalization.sql:12:--   endorsed ShapeArchitecture axes (VolumePlacement, AsymmetryType,
supabase/migrations/20260516000000_catalog_enriched_path_b_rationalization.sql:48:  -- VolumePlacement: where on the garment volume concentrates
supabase/migrations/20260516000000_catalog_enriched_path_b_rationalization.sql:50:  add column if not exists "VolumePlacement" text null,
supabase/migrations/20260516000000_catalog_enriched_path_b_rationalization.sql:51:  add column if not exists "VolumePlacement_confidence" double precision null,
tests/test_config_and_schema.py:47:        # ShapeArchitecture axes: VolumePlacement, AsymmetryType,
tests/test_config_and_schema.py:63:            "VolumePlacement", "AsymmetryType", "AttachmentStructure",
```

### `VolumeProfile` (80 hits)

```
knowledge/style_graph/archetype.yaml:47:      VolumeProfile:         [sculpted, exaggerated]       # sculpted (puff sleeve, peplum) reads trendy / dramatic — conflicts with classic timelessness
knowledge/style_graph/archetype.yaml:84:      VolumeProfile:         [sculpted, voluminous, exaggerated]   # any localized or whole-garment drama violates minimalist's clean-line ethic
knowledge/style_graph/archetype.yaml:143:      VolumeProfile:         [moderate, sculpted]          # peplum, puff sleeve, balloon hem are signature romantic shapes
knowledge/style_graph/archetype.yaml:206:      VolumeProfile:         [moderate, voluminous, exaggerated, sculpted]   # sculpted (architectural sleeve / peplum / structured shoulder) is signature dramatic
knowledge/style_graph/archetype.yaml:239:      VolumeProfile:         [moderate, sculpted]          # sculpted sleeves / peplum read as artisanal craft on creative palette
knowledge/style_graph/body_frame/female.yaml:25:      VolumeProfile:       [flat, moderate]
knowledge/style_graph/body_frame/female.yaml:36:      VolumeProfile:       [voluminous, exaggerated]
knowledge/style_graph/body_frame/female.yaml:56:      VolumeProfile:       [moderate, sculpted]           # bottom can carry more; sculpted at top (puff sleeve, peplum bodice) balances wider hips — never at bottom
knowledge/style_graph/body_frame/female.yaml:84:      VolumeProfile:       [voluminous, sculpted]         # at bottom slot only — top stays moderate (see notes); sculpted at bottom (peplum, balloon hem) softens broad shoulder, never at top (puff sleeve overloads shoulder line)
knowledge/style_graph/body_frame/female.yaml:114:      VolumeProfile:       [moderate, sculpted]           # mid-section adds curve; sculpted at either slot (puff sleeve, peplum hem) creates curve illusion on a straight frame
knowledge/style_graph/body_frame/female.yaml:140:      VolumeProfile:       [moderate]                     # at top
knowledge/style_graph/body_frame/female.yaml:151:      VolumeProfile:       [flat, sculpted]               # flat is too body-skimming; sculpted (peplum, puff sleeve) draws eye to midsection — sleeves only OK if visually distant from torso (handled in notes)
knowledge/style_graph/body_frame/female.yaml:170:      VolumeProfile:       [moderate, sculpted]           # sculpted at top (puff/sculpted sleeve) broadens shoulder line — at bottom is fine since hips are narrow
knowledge/style_graph/body_frame/female.yaml:178:      VolumeProfile:       [exaggerated]                  # at midsection
knowledge/style_graph/body_frame/female.yaml:194:      VolumeProfile:       [moderate, sculpted]           # athletic frame carries sculpted accents at either slot — polished without overpowering
knowledge/style_graph/body_frame/female.yaml:199:      VolumeProfile:       [exaggerated]
knowledge/style_graph/body_frame/female.yaml:213:      VolumeProfile:       [moderate, voluminous, sculpted]  # at bottom; sculpted at bottom (peplum, balloon hem) softens broad shoulder by adding weight below
knowledge/style_graph/body_frame/female.yaml:220:      VolumeProfile:       [exaggerated]                  # at top
knowledge/style_graph/body_frame/female.yaml:228:      VolumeProfile:       [moderate]                     # at bottom
knowledge/style_graph/body_frame/female.yaml:237:      VolumeProfile:       [flat, moderate, sculpted]     # balanced ratio carries sculpted at either slot
knowledge/style_graph/body_frame/female.yaml:309:      VolumeProfile:       [voluminous, exaggerated]
knowledge/style_graph/body_frame/female.yaml:326:      VolumeProfile:       [moderate, voluminous]
knowledge/style_graph/body_frame/female.yaml:343:      VolumeProfile:       [flat, moderate]
knowledge/style_graph/body_frame/female.yaml:348:      VolumeProfile:       [exaggerated]
knowledge/style_graph/body_frame/female.yaml:382:      VolumeProfile:       [moderate]
knowledge/style_graph/body_frame/female.yaml:427:      VolumeProfile:       [moderate]                     # at bust
knowledge/style_graph/body_frame/female.yaml:714:      VolumeProfile:       [flat, moderate]
knowledge/style_graph/body_frame/female.yaml:719:      VolumeProfile:       [exaggerated]
knowledge/style_graph/body_frame/female.yaml:761:      VolumeProfile:       [moderate]
knowledge/style_graph/body_frame/female.yaml:765:      VolumeProfile:       [exaggerated]
knowledge/style_graph/body_frame/female.yaml:776:      VolumeProfile:       [flat, moderate]
knowledge/style_graph/body_frame/female.yaml:782:      VolumeProfile:       [voluminous, exaggerated]
knowledge/style_graph/body_frame/female.yaml:797:      VolumeProfile:       [moderate, voluminous]
knowledge/style_graph/body_frame/male.yaml:23:      VolumeProfile:       [flat, moderate]
knowledge/style_graph/body_frame/male.yaml:43:      VolumeProfile:       [moderate]                      # at bottom
knowledge/style_graph/body_frame/male.yaml:48:      VolumeProfile:       [exaggerated, sculpted]         # at top — sculpted shoulder/yoke detail overloads an already-broad shoulder line
knowledge/style_graph/body_frame/male.yaml:63:      VolumeProfile:       [flat, moderate, sculpted]      # sculpted yoke/shoulder structure adds visual shape to a straight column frame
knowledge/style_graph/body_frame/male.yaml:87:      VolumeProfile:       [moderate, sculpted]            # at top — sculpted yoke / structured shoulder broadens shoulder line to balance wider lower body
knowledge/style_graph/body_frame/male.yaml:131:      VolumeProfile:       [sculpted]                      # at top — sculpted yoke / shoulder broadens narrower shoulder line; never at midsection (already full)
knowledge/style_graph/body_frame/male.yaml:156:      VolumeProfile:       [moderate]                      # at bottom
knowledge/style_graph/body_frame/male.yaml:182:      VolumeProfile:       [moderate]                      # at top
knowledge/style_graph/body_frame/male.yaml:185:      VolumeProfile:       [voluminous]                    # at bottom
knowledge/style_graph/body_frame/male.yaml:193:      VolumeProfile:       [moderate]                      # at top
knowledge/style_graph/body_frame/male.yaml:196:      VolumeProfile:       [voluminous]                    # at bottom
knowledge/style_graph/body_frame/male.yaml:234:      VolumeProfile:       [flat, moderate]
knowledge/style_graph/body_frame/male.yaml:239:      VolumeProfile:       [voluminous]
knowledge/style_graph/body_frame/male.yaml:254:      VolumeProfile:       [moderate]
knowledge/style_graph/body_frame/male.yaml:267:      VolumeProfile:       [flat, moderate]
knowledge/style_graph/body_frame/male.yaml:304:      VolumeProfile:       [moderate]
knowledge/style_graph/body_frame/male.yaml:598:      VolumeProfile:       [flat, moderate]
knowledge/style_graph/body_frame/male.yaml:602:      VolumeProfile:       [voluminous]
knowledge/style_graph/body_frame/male.yaml:645:      VolumeProfile:       [moderate]
knowledge/style_graph/body_frame/male.yaml:659:      VolumeProfile:       [flat, moderate]
knowledge/style_graph/body_frame/male.yaml:678:      VolumeProfile:       [moderate]
modules/agentic_application/src/agentic_application/composition/engine.py:664:#       NecklineType, PatternScale, VolumeProfile, ShoulderStructure,
modules/agentic_application/src/agentic_application/composition/pairing.py:130:# (VolumeProfile, ShoulderStructure, etc.) get skipped at tuple-level
modules/agentic_application/src/agentic_application/composition/render.py:61:    "VolumeProfile",
modules/agentic_application/src/agentic_application/orchestrator.py:189:        "volume_profile": str(enriched.get("volume_profile") or metadata.get("VolumeProfile") or ""),
modules/agentic_application/src/agentic_application/orchestrator.py:4137:            "volume_profile": str(item.get("volume_profile") or catalog_attrs.get("VolumeProfile") or ""),
modules/agentic_application/src/agentic_application/services/onboarding_gateway.py:77:                row["volume_profile"] = str(row.get("volume_profile") or catalog_attrs.get("VolumeProfile") or "")
modules/catalog/src/catalog/enrichment/audit.py:20:    "VolumeProfile",
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:62:VolumeProfile rules:
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:63:VolumeProfile describes macro visual mass relative to body, not closeness.
modules/catalog/src/catalog/retrieval/document_builder.py:32:    ("SILHOUETTE_AND_FIT", ["SilhouetteContour", "SilhouetteType", "VolumeProfile", "FitEase", "FitType", "ShoulderStructure", "WaistDefinition", "HipDefinition"]),
modules/style_engine/configs/config/garment_attributes.json:95:    "VolumeProfile": [
modules/style_engine/configs/config/tier2_ranked_attributes.json:163:    "VolumeProfile": [],
ops/scripts/patch_volume_profile_corrections.py:7:couldn't represent until ``sculpted`` was added to the VolumeProfile enum
ops/scripts/patch_volume_profile_corrections.py:50:            "VolumeProfile": "sculpted",
supabase/migrations/20260312160000_catalog_enriched.sql:19:  "VolumeProfile" text null,
supabase/migrations/20260312160000_catalog_enriched.sql:66:  "VolumeProfile_confidence" double precision null,
tests/test_catalog_retrieval.py:53:            "VolumeProfile": "Moderate",
tests/test_catalog_retrieval.py:54:            "VolumeProfile_confidence": "0.84",
tests/test_composition_engine.py:698:        mapping = self._mk_mapping(hard_flatters={"VolumeProfile": ["moderate"]})
tests/test_composition_engine.py:700:        contribs = by_attr["VolumeProfile"]
tests/test_composition_yaml_loader.py:249:        VolumeProfile in body_frame/female.yaml, body_frame/male.yaml, and
tests/test_composition_yaml_loader.py:258:                        if attr == "VolumeProfile" and "sculpted" in vals:
tests/test_composition_yaml_loader.py:261:                        if attr == "VolumeProfile" and "sculpted" in vals:
tests/test_composition_yaml_loader.py:267:            "body_frame/female.yaml has no VolumeProfile=sculpted reference",
tests/test_composition_yaml_loader.py:271:            "body_frame/male.yaml has no VolumeProfile=sculpted reference",
tests/test_composition_yaml_loader.py:275:            "archetype.yaml has no VolumeProfile=sculpted reference",
```

### `WaistDefinition` (78 hits)

```
knowledge/style_graph/body_frame/female.yaml:24:      WaistDefinition:     [defined, cinched, belted, natural]
knowledge/style_graph/body_frame/female.yaml:35:      WaistDefinition:     [undefined, dropped, empire]
knowledge/style_graph/body_frame/female.yaml:49:      WaistDefinition:     [defined, empire, natural]
knowledge/style_graph/body_frame/female.yaml:85:      WaistDefinition:     [empire, natural, undefined]
knowledge/style_graph/body_frame/female.yaml:110:      WaistDefinition:     [defined, cinched, belted, empire]
knowledge/style_graph/body_frame/female.yaml:122:      WaistDefinition:     [undefined, dropped]
knowledge/style_graph/body_frame/female.yaml:135:      WaistDefinition:     [empire, undefined]
knowledge/style_graph/body_frame/female.yaml:148:      WaistDefinition:     [defined, cinched, belted]
knowledge/style_graph/body_frame/female.yaml:165:      WaistDefinition:     [empire, undefined]
knowledge/style_graph/body_frame/female.yaml:176:      WaistDefinition:     [defined, cinched, belted]
knowledge/style_graph/body_frame/female.yaml:192:      WaistDefinition:     [natural, defined]
knowledge/style_graph/body_frame/female.yaml:269:      WaistDefinition:     [defined, cinched, belted, empire]
knowledge/style_graph/body_frame/female.yaml:275:      WaistDefinition:     [dropped, undefined]           # extends torso visually
knowledge/style_graph/body_frame/female.yaml:289:      WaistDefinition:     [natural, dropped]             # elongates torso
knowledge/style_graph/body_frame/female.yaml:291:      WaistDefinition:     [empire]                       # shortens torso further
knowledge/style_graph/body_frame/female.yaml:478:      WaistDefinition:     [defined, cinched, belted, natural]
knowledge/style_graph/body_frame/female.yaml:482:      WaistDefinition:     [empire, undefined]            # wastes the asset
knowledge/style_graph/body_frame/female.yaml:488:      WaistDefinition:     [natural, empire, undefined]
knowledge/style_graph/body_frame/female.yaml:493:      WaistDefinition:     [cinched, belted]
knowledge/style_graph/body_frame/female.yaml:501:      WaistDefinition:     [empire, undefined]
knowledge/style_graph/body_frame/female.yaml:508:      WaistDefinition:     [defined, cinched, belted]
knowledge/style_graph/body_frame/female.yaml:808:      WaistDefinition:     [defined, cinched, belted]
knowledge/style_graph/body_frame/female.yaml:816:      WaistDefinition:     [defined, cinched, belted, natural]
knowledge/style_graph/body_frame/female.yaml:823:      WaistDefinition:     [natural, defined]
knowledge/style_graph/body_frame/female.yaml:830:      WaistDefinition:     [empire, natural, undefined]
knowledge/style_graph/body_frame/female.yaml:834:      WaistDefinition:     [cinched, belted]
knowledge/style_graph/body_frame/female.yaml:841:      WaistDefinition:     [empire, undefined]
knowledge/style_graph/body_frame/female.yaml:846:      WaistDefinition:     [defined, cinched, belted]
knowledge/style_graph/body_frame/male.yaml:21:      WaistDefinition:     [natural, defined]
knowledge/style_graph/body_frame/male.yaml:61:      WaistDefinition:     [natural]
knowledge/style_graph/body_frame/male.yaml:67:      WaistDefinition:     [undefined]                     # makes silhouette read as a column
knowledge/style_graph/body_frame/male.yaml:106:      WaistDefinition:     [empire, undefined]
knowledge/style_graph/body_frame/male.yaml:114:      WaistDefinition:     [defined]
knowledge/style_graph/body_frame/male.yaml:130:      WaistDefinition:     [undefined, empire]
knowledge/style_graph/body_frame/male.yaml:134:      WaistDefinition:     [defined]
knowledge/style_graph/body_frame/male.yaml:146:      WaistDefinition:     [defined, natural]
knowledge/style_graph/body_frame/male.yaml:221:      WaistDefinition:     [natural, dropped]
knowledge/style_graph/body_frame/male.yaml:223:      WaistDefinition:     [empire]                        # shortens torso further
knowledge/style_graph/body_frame/male.yaml:386:      WaistDefinition:     [defined, natural]
knowledge/style_graph/body_frame/male.yaml:393:      WaistDefinition:     [natural, undefined]
knowledge/style_graph/body_frame/male.yaml:397:      WaistDefinition:     [defined]                       # cinches midsection
knowledge/style_graph/body_frame/male.yaml:404:      WaistDefinition:     [empire, undefined]
knowledge/style_graph/body_frame/male.yaml:410:      WaistDefinition:     [defined]
knowledge/style_graph/body_frame/male.yaml:687:      WaistDefinition:     [defined, natural]
knowledge/style_graph/body_frame/male.yaml:694:      WaistDefinition:     [defined, natural]
knowledge/style_graph/body_frame/male.yaml:701:      WaistDefinition:     [natural]
knowledge/style_graph/body_frame/male.yaml:708:      WaistDefinition:     [natural, undefined]
knowledge/style_graph/body_frame/male.yaml:711:      WaistDefinition:     [defined]
knowledge/style_graph/body_frame/male.yaml:718:      WaistDefinition:     [empire, undefined]
knowledge/style_graph/body_frame/male.yaml:723:      WaistDefinition:     [defined]
modules/agentic_application/src/agentic_application/composition/engine.py:665:#       WaistDefinition, HipDefinition, BodyFocusZone. Without it
modules/agentic_application/src/agentic_application/composition/render.py:64:    "WaistDefinition",
modules/catalog/src/catalog/enrichment/audit.py:24:    "WaistDefinition",
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:140:WaistDefinition rules:
modules/catalog/src/catalog/enrichment/prompts/system_prompt.txt:141:WaistDefinition refers only to shaping, seam placement, or tightening at waist.
modules/catalog/src/catalog/retrieval/document_builder.py:32:    ("SILHOUETTE_AND_FIT", ["SilhouetteContour", "SilhouetteType", "VolumeProfile", "FitEase", "FitType", "ShoulderStructure", "WaistDefinition", "HipDefinition"]),
modules/style_engine/configs/config/garment_attributes.json:160:    "WaistDefinition": [
modules/style_engine/configs/config/tier2_ranked_attributes.json:33:      "WaistDefinition",
modules/style_engine/configs/config/tier2_ranked_attributes.json:42:      "WaistDefinition",
modules/style_engine/configs/config/tier2_ranked_attributes.json:65:      "WaistDefinition",
modules/style_engine/configs/config/tier2_ranked_attributes.json:83:      "WaistDefinition",
modules/style_engine/configs/config/tier2_ranked_attributes.json:92:      "WaistDefinition",
modules/style_engine/configs/config/tier2_ranked_attributes.json:196:    "WaistDefinition": [
supabase/migrations/20260312160000_catalog_enriched.sql:27:  "WaistDefinition" text null,
supabase/migrations/20260312160000_catalog_enriched.sql:74:  "WaistDefinition_confidence" double precision null,
tests/test_catalog_retrieval.py:61:            "WaistDefinition": "Defined",
tests/test_catalog_retrieval.py:62:            "WaistDefinition_confidence": "0.9",
tests/test_composition_engine.py:709:        mapping = self._mk_mapping(soft_flatters={"WaistDefinition": ["soft_defined"]})
tests/test_composition_engine.py:711:        contribs = by_attr["WaistDefinition"]
tests/test_composition_engine.py:722:            hard_flatters={"WaistDefinition": ["defined"]},
tests/test_composition_engine.py:727:        self.assertEqual(by_attr["WaistDefinition"][0].tier, "hard")  # forced
tests/test_composition_yaml_loader.py:431:            hard_flatters={"WaistDefinition": ["defined", "hard_cinched"]},
tests/test_composition_yaml_loader.py:436:        self.assertEqual(m.hard_flatters["WaistDefinition"], ("defined", "hard_cinched"))
tests/test_composition_yaml_loader.py:443:            soft_flatters={"WaistDefinition": ["soft_defined"]},
tests/test_composition_yaml_loader.py:448:        self.assertEqual(m.soft_flatters["WaistDefinition"], ("soft_defined",))
tests/test_composition_yaml_loader.py:453:            hard_flatters={"WaistDefinition": ["defined"]},
tests/test_composition_yaml_loader.py:454:            soft_flatters={"WaistDefinition": ["soft_defined"]},
tests/test_composition_yaml_loader.py:459:        self.assertIn("WaistDefinition", msg)
```
