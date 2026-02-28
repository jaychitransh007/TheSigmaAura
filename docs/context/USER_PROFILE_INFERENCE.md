# User Profile Inference

Last updated: February 28, 2026

Context sync note:
- Latest changes were in conversation feedback telemetry/UI; profiler schema and model routing remain unchanged.
- Latest catalog update adds auto-chunk checkpoint/resume in enrichment; profiler behavior remains unchanged.
- Conversation eval runs can reuse profiler image artifacts (`data/logs/user_profiler/input_*.{ext}`) as fixed `--image-ref` inputs.

## Purpose
Infer user-side styling context from:
- one uploaded user image (visual reasoning)
- one natural-language user intent text (textual reasoning)

The module makes exactly two OpenAI Responses API calls.
It uses the standard real-time API (not Batch API).

## Module Layout
- Module package: `modules/user_profiler/src/user_profiler/`
- Root entrypoint: `run_user_profiler.py`
- Prompts:
  - `modules/user_profiler/src/user_profiler/prompts/visual_prompt.txt`
  - `modules/user_profiler/src/user_profiler/prompts/textual_prompt.txt`

## OpenAI Calls
1. Visual reasoning call (`gpt-5.2`)
- Input: user image (local file path, URL, or browser-provided `data:image/...` payload)
- Output fields:
  - `HeightCategory`
  - `BodyShape`
  - `VisualWeight`
  - `VerticalProportion`
  - `ArmVolume`
  - `MidsectionState`
  - `WaistVisibility`
  - `BustVolume`
  - `SkinUndertone`
  - `SkinSurfaceColor`
  - `SkinContrast`
  - `FaceShape`
  - `NeckLength`
  - `HairLength`
  - `HairColor`
  - `gender`
  - `age`

2. Textual reasoning call (`gpt-5-mini`)
- Input: natural-language context text
- Output fields:
  - `occasion`
  - `archetype`

## Enum Sources
- Body-harmony enums: `modules/style_engine/configs/config/body_harmony_attributes.json`
- User-context enums: `modules/style_engine/configs/config/user_context_attributes.json`

## Outputs
Default outputs under `data/logs/`:
- Combined result: `user_profile_inference.json`
- Tier2 profile payload: `user_style_profile.json`
- Tier1/Tier2 context payload: `user_style_context.json`
- Stored input image artifact: `data/logs/user_profiler/input_*.{ext}`

`user_style_profile.json` is ready for `run_style_pipeline.py --profile`.
`user_style_context.json` contains `occasion`, `archetype`, `gender`, `age`.

## CLI
```bash
python3 run_user_profiler.py \
  --image /absolute/path/to/user_photo.jpg \
  --context-text "I need looks for office days and occasional evening dinners." \
  --out data/logs/user_profile_inference.json \
  --style-profile-out data/logs/user_style_profile.json \
  --style-context-out data/logs/user_style_context.json
```

## Notes
- No `temperature` or `top_p` are sent.
- Visual call uses highest reasoning effort (`reasoning.effort = high`).
- Combined output logs per-call request/response payloads and visual reasoning notes.
- If unsure between enum values, prompts force deterministic tie-break to earliest enum value.
- Errors are returned as one-line `error: ...` messages from CLI.

## Role in Conversation Eval
- Eval runner: `ops/scripts/run_conversation_eval.py`
- Optional usage:
  - pass `--image-ref data/logs/user_profiler/input_<id>.webp` so all prompts are evaluated with a stable visual profile context
- This reduces clarification-only turns and improves comparability across eval runs.
