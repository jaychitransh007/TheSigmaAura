# Product Overview

Last updated: April 8, 2026

> **What is live today vs. aspirational:** This document describes the
> **target** product, including personas and surfaces that are not yet
> built. The currently live surfaces are **web** (onboarding, chat,
> wardrobe, profile, admin catalog) only. WhatsApp inbound is *not* in
> the live system — the runtime was deliberately removed and is being
> rebuilt as a separate workstream. Treat every mention of WhatsApp
> below as roadmap, not production. For the authoritative "what
> actually works right now" view, see `docs/CURRENT_STATE.md`.

## Purpose

Sigma Aura is a personal fashion copilot.

For a user, it is meant to become a repeat-use assistant for real clothing decisions:
- what should I wear
- what goes with this piece
- should I buy this
- how would this look on me
- how do I plan from what I already own
- what collar, color, pattern, or style direction suits me

The product is not meant to behave like a one-time recommendation demo.
It is meant to behave like a memory-backed style assistant that gets more useful as the user completes onboarding, adds wardrobe items, gives feedback, and returns through chat.

## Product Definition

> A mandatory-onboarding, memory-backed personal fashion copilot that helps the user make better shopping and dressing decisions over time through intent-routed chat.

Core product principles:
- onboarding is required before first chat
- wardrobe is optional to provide, but fully supported by the system
- web handles onboarding and richer tasks
- WhatsApp handles lightweight repeat usage and retention
- every major answer should be explainable
- confidence should be visible
- safety guardrails should fail closed where needed

## User Value

For the user, the product should deliver:
- better shopping decisions before spending money
- better dressing decisions before real occasions
- wardrobe-first help instead of defaulting to new purchases
- more personalized guidance than generic styling content
- explanations grounded in the user's own profile and history
- continuity across web and WhatsApp

## Primary Personas

### 1. Practical Repeat Buyer

Needs:
- quick buy / skip guidance
- pairing suggestions before buying
- low-friction repeat use

Typical prompts:
- "Should I buy this?"
- "What would I wear this with?"
- "Show me a safer option."

### 2. Wardrobe Optimizer

Needs:
- better use of existing clothes
- occasion planning from owned items
- help filling real wardrobe gaps

Typical prompts:
- "What goes with this blazer?"
- "What should I wear tomorrow?"
- "Plan a mini capsule for my trip."
- "Build an outfit around this shirt from my wardrobe."

### 3. Style Learner

Needs:
- to understand what suits them
- transparency into why recommendations fit
- a guided path to better choices over time

Typical prompts:
- "What style suits me?"
- "Why did you recommend this?"
- "What should I avoid?"
- "What collar works best on me?"

### 4. Low-Friction Return User

Needs:
- to come back through WhatsApp without repeating context
- short answers and quick loops
- deep links to web only when necessary

Typical prompts:
- "Office dinner tomorrow"
- "Should I buy this?" + link
- "Save this to my wardrobe"

## User Journey

### Stage 1: Discovery

The user first encounters the website.

Goals:
- understand what the product helps with
- decide whether onboarding is worth the effort
- start onboarding

Expected surface:
- stylist-led landing language
- visible jobs to be done
- immediate clarity that Aura helps with dressing, pairing, checking, learning, and planning

### Stage 2: Onboarding

The user verifies identity by OTP and completes the required pre-chat contract:
- baseline profile
- required images
- style preference selection
- profile analysis

Optional:
- initial wardrobe upload

User outcome:
- the system has enough evidence to personalize future chat

### Stage 3: Processing and Unlock

The system analyzes the user's images and builds derived interpretations.
Chat remains blocked until the required onboarding state is complete.

User outcome:
- the user sees that the system is preparing a profile before giving advice

Unlock requirement:
- once analysis is complete, the user lands in a stylist dashboard rather than an empty chat box

### Stage 4: First Successful Chat

The user asks a first real question on web.

Examples:
- "What should I wear to an office dinner?"
- "What colors should I prioritise?"
- "What style suits me?"

User outcome:
- the product demonstrates profile-aware value quickly

Ideal first-session entry points:
- `Dress Me` for occasion outfits
- `Style This` for pairing
- `Check Me` for outfit critique
- `Know Me` for style advice
- `Trips` for capsule planning

### Stage 5: Memory Growth

The user saves wardrobe items, gives feedback, asks follow-up questions, and starts relying on the system for repeat decisions.

User outcome:
- the system becomes more useful with accumulated memory

### Stage 6: Repeat Usage Through WhatsApp

After onboarding, the user returns through WhatsApp for lightweight day-to-day use.

Examples:
- "Should I buy this?" + product link
- "What goes with this?" + image
- "What should I wear tomorrow?"

User outcome:
- repeat usage becomes habit-like, not novelty-like

### Stage 7: Web Return From WhatsApp

The user returns from WhatsApp through a deep link when the task needs richer visuals or more editing control.

Expected behavior:
- the same task context is visible on web
- the user lands in the relevant section, not a generic home state
- the stylist tone and source clarity remain consistent across channels

## Canonical Journey Loop

The full operating loop should be:

1. discovery on web
2. onboarding and processing
3. first value on web
4. wardrobe growth and saved-look accumulation
5. repeat day-to-day usage in chat and WhatsApp
6. return to web for richer review, wardrobe management, outfit check, or trip planning

This loop is the product’s intended habit system.

## First-Run Experience Contract

Immediately after onboarding and analysis completion, the user should land in:
- a stylist dashboard
- not an empty text field
- not a processing residue state

The first-run page should answer:
- what can Aura do for me right now
- what should I ask first
- what has Aura already learned about me
- how do I use my wardrobe with it

## Ideal First-Session Paths

### Occasion Outfit
- entry: `Dress Me`
- success condition: user receives a source-labeled occasion answer and can refine it quickly

### Pairing
- entry: `Style This` or image upload
- success condition: Aura builds around an anchor piece instead of echoing it

### Outfit Check
- entry: `Check Me` or outfit photo
- success condition: user receives a critique plus wardrobe-first swaps

### Shopping Decision
- entry: pasted product URL
- success condition: user gets buy / skip guidance plus a natural next step

### Style Advice
- entry: `Know Me`
- success condition: user understands one concrete profile-grounded styling principle

### Trip Planning
- entry: `Trips`
- success condition: user gets a duration-aware plan, not a generic short list

## Operating Surfaces

### Website

Responsibilities:
- onboarding and identity verification
- profile completion
- image upload and processing
- wardrobe management
- first successful chat
- richer visual and explanatory experiences

### WhatsApp

Responsibilities:
- repeat usage
- low-friction natural-language entry
- image / link intake
- quick answer loops
- re-engagement
- handoff back to web for heavier tasks

## Main User Stories

### US-01: Mandatory onboarding before chat

As a new user, I want onboarding to happen before chat so the advice is grounded in real evidence instead of generic guesses.

### US-02: Occasion recommendation

As an onboarded user, I want to ask what to wear for an occasion and get a useful answer based on my profile and, when available, my wardrobe first.

Expected behavior:
- wardrobe-first should work when the user wants an outfit from owned items
- catalog-only should work when the user explicitly wants options from the catalog
- the response should make the source mode explicit: wardrobe-first, catalog-only, or hybrid

### US-03: Pairing request

As an onboarded user, I want to ask what goes with a piece I own or want to buy.

Expected behavior:
- uploading a wardrobe garment image should let the user ask for the best pairing for an occasion
- uploading a catalog garment image should let the user ask for the best pairing for an occasion
- the product should pair around the garment, not repeat the garment back as the only answer
- the system should distinguish wardrobe-image vs catalog-image anchors automatically or from explicit user phrasing

### US-04: Shopping decision

As an onboarded user, I want buy / skip help before spending money on clothing.

### US-05: Wardrobe ingestion

As an onboarded user, I want to save items into my wardrobe during onboarding or later through chat.

### US-06: Style discovery

As an onboarded user, I want to understand what suits me and why.

Expected behavior:
- the user can ask broad style questions ("what style suits me?")
- the user can ask specific styling questions ("what collar / color / pattern suits me?")

### US-07: Explanation request

As an onboarded user, I want the system to explain recommendations using my actual profile, memory, wardrobe, and confidence state.

### US-08: Virtual try-on

As an onboarded user, I want to request a try-on when it is safe and the output quality passes guardrails.

### US-09: Cross-channel continuity

As a repeat user, I want the same memory and identity to carry from web to WhatsApp.

### US-10: Outfit check with wardrobe follow-up

As an onboarded user, I want to rate or check my current outfit and get suggestions for what would work better from my wardrobe.

Expected behavior:
- the critique should suggest wardrobe swaps first
- catalog follow-up should stay optional, not forced
- a later `Show me better options from the catalog` should pivot with the same outfit context

### US-11: Trip / capsule planning

As an onboarded user, I want a trip-duration-aware capsule or outfit list that combines my wardrobe first and catalog gap-fillers when needed.

Expected behavior:
- trip duration should expand the number of looks up to a bounded multi-day plan
- the plan should cover multiple contexts or dayparts, not repeated undifferentiated looks
- catalog-supported hybrid looks should appear when wardrobe depth alone cannot cover the trip

## What Success Looks Like For The User

User success is not:
- receiving one interesting answer

User success is:
- completing onboarding
- trusting the system enough to ask real questions
- coming back before real buy / wear decisions
- feeling remembered across channels
- seeing explanations and confidence when needed
- experiencing wardrobe-first value, not only catalog upsell

## First-50 Product Success

The first-50 rollout is about dependency, not generic engagement.

The product succeeds in this phase if users:
- complete onboarding
- return through WhatsApp
- use the product before real clothing decisions
- show recurring intent patterns
- build memory through wardrobe, feedback, and repeated usage

## Relationship To Other Docs

- [`docs/CURRENT_STATE.md`](CURRENT_STATE.md): **source of truth** — implementation state, execution checklist, parked architectural decisions
- [`docs/DESIGN.md`](DESIGN.md): design system, visual language, component rules
- [`docs/RELEASE_READINESS.md`](RELEASE_READINESS.md): 4-gate release checklist
- [`docs/OPERATIONS.md`](OPERATIONS.md): dashboards and SQL for the first-50 rollout
- [`docs/DESIGN_SYSTEM_VALIDATION.md`](DESIGN_SYSTEM_VALIDATION.md): manual design QA checklist
- [`docs/APPLICATION_SPECS.md`](APPLICATION_SPECS.md): runtime contract (⚠️ *partially deprecated*)
- [`docs/INTENT_COPILOT_ARCHITECTURE.md`](INTENT_COPILOT_ARCHITECTURE.md): target system design (pre-planner-inlining era)
- [`docs/WORKFLOW_REFERENCE.md`](WORKFLOW_REFERENCE.md): human-facing per-intent execution flows (not loaded at runtime)
