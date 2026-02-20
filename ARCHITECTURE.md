# Garment Attribute Extraction Architecture (Batch + Confidence)

## 1) Scope and Inputs
- Input: `catalog.csv` with `name, description, store, image_url, url, price`.
- Target: derive categorical attributes from `ATTRIBUTE_LIST.md` and produce per-attribute confidence.
- Note: current `ATTRIBUTE_LIST.md` defines **30** attributes (original 27 + `GarmentCategory`, `PrimaryColor`, `SecondaryColor`).

## 2) Output Contract
For each attribute `X`, output:
- `X`: enum value (or `null` when unknown)
- `X_confidence`: float in `[0,1]`

Final enriched CSV:
- Original columns
- 30 attribute columns
- 30 confidence columns
- optional: `row_status`, `error_reason`

## 3) Batch Pipeline
1. Read `catalog.csv`.
2. Build `batch_input.jsonl` (1 request per row, unique `custom_id`).
3. Upload JSONL (`purpose=batch`), create Batch job on `/v1/responses` with `model: gpt-5-nano`.
4. Poll until completed.
5. Download `output_file_id` and `error_file_id`.
6. Parse responses by `custom_id` (never rely on line order).
7. Merge attributes + confidence back into original rows.
8. Export `enriched_catalog.csv`.
9. Retry only failed/invalid rows.

## 4) Request/Response Design
Use Structured Outputs with strict JSON Schema:
- `text.format.type = "json_schema"`
- `text.format.strict = true`
- `additionalProperties = false`
- each attribute field uses enum from `ATTRIBUTE_LIST.md`
- each `*_confidence` uses numeric bounds `minimum: 0`, `maximum: 1`

### Response shape per row
```json
{
  "GarmentLength": "knee",
  "GarmentLength_confidence": 0.86,
  "SilhouetteType": "a_line",
  "SilhouetteType_confidence": 0.79
}
```

## 5) Confidence Strategy (Per Attribute)
Confidence should be produced per attribute by combining 3 signals:
- `model_confidence`: score returned by model for that attribute.
- `evidence_consistency`: agreement between text cues and image cues.
- `enum_margin`: confidence penalty when multiple enum classes are plausible.

Recommended calibrated score:
`final_confidence = 0.60*model_confidence + 0.30*evidence_consistency + 0.10*enum_margin`

Operational rules:
- If evidence is weak/conflicting, prefer `null` with low confidence (e.g., `<=0.35`).
- If image is unavailable/invalid, lower image-dependent attributes automatically.
- If schema validation fails, mark row failed and retry.

## 6) Attribute Set (from ATTRIBUTE_LIST.md)
Attributes:
1. `GarmentCategory` (enum)
2. `GarmentLength` (enum)
3. `SilhouetteType` (enum)
4. `FitType` (enum)
5. `VisualWeightPlacement` (enum)
6. `NecklineType` (enum)
7. `NecklineDepth` (enum)
8. `SleeveLength` (enum)
9. `SkinExposureLevel` (enum)
10. `FormalitySignalStrength` (enum)
11. `OccasionFit` (enum)
12. `TimeOfDay` (enum)
13. `ColorTemperature` (enum)
14. `ColorSaturation` (enum)
15. `ColorCount` (enum)
16. `ColorValue` (enum)
17. `ConstructionDetail` (enum)
18. `ContrastLevel` (enum)
19. `PatternType` (enum)
20. `PatternScale` (enum)
21. `PatternOrientation` (enum)
22. `FabricDrape` (enum)
23. `FabricWeight` (enum)
24. `FabricTexture` (enum)
25. `WaistDefinition` (enum)
26. `EmbellishmentLevel` (enum)
27. `EmbellishmentZone` (enum)
28. `BodyFocusZone` (enum)
29. `PrimaryColor` (free-text, nullable)
30. `SecondaryColor` (free-text, nullable)

## 7) Confidence by Attribute Family
- Silhouette/Fit family (`GarmentLength`, `SilhouetteType`, `FitType`, `WaistDefinition`): image-dominant, text-secondary.
- Neck/Sleeve/Skin family (`NecklineType`, `NecklineDepth`, `SleeveLength`, `SkinExposureLevel`): image-dominant.
- Styling/Occasion family (`FormalitySignalStrength`, `OccasionFit`, `TimeOfDay`): text + image balanced.
- Color/Pattern family (`ColorTemperature`, `ColorSaturation`, `ColorCount`, `ColorValue`, `PatternType`, `PatternScale`, `PatternOrientation`, `ContrastLevel`): image-dominant.
- Fabric/Detail family (`FabricDrape`, `FabricWeight`, `FabricTexture`, `ConstructionDetail`, `EmbellishmentLevel`, `EmbellishmentZone`): often uncertain from image; confidence should be conservative.
- Focus/Balance family (`VisualWeightPlacement`, `BodyFocusZone`): image-dominant with low tolerance for guessing.

## 8) Quality Controls
- Preflight:
  - verify CSV headers
  - verify `image_url` format and fetchability
- Post-parse:
  - JSON Schema validation on every row
  - confidence range checks `[0,1]`
  - enum membership checks
- QA metrics:
  - per-attribute null rate
  - per-attribute mean confidence
  - drift alerts when confidence/null rate shifts materially

## 9) 22 vs 30 Reconciliation
If business requires exactly 22:
- keep this architecture unchanged
- configure an `active_attribute_list` containing the chosen 22
- generate schema dynamically from that list so pipeline remains stable.
