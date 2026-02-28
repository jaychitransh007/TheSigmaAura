# User Profile + Body Harmony Module

Last updated: February 28, 2026

## Purpose
Define the canonical profile contract and body-harmony responsibilities used by the conversation system.

## Module Scope
1. Infer and maintain body-harmony profile attributes.
2. Maintain user identity and preference profile.
3. Provide profile and constraints to recommendation flow.

## Canonical User Profile Schema

```json
{
  "sizes": {
    "top_size": "M",
    "bottom_size": "30",
    "dress_size": "M",
    "shoe_size": "39"
  },
  "fit_preferences": {
    "fit_preference": "regular",
    "comfort_preferences": ["stretch_fabric", "mid_rise", "breathable"],
    "blocked_styles": ["sleeveless", "cropped"],
    "blocked_categories": ["innerwear"]
  },
  "brand_preferences": {
    "liked": ["BrandA", "BrandB"],
    "disliked": ["BrandX"]
  },
  "budget_preferences": {
    "soft_cap": 4000,
    "hard_cap": 5000,
    "currency": "INR"
  },
  "consent_flags": {
    "image_inference_allowed": true,
    "telemetry_allowed": true
  }
}
```

## Body Harmony Contract
The body-harmony portion uses enum attributes configured in:
1. `modules/style_engine/configs/config/body_harmony_attributes.json`

Current inferred fields:
1. `HeightCategory`
2. `BodyShape`
3. `VisualWeight`
4. `VerticalProportion`
5. `ArmVolume`
6. `MidsectionState`
7. `WaistVisibility`
8. `BustVolume`
9. `SkinUndertone`
10. `SkinSurfaceColor`
11. `SkinContrast`
12. `FaceShape`
13. `NeckLength`
14. `HairLength`
15. `HairColor`
16. `gender`
17. `age`

## Merge Strategy
1. Explicit user input always wins over inferred values (last-write-wins for explicit fields).
2. Inferred fields are updated only when confidence exceeds prior value or no prior exists.
3. `size_overrides` from turn request are applied as explicit input.
4. Confidence and timestamp are stored per inferred field.

## Responsibility Boundary
1. `User Profile & Identity` owns explicit user-provided profile fields and consent state.
2. `Body Harmony & Archetype` owns inferred visual/body context and confidence.
3. `Style Agent` consumes both outputs but does not own persistence of canonical profile data.

## Confidence Handling
1. Each inferred field should have confidence metadata.
2. Confidence levels are stored in profile snapshot `confidence_json`.
3. Explicit user input overrides inferred fields for overlapping concepts.

## Clarification Triggers
A clarification question is required when any of the below blocks recommendation execution:
1. Missing `gender` and `age` with no reusable profile snapshot.
2. Missing `occasion` and `archetype` after text inference.
3. Missing essential size fields when user requests checkout preparation.
4. Consent flags not present for image inference while image input is required.

## Runtime Contract
1. Visual inference call (model and prompt controlled by module config).
2. Text inference call for context (`occasion`, `archetype`).
3. Profile merge performed before recommendation stage.
4. Snapshot persisted to conversation context and profile snapshots.
