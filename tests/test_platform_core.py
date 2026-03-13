import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from platform_core.api_schemas import CreateTurnRequest
from platform_core.config import load_config


class PlatformCoreTests(unittest.TestCase):
    def test_turn_request_minimal_contract(self) -> None:
        req = CreateTurnRequest(user_id="u1", message="Need smart casual office wear")
        self.assertEqual("u1", req.user_id)
        self.assertEqual("Need smart casual office wear", req.message)

    def test_load_config_accepts_supabase_cli_env_vars(self) -> None:
        with patch("platform_core.config._load_dotenv", return_value=None), patch.dict(
            "os.environ",
            {
                "API_URL": "http://127.0.0.1:55321",
                "SERVICE_ROLE_KEY": "service-role-jwt",
            },
            clear=True,
        ):
            cfg = load_config()
        self.assertEqual("http://127.0.0.1:55321/rest/v1", cfg.supabase_rest_url)
        self.assertEqual("service-role-jwt", cfg.supabase_service_role_key)
        self.assertEqual(12, cfg.retrieval_match_count)


if __name__ == "__main__":
    unittest.main()
