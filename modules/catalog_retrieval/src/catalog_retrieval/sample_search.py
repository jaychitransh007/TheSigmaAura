import argparse
import json
from onboarding.analysis import UserAnalysisService
from onboarding.repository import OnboardingRepository

from .config import CatalogEmbeddingConfig
from .embedder import CatalogEmbedder
from .query_builder import RetrievalQueryInput, StyleRequirementQueryBuilder
from .vector_store import SupabaseVectorStore, _load_supabase_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a sample LLM-driven catalog similarity search.")
    parser.add_argument("--user-id", required=True, help="Onboarded user id to build retrieval context from.")
    parser.add_argument("--need", required=True, help="Immediate user need/request, e.g. 'wedding guest dress'.")
    parser.add_argument("--occasion", default="", help="Occasion context.")
    parser.add_argument("--style-goal", default="", help="Additional styling goal, e.g. 'need to look tall'.")
    parser.add_argument("--top-k", type=int, default=10, help="Similarity search result count.")
    return parser.parse_args()


def _sample_filters(profile: dict, user_context: dict) -> dict:
    filters = {}
    gender = str(profile.get("gender") or "").strip().lower()
    if gender == "male":
        filters["gender_expression"] = "masculine"
    elif gender == "female":
        filters["gender_expression"] = "feminine"
    occasion = str(user_context.get("occasion") or "").strip().lower().replace(" ", "_")
    if occasion:
        filters["occasion_fit"] = occasion
    return filters


def main() -> int:
    args = parse_args()
    client = _load_supabase_client()
    onboarding_repo = OnboardingRepository(client)
    analysis_service = UserAnalysisService(repo=onboarding_repo)
    profile = onboarding_repo.get_profile_by_user_id(args.user_id)
    if not profile:
        raise SystemExit(f"User not found: {args.user_id}")
    analysis_status = analysis_service.get_analysis_status(args.user_id)
    query_builder = StyleRequirementQueryBuilder()
    query_input = RetrievalQueryInput(
        profile=analysis_status.get("profile") or {},
        analysis_attributes=analysis_status.get("attributes") or {},
        derived_interpretations=analysis_status.get("derived_interpretations") or {},
        style_preference=(analysis_status.get("profile") or {}).get("style_preference") or {},
        user_need=args.need,
        user_context={"occasion": args.occasion, "style_goal": args.style_goal},
    )
    query_document = query_builder.build_query_document(query_input)

    embedder = CatalogEmbedder(CatalogEmbeddingConfig())
    vector = embedder.embed_texts([query_document])[0]
    vector_store = SupabaseVectorStore(client)
    filters = _sample_filters(profile, {"occasion": args.occasion})
    results = vector_store.similarity_search(query_embedding=vector, match_count=args.top_k, filters=filters)
    print(
        json.dumps(
            {
                "query_document": query_document,
                "filters": filters,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
