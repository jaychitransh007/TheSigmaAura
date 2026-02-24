from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ConversationPlatformConfig:
    supabase_rest_url: str
    supabase_service_role_key: str
    catalog_csv_path: str = "data/output/enriched.csv"
    default_strictness: str = "balanced"
    default_hard_filter_profile: str = "rl_ready_minimal"
    default_max_results: int = 12
    request_timeout_seconds: int = 30


def _load_dotenv(dotenv_path: str = ".env") -> None:
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
            if key and key not in os.environ:
                os.environ[key] = value


def _ensure_rest_url(base: str) -> str:
    url = base.rstrip("/")
    if url.endswith("/rest/v1"):
        return url
    return f"{url}/rest/v1"


def load_config() -> ConversationPlatformConfig:
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

    catalog_csv_path = os.getenv("CATALOG_CSV_PATH", "data/output/enriched.csv").strip() or "data/output/enriched.csv"

    return ConversationPlatformConfig(
        supabase_rest_url=_ensure_rest_url(supabase_url),
        supabase_service_role_key=service_key,
        catalog_csv_path=catalog_csv_path,
    )
