from dataclasses import dataclass
import os


@dataclass(frozen=True)
class UserProfilerConfig:
    visual_model: str = "gpt-5.2"
    textual_model: str = "gpt-5-mini"
    visual_reasoning_effort: str = "high"
    output_dir: str = "data/logs"


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


def get_api_key() -> str:
    _load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in environment or .env file.")
    return api_key
