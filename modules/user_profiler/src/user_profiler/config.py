from dataclasses import dataclass
import os


@dataclass(frozen=True)
class UserProfilerConfig:
    # May 1, 2026: upgraded from gpt-5.4 to gpt-5.5 alongside the
    # equivalent change in modules/user/src/user/analysis.py — keeps
    # the standalone profiler runtime in sync with the in-app one.
    visual_model: str = "gpt-5.5"
    textual_model: str = "gpt-5.5"
    visual_reasoning_effort: str = "high"
    output_dir: str = "data/logs"


def _resolve_env_file(explicit_path: str | None = None) -> str:
    """Resolve which dotenv file to load. Returns empty string when no
    file should be loaded (CI / unit-test environments where the
    OPENAI_API_KEY is supplied via os.environ directly or not needed at
    all because the call site is mocked).

    May 1, 2026 (CI fix): the previous behaviour was to RAISE when no
    env file existed and no APP_ENV/ENV_FILE was set. That broke unit
    tests on CI runners where there's no .env file by design — process
    env or test mocks are the source of truth there. Production deploys
    set APP_ENV explicitly and still get the strict "file must exist"
    enforcement (see the two raises below).
    """
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
    # No env file and no APP_ENV/ENV_FILE — fine. Caller falls back to
    # whatever's in process env. _load_dotenv treats "" as a no-op.
    return ""


def _load_dotenv(dotenv_path: str | None = None) -> None:
    dotenv_path = _resolve_env_file(dotenv_path)
    if not dotenv_path or not os.path.exists(dotenv_path):
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


def get_api_key() -> str:
    """Return the OpenAI API key from env (loading .env if found).

    Returns an empty string when no key is set. Construction-time callers
    (lazy `cached_property` on each agent's `_client`) accept this; the
    actual API call fails downstream with an auth error if no real key is
    present. This shape keeps unit tests on CI runners (no env file by
    design) able to construct agents and orchestrators that get mocked
    upstream without tripping at import time.

    May 1, 2026 (CI fix): was previously a hard raise. Production
    callers that need a real key should set `APP_ENV=staging` (or
    `ENV_FILE=…`); the env-file resolver still raises if the named
    file is missing in those cases.
    """
    _load_dotenv()
    return os.getenv("OPENAI_API_KEY", "").strip()
