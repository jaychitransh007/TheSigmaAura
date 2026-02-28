# Conversation Service Blueprint

Last updated: February 28, 2026

## Scope
This blueprint defines API contracts and runtime behavior for:
1. Conversation turns and recommendation generation.
2. Mode-aware output (garment vs outfit).
3. Checkout preparation (without order placement).

## Service Components
1. Conversation API service (`conversation_platform`).
2. User profiling service (`user_profiler`).
3. Deterministic style engine (`style_engine`).
4. Local Supabase persistence and telemetry.
5. Commerce adapter service for cart/checkout prep.

## API Surface (Target Contract)
1. `POST /v1/conversations`
2. `GET /v1/conversations/{conversation_id}`
3. `POST /v1/conversations/{conversation_id}/turns`
4. `POST /v1/conversations/{conversation_id}/turns/start`
5. `GET /v1/conversations/{conversation_id}/turns/{job_id}/status`
6. `GET /v1/recommendations/{run_id}`
7. `POST /v1/feedback`
8. `POST /v1/conversations/{conversation_id}/checkout/prepare`
9. `GET /v1/checkout/preparations/{checkout_prep_id}`

## Conversation Create Contract
`POST /v1/conversations`

```json
{
  "user_id": "user_123",
  "initial_profile": {
    "sizes": { "top_size": "M" },
    "fit_preferences": { "fit_preference": "regular" },
    "brand_preferences": { "liked": ["BrandA"] },
    "budget_preferences": { "soft_cap": 4000, "hard_cap": 5000, "currency": "INR" }
  }
}
```

### Conversation Create Additions
1. `initial_profile`: optional profile object to seed canonical user profile at conversation start.

## Turn Request Contract
`POST /v1/conversations/{conversation_id}/turns`

```json
{
  "user_id": "user_123",
  "message": "Need a polished office look.",
  "image_refs": ["/absolute/path/user.jpg"],
  "strictness": "balanced",
  "hard_filter_profile": "rl_ready_minimal",
  "max_results": 12,
  "result_filter": "complete_plus_combos",
  "mode_preference": "auto",
  "target_garment_type": "shirt",
  "autonomy_level": "suggest",
  "size_overrides": {
    "top_size": "M",
    "bottom_size": "30",
    "fit_preference": "regular"
  }
}
```

### Turn Request Additions
1. `mode_preference`: `auto|garment|outfit` (default `auto`).
2. `target_garment_type`: optional string for garment-specific requests.
3. `autonomy_level`: `suggest|prepare` (default `suggest`).
4. `size_overrides`: optional profile patch object.

## Turn Response Contract

```json
{
  "conversation_id": "uuid",
  "turn_id": "uuid",
  "assistant_message": "Top recommendations are ready.",
  "resolved_context": {
    "occasion": "work_mode",
    "archetype": "classic",
    "gender": "female",
    "age": "25_30"
  },
  "profile_snapshot_id": "uuid",
  "recommendation_run_id": "uuid",
  "resolved_mode": "outfit",
  "complete_the_look_offer": true,
  "style_constraints_applied": ["body_harmony", "budget"],
  "profile_fields_used": ["top_size", "fit_preference", "brand_preferences"],
  "agent_trace_ids": ["trace_uuid_1", "trace_uuid_2"],
  "recommendations": [
    {
      "rank": 1,
      "garment_id": "combo::A|B",
      "title": "Look 1",
      "image_url": "https://...",
      "score": 0.89,
      "max_score": 1.1,
      "compatibility_confidence": 0.81,
      "reasons": "...",
      "recommendation_kind": "outfit_combo",
      "outfit_id": "combo::A|B",
      "component_count": 2,
      "component_ids": ["A", "B"]
    }
  ],
  "needs_clarification": false,
  "clarifying_question": ""
}
```

### Turn Response Additions
1. `resolved_mode`
2. `complete_the_look_offer`
3. `style_constraints_applied`
4. `profile_fields_used`
5. `agent_trace_ids` (for eval/debug environments)

## Checkout Preparation Contract

### Request
`POST /v1/conversations/{conversation_id}/checkout/prepare`

```json
{
  "user_id": "user_123",
  "recommendation_run_id": "uuid",
  "selected_item_ids": ["9259444797653", "9259444764885"],
  "selected_outfit_id": "combo::9259444797653|9259444764885",
  "budget_cap": 5000
}
```

### Response

```json
{
  "checkout_prep_id": "uuid",
  "status": "ready",
  "cart_items": [
    {
      "garment_id": "9259444797653",
      "qty": 1,
      "unit_price": 2499,
      "discount": 300,
      "final_price": 2199
    }
  ],
  "subtotal": 2499,
  "discount_total": 300,
  "final_total": 2199,
  "currency": "INR",
  "checkout_url_or_token": "checkout_ref",
  "validation_notes": ["stock_revalidated", "price_revalidated"]
}
```

Hard rule:
1. Checkout preparation endpoint must not place order.

## Type Definitions

```python
ModePreference = Literal["auto", "garment", "outfit"]
ResolvedMode = Literal["garment", "outfit"]
AutonomyLevel = Literal["suggest", "prepare"]
CheckoutPreparationStatus = Literal["pending", "ready", "needs_user_action", "failed"]
```

### SizeProfile Fields
1. `top_size`: optional string.
2. `bottom_size`: optional string.
3. `dress_size`: optional string.
4. `shoe_size`: optional string.
5. `fit_preference`: optional `"slim"|"regular"|"relaxed"|"oversized"`.
6. `comfort_preferences`: `List[str]`.
7. `blocked_styles`: `List[str]`.

## Stage Lifecycle
1. `validate_request`
2. `load_conversation_state`
3. `visual_profile_inference`
4. `text_intent_inference`
5. `merge_context_memory`
6. `resolve_mode`
7. `tier1_tier2_recommendation`
8. `persist_results`
9. `build_response`
10. `clarification_required` (conditional)
11. `checkout_prepare` (separate endpoint path)

## Persistence Points
1. Create `conversation_turns` row at turn start.
2. Persist `profile_snapshots` and `context_snapshots` after inference merge.
3. Persist `recommendation_runs` and `recommendation_items` after ranking.
4. Persist `tool_traces` for key agent/tool decisions.
5. Persist `checkout_preparations` and `checkout_preparation_items` after checkout-prep flow.

## Data Model Additions

### users
1. `profile_json jsonb not null default '{}'` for canonical user profile.
2. `profile_updated_at timestamptz`.

### conversation_turns
1. `mode_preference text`.
2. `resolved_mode text check (resolved_mode in ('garment','outfit'))`.
3. `autonomy_level text check (autonomy_level in ('suggest','prepare'))`.

### recommendation_runs
1. `resolved_mode text not null`.
2. `requested_garment_types_json jsonb not null default '[]'::jsonb`.
3. `style_constraints_json jsonb not null default '{}'::jsonb`.

### new table: checkout_preparations
1. `id uuid pk`, `conversation_id`, `turn_id`, `recommendation_run_id`, `user_id`.
2. `status text check (status in ('pending','ready','needs_user_action','failed'))`.
3. `cart_payload_json`, `pricing_json`, `validation_json`, `checkout_ref`.
4. `created_at`, `updated_at`.

### new table: checkout_preparation_items
1. `id uuid pk`, `checkout_preparation_id`, `rank`, `garment_id`, `title`, `qty`, `unit_price`, `discount`, `final_price`, `meta_json`.

## Error and Fallback Behavior
1. Missing image and no prior profile snapshot:
   - return clarification request; skip recommendation run.

2. Missing required context fields:
   - return clarification question; keep conversation active.

3. Low recommendation confidence:
   - return refinement prompt with constraints request.

4. Inventory or price mismatch in checkout prep:
   - apply substitution within budget, else return `needs_user_action`.

5. Policy violation attempts:
   - block action and return guardrail explanation.

6. Mode ambiguity:
   - fallback to outfit mode with explicit switch CTA.
