# Product Overview

Last updated: March 19, 2026

## Purpose

Sigma Aura is a personal fashion copilot.

For a user, it is meant to become a repeat-use assistant for real clothing decisions:
- what should I wear
- what goes with this piece
- should I buy this
- how would this look on me
- how do I plan from what I already own

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

### 3. Style Learner

Needs:
- to understand what suits them
- transparency into why recommendations fit
- a guided path to better choices over time

Typical prompts:
- "What style suits me?"
- "Why did you recommend this?"
- "What should I avoid?"

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

### Stage 4: First Successful Chat

The user asks a first real question on web.

Examples:
- "What should I wear to an office dinner?"
- "What colors should I prioritise?"
- "What style suits me?"

User outcome:
- the product demonstrates profile-aware value quickly

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

### US-03: Pairing request

As an onboarded user, I want to ask what goes with a piece I own or want to buy.

### US-04: Shopping decision

As an onboarded user, I want buy / skip help before spending money on clothing.

### US-05: Wardrobe ingestion

As an onboarded user, I want to save items into my wardrobe during onboarding or later through chat.

### US-06: Style discovery

As an onboarded user, I want to understand what suits me and why.

### US-07: Explanation request

As an onboarded user, I want the system to explain recommendations using my actual profile, memory, wardrobe, and confidence state.

### US-08: Virtual try-on

As an onboarded user, I want to request a try-on when it is safe and the output quality passes guardrails.

### US-09: Cross-channel continuity

As a repeat user, I want the same memory and identity to carry from web to WhatsApp.

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

- [`docs/CURRENT_STATE.md`](/Users/mj/Projects/TheSigmaProject/Aura/docs/CURRENT_STATE.md): implementation state and execution checklist
- [`docs/APPLICATION_SPECS.md`](/Users/mj/Projects/TheSigmaProject/Aura/docs/APPLICATION_SPECS.md): runtime and implementation contract
- [`docs/INTENT_COPILOT_ARCHITECTURE.md`](/Users/mj/Projects/TheSigmaProject/Aura/docs/INTENT_COPILOT_ARCHITECTURE.md): system design and boundaries
