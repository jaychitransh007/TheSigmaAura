from dataclasses import dataclass
import os


MANDATORY_COLUMNS = ["description", "images__0__src", "images__1__src"]


@dataclass(frozen=True)
class PipelineConfig:
    model: str = "gpt-5-mini"
    endpoint: str = "/v1/responses"
    completion_window: str = "24h"
    poll_interval_seconds: int = 30
    max_wait_minutes: int = 180
    output_dir: str = "out"


def _load_dotenv(dotenv_path: str = ".env") -> None:
    env_file = os.getenv("ENV_FILE", "").strip()
    app_env = os.getenv("APP_ENV", "").strip().lower()
    if dotenv_path == ".env":
        if env_file:
            dotenv_path = env_file
        elif app_env == "staging":
            dotenv_path = ".env.staging"
        elif app_env == "local" or os.path.exists(".env.local"):
            dotenv_path = ".env.local"
        else:
            raise RuntimeError("Set APP_ENV=local or APP_ENV=staging, or provide ENV_FILE explicitly.")
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
