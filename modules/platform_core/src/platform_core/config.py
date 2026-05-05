from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AuraRuntimeConfig:
    supabase_rest_url: str
    supabase_service_role_key: str
    catalog_csv_path: str = "data/catalog/enriched_catalog_upload.csv"
    retrieval_match_count: int = 12
    request_timeout_seconds: int = 30
    # Reasoning effort the OutfitArchitect passes via the Responses API
    # `reasoning.effort` parameter. May 5, 2026 set this explicitly to
    # "medium" alongside the gpt-5.5 → gpt-5.4 model swap — going both
    # cheaper-model AND lower-effort at once would compound quality
    # risk on the agent that drives retrieval quality across the whole
    # pipeline. Override per-environment via ARCHITECT_REASONING_EFFORT
    # (low | medium | high). See docs/OPEN_TASKS.md for the
    # measure-and-decide entry that backs both defaults.
    architect_reasoning_effort: str = "medium"


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

    architect_effort = os.getenv("ARCHITECT_REASONING_EFFORT", "").strip().lower() or "medium"
    if architect_effort not in {"low", "medium", "high"}:
        # Unknown values fall back to "medium" rather than failing app
        # start. OpenAI may add or rename values; we'd rather degrade
        # than crash.
        architect_effort = "medium"

    return AuraRuntimeConfig(
        supabase_rest_url=_ensure_rest_url(supabase_url),
        supabase_service_role_key=service_key,
        catalog_csv_path=catalog_csv_path,
        architect_reasoning_effort=architect_effort,
    )
