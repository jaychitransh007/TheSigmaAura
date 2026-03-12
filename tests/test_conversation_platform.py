import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "catalog_retrieval" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "conversation_platform" / "src",
    ROOT / "modules" / "onboarding" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from conversation_platform.config import load_config
from conversation_platform.orchestrator import ConversationOrchestrator
from conversation_platform.schemas import CreateTurnRequest


class ConversationPlatformTests(unittest.TestCase):
    def test_turn_request_minimal_contract(self) -> None:
        req = CreateTurnRequest(user_id="u1", message="Need smart casual office wear")
        self.assertEqual("u1", req.user_id)
        self.assertEqual("Need smart casual office wear", req.message)

    def test_load_config_accepts_supabase_cli_env_vars(self) -> None:
        with patch("conversation_platform.config._load_dotenv", return_value=None), patch.dict(
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

    def test_orchestrator_builds_embedding_matches_without_legacy_controls(self) -> None:
        repo = Mock()
        onboarding_repo = Mock()
        client = Mock()
        repo.client = client
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "db-user", "session_context_json": {}}
        repo.create_turn.return_value = {"id": "t1"}

        config = Mock(retrieval_match_count=3)
        analysis_payload = {
            "status": "completed",
            "profile": {"gender": "male", "style_preference": {"primaryArchetype": "classic"}},
            "attributes": {"BodyShape": {"value": "Rectangle"}},
            "derived_interpretations": {"HeightCategory": {"value": "Tall"}},
        }
        query_document = "GARMENT_REQUIREMENTS:\\n- GarmentCategory: top\\nOCCASION_AND_SIGNAL:\\n- OccasionFit: smart_casual"
        matches = [
            {
                "product_id": "sku-1",
                "metadata_json": {
                    "title": "Oxford Shirt",
                    "images__0__src": "https://img/1.jpg",
                    "price": "1999",
                    "GarmentCategory": "top",
                    "GarmentSubtype": "shirt",
                    "StylingCompleteness": "needs_pairing",
                    "PrimaryColor": "blue",
                },
                "garment_category": "top",
                "garment_subtype": "shirt",
                "styling_completeness": "needs_pairing",
                "primary_color": "blue",
                "price": "1999",
                "similarity": 0.82,
            }
        ]

        with patch("conversation_platform.orchestrator.UserAnalysisService") as analysis_cls, \
            patch("conversation_platform.orchestrator.StyleRequirementQueryBuilder") as qb_cls, \
            patch("conversation_platform.orchestrator.CatalogEmbedder") as embedder_cls, \
            patch("conversation_platform.orchestrator.SupabaseVectorStore") as store_cls:
            analysis_cls.return_value.get_analysis_status.return_value = analysis_payload
            qb_cls.return_value.build_query_document.return_value = query_document
            embedder_cls.return_value.embed_texts.return_value = [[0.1, 0.2]]
            store_cls.return_value.similarity_search.return_value = matches

            orchestrator = ConversationOrchestrator(repo=repo, onboarding_repo=onboarding_repo, config=config)
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Need smart casual office wear",
            )

        self.assertEqual("c1", result["conversation_id"])
        self.assertEqual("t1", result["turn_id"])
        self.assertEqual("masculine", result["filters_applied"]["gender_expression"])
        self.assertEqual("sku-1", result["recommendations"][0]["product_id"])
        self.assertIn("embedding matches", result["assistant_message"])


if __name__ == "__main__":
    unittest.main()
