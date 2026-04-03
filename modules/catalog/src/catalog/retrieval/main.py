import argparse

from .config import CatalogEmbeddingConfig
from .document_builder import iter_catalog_documents
from .embedder import CatalogEmbedder
from .repository import build_catalog_enriched_rows, read_catalog_rows, write_jsonl
from .vector_store import SupabaseVectorStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build catalog embedding documents and optional embeddings.")
    parser.add_argument("--input", default="data/catalog/enriched_catalog_upload.csv", help="Input enriched catalog CSV path.")
    parser.add_argument("--documents-output", default="data/catalog/embeddings/catalog_documents.jsonl", help="Output JSONL path for embedding documents.")
    parser.add_argument("--embeddings-output", default="data/catalog/embeddings/catalog_embeddings.jsonl", help="Output JSONL path for generated embeddings.")
    parser.add_argument("--model", default="text-embedding-3-small", help="Embedding model name.")
    parser.add_argument("--dimensions", type=int, default=1536, help="Embedding dimensions.")
    parser.add_argument("--max-rows", type=int, default=0, help="Generate documents/embeddings only for the first N eligible rows. Use 0 for all.")
    parser.add_argument("--max-description-chars", type=int, default=700, help="Max cleaned description chars in the embedding document.")
    parser.add_argument("--include-incomplete", action="store_true", help="Include non-complete rows for debugging.")
    parser.add_argument("--embed", action="store_true", help="Call the embedding API after document generation.")
    parser.add_argument("--save-supabase", action="store_true", help="Persist generated embeddings into Supabase catalog_item_embeddings.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = CatalogEmbeddingConfig(
        input_csv_path=args.input,
        documents_output_path=args.documents_output,
        embeddings_output_path=args.embeddings_output,
        embedding_model=args.model,
        embedding_dimensions=args.dimensions,
        max_rows=args.max_rows,
        max_description_chars=args.max_description_chars,
        require_complete_rows_only=not args.include_incomplete,
    )
    rows = read_catalog_rows(config.input_csv_path)
    documents = list(iter_catalog_documents(rows, config))
    write_jsonl(config.documents_output_path, [doc.as_dict() for doc in documents])
    if args.embed:
        embedder = CatalogEmbedder(config)
        embeddings = embedder.embed_documents(documents)
        write_jsonl(config.embeddings_output_path, [record.as_dict() for record in embeddings])
        if args.save_supabase:
            vector_store = SupabaseVectorStore()
            vector_store.upsert_catalog_enriched(build_catalog_enriched_rows(rows))
            vector_store.insert_embeddings(embeddings)
    elif args.save_supabase:
        vector_store = SupabaseVectorStore()
        vector_store.upsert_catalog_enriched(build_catalog_enriched_rows(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
