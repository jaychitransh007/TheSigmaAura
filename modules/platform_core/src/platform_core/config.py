from dataclasses import dataclass
import os

from platform_core.reasoning_effort import GPT5_MID_EFFORTS


@dataclass(frozen=True)
class AuraRuntimeConfig:
    supabase_rest_url: str
    supabase_service_role_key: str
    catalog_csv_path: str = "data/catalog/enriched_catalog_upload.csv"
    retrieval_match_count: int = 12
    request_timeout_seconds: int = 30
    # Reasoning effort the OutfitArchitect passes via the Responses API
    # `reasoning.effort` parameter. Stepped from "medium" → "low" on
    # the May-5 latency-fix pass after the turn audit showed architect
    # at 88.9s with 6.5K output tokens — most of those tokens were
    # reasoning the structured-output task doesn't need. "low" remains
    # the right setting for gpt-5.2 (Phase 1.4 swap, May 13 2026):
    # gpt-5-mini at "minimal" produced low-quality outputs (rater
    # fashion_score collapsed to 50-65 on a wedding query); gpt-5.2 at
    # "low" recovered quality (top=96) with ~10s latency win vs gpt-5.4.
    # Override per-environment via ARCHITECT_REASONING_EFFORT
    # (low | medium | high | xhigh — full gpt-5.x reasoning vocabulary).
    architect_reasoning_effort: str = "low"

    # Phase 1.4 latency push (May 13 2026): every agent's model string
    # is exposed as an env var so per-environment swaps don't require
    # a code change. Defaults reflect the production lineup as of the
    # 1.4 swap — architect + composer moved gpt-5.4 → gpt-5.2 after
    # staging validation showed equivalent quality with ~10s latency
    # win. Planner / rater / style_advisor stayed on their existing
    # models (gpt-5-mini for the two minimal-reasoning callers,
    # gpt-5.4 for the open-ended advisor — gpt-5.2 untested there).
    # Cross-vendor swaps (claude-sonnet-4-7, gemini-2.5-pro) require
    # a vendor adapter and are not supported via these env vars.
    planner_model: str = "gpt-5-mini"
    architect_model: str = "gpt-5.2"
    composer_model: str = "gpt-5.2"
    rater_model: str = "gpt-5-mini"
    style_advisor_model: str = "gpt-5.4"

    # Phase 4.10 — staged rollout of the composition engine. 0 = always
    # take the LLM architect path (default until ops flips it on);
    # 100 = always try the engine first. Values in between deterministically
    # bucket users by user_id so per-cohort metrics stay attributable.
    composition_rollout_pct: int = 0


def _resolve_env_file(explicit_path: str | None = None) -> str:
    if explicit_path:
        return explicit_path
    env_file = os.getenv("ENV_FILE", "").strip()
    if env_file:
        return env_file
    app_env = os.getenv("APP_ENV", "").strip().lower()
    if app_env == "staging":
        if not os.path.exists(".env.staging"):
            raise RuntimeError("APP_ENV=staging requires .env.staging to exist.")
        return ".env.staging"
    if app_env == "local":
        if not os.path.exists(".env.local"):
            raise RuntimeError("APP_ENV=local requires .env.local to exist.")
        return ".env.local"
    if os.path.exists(".env.local"):
        return ".env.local"
    raise RuntimeError("Set APP_ENV=local or APP_ENV=staging, or provide ENV_FILE explicitly.")


def _load_dotenv(dotenv_path: str | None = None) -> None:
    dotenv_path = _resolve_env_file(dotenv_path)
    if not os.path.exists(dotenv_path):
        return

    with open(dotenv_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ[key] = value


def _ensure_rest_url(base: str) -> str:
    url = base.rstrip("/")
    if url.endswith("/rest/v1"):
        return url
    return f"{url}/rest/v1"


def load_config() -> AuraRuntimeConfig:
    _load_dotenv()

    supabase_url = (
        os.getenv("SUPABASE_URL", "").strip()
        or os.getenv("API_URL", "").strip()
        or "http://127.0.0.1:55321"
    )
    service_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SECRET_KEY", "").strip()
    )
    if not service_key:
        raise RuntimeError(
            "Missing service key. Set SUPABASE_SERVICE_ROLE_KEY, "
            "or export SERVICE_ROLE_KEY from `supabase status --output env`."
        )

    catalog_csv_path = (
        os.getenv("CATALOG_CSV_PATH", "data/catalog/enriched_catalog_upload.csv").strip()
        or "data/catalog/enriched_catalog_upload.csv"
    )

    # Architect runs on gpt-5.4 (gpt-5-mid family). Validation set
    # imported from platform_core.reasoning_effort (top of file) so
    # this env-loader stays in sync with the architect's own
    # constructor validation.
    architect_effort = os.getenv("ARCHITECT_REASONING_EFFORT", "").strip().lower() or "low"
    if architect_effort not in GPT5_MID_EFFORTS:
        # Unknown values fall back to "low" rather than failing app
        # start. OpenAI may add or rename values; we'd rather degrade
        # than crash.
        architect_effort = "low"

    # Phase 1.4: every agent's model is overridable via env. Trim +
    # fallback on empty so an unset var keeps the production default;
    # fallback references the dataclass attribute so a single edit to
    # the class default also moves the env-loader's default.
    planner_model = os.getenv("PLANNER_MODEL", "").strip() or AuraRuntimeConfig.planner_model
    architect_model = os.getenv("ARCHITECT_MODEL", "").strip() or AuraRuntimeConfig.architect_model
    composer_model = os.getenv("COMPOSER_MODEL", "").strip() or AuraRuntimeConfig.composer_model
    rater_model = os.getenv("RATER_MODEL", "").strip() or AuraRuntimeConfig.rater_model
    style_advisor_model = os.getenv("STYLE_ADVISOR_MODEL", "").strip() or AuraRuntimeConfig.style_advisor_model

    # Phase 4.10 rollout pct. Bad values clamp to [0, 100] rather than
    # crashing app start — degraded operation beats outage on a misset
    # ops env var.
    rollout_raw = os.getenv("AURA_COMPOSITION_ROLLOUT_PCT", "").strip()
    try:
        composition_rollout_pct = int(rollout_raw) if rollout_raw else AuraRuntimeConfig.composition_rollout_pct
    except ValueError:
        composition_rollout_pct = AuraRuntimeConfig.composition_rollout_pct
    composition_rollout_pct = max(0, min(100, composition_rollout_pct))

    return AuraRuntimeConfig(
        supabase_rest_url=_ensure_rest_url(supabase_url),
        supabase_service_role_key=service_key,
        catalog_csv_path=catalog_csv_path,
        architect_reasoning_effort=architect_effort,
        planner_model=planner_model,
        architect_model=architect_model,
        composer_model=composer_model,
        rater_model=rater_model,
        style_advisor_model=style_advisor_model,
        composition_rollout_pct=composition_rollout_pct,
    )
