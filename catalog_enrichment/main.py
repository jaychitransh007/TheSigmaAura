import argparse
import os

from .batch_builder import build_batch_input_jsonl, build_retry_batch_input_jsonl
from .batch_runner import BatchRunner, extract_file_ids, save_batch_metadata
from .config import PipelineConfig, get_api_key
from .csv_io import read_csv_rows
from .merge_writer import merge_rows, write_csv
from .quality import build_run_report, write_report
from .response_parser import parse_batch_output_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch garment attribute enrichment pipeline.")
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output enriched CSV path.")
    parser.add_argument(
        "--mode",
        choices=["prepare", "run_batch", "merge", "all"],
        default="prepare",
        help="Pipeline step to run.",
    )
    parser.add_argument("--out-dir", default="out", help="Working directory for batch artifacts.")
    parser.add_argument("--batch-input-jsonl", default="", help="Optional explicit path for batch input jsonl.")
    parser.add_argument("--batch-output-jsonl", default="", help="Optional explicit path for batch output jsonl.")
    parser.add_argument(
        "--num-products",
        choices=["5", "all"],
        default="5",
        help="Safety limit for product rows to process. Default is 5.",
    )
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    config = PipelineConfig(output_dir=args.out_dir)

    batch_input_jsonl = args.batch_input_jsonl or os.path.join(args.out_dir, "batch_input.jsonl")
    batch_output_jsonl = args.batch_output_jsonl or os.path.join(args.out_dir, "batch_output.jsonl")
    batch_errors_jsonl = os.path.join(args.out_dir, "batch_errors.jsonl")
    batch_meta_json = os.path.join(args.out_dir, "batch_metadata.json")
    report_json = os.path.join(args.out_dir, "run_report.json")
    retry_jsonl = os.path.join(args.out_dir, "retry_batch_input.jsonl")

    rows = read_csv_rows(args.input)
    if args.num_products == "5":
        rows = rows[:5]

    if args.mode in {"prepare", "all"}:
        build_batch_input_jsonl(rows, batch_input_jsonl, config)
        if args.mode == "prepare":
            return

    if args.mode in {"run_batch", "all"}:
        api_key = get_api_key()
        runner = BatchRunner(api_key=api_key, config=config)
        input_file_id = runner.upload_batch_file(batch_input_jsonl)
        batch_id = runner.create_batch(input_file_id)
        batch_data = runner.wait_for_completion(batch_id)
        save_batch_metadata(batch_data, batch_meta_json)

        file_ids = extract_file_ids(batch_data)
        if file_ids["output_file_id"]:
            runner.download_file_content(file_ids["output_file_id"], batch_output_jsonl)
        if file_ids["error_file_id"]:
            runner.download_file_content(file_ids["error_file_id"], batch_errors_jsonl)

        if args.mode == "run_batch":
            return

    if args.mode in {"merge", "all"}:
        parsed = parse_batch_output_jsonl(batch_output_jsonl)
        merged = merge_rows(rows, parsed)
        write_csv(merged, args.output)
        report = build_run_report(merged)
        write_report(report, report_json)
        failed_indices = [i for i, row in enumerate(merged) if row.get("row_status") != "ok"]
        if failed_indices:
            build_retry_batch_input_jsonl(rows, failed_indices, retry_jsonl, config)


if __name__ == "__main__":
    run()
