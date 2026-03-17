import argparse
import csv
import json
import os
from typing import Any, Dict, List, Tuple

from .audit import run_schema_audit, write_audit_report
from .batch_builder import build_batch_input_jsonl, build_request_body, build_retry_batch_input_jsonl
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
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip pre-run schema/prompt audit.",
    )
    parser.add_argument(
        "--auto-chunk",
        action="store_true",
        help="Automatically split large catalogs into multiple batch files and merge final output.",
    )
    parser.add_argument(
        "--max-batch-bytes",
        type=int,
        default=180_000_000,
        help="Max input JSONL size in bytes per batch chunk when --auto-chunk is enabled.",
    )
    return parser.parse_args()


def _request_line_bytes(row: Dict[str, str], idx: int, config: PipelineConfig) -> int:
    req = {
        "custom_id": f"row_{idx}",
        "method": "POST",
        "url": config.endpoint,
        "body": build_request_body(row, config),
    }
    return len(json.dumps(req, ensure_ascii=True).encode("utf-8")) + 1


def _is_enqueued_token_limit_error(message: str) -> bool:
    text = (message or "").lower()
    return (
        "enqueued token limit reached" in text
        or ("enqueued token" in text and "limit" in text)
    )


def _is_billing_hard_limit_error(message: str) -> bool:
    text = (message or "").lower()
    return "billing_hard_limit_reached" in text or "billing hard limit has been reached" in text


def _extract_batch_error_message(batch_data: Dict[str, Any]) -> str:
    errors = batch_data.get("errors")
    if isinstance(errors, dict):
        data = errors.get("data")
        if isinstance(data, list):
            parts: List[str] = []
            for item in data:
                if isinstance(item, dict):
                    code = item.get("code", "")
                    message = item.get("message", "")
                    if code or message:
                        parts.append(f"{code}: {message}".strip(": "))
            if parts:
                return " | ".join(parts)
    return ""


def _split_chunk_for_retry(chunk_rows: List[Dict[str, str]]) -> List[List[Dict[str, str]]]:
    if len(chunk_rows) < 2:
        return []
    midpoint = len(chunk_rows) // 2
    left = chunk_rows[:midpoint]
    right = chunk_rows[midpoint:]
    return [left, right]


def _read_any_csv_rows(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            return []
        return list(reader)


def _write_raw_rows_csv(rows: List[Dict[str, str]], output_csv_path: str) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(output_csv_path, "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_resume_artifacts(
    *,
    out_dir: str,
    pending_chunks: List[List[Dict[str, str]]],
    completed_chunks: int,
    partial_rows: List[Dict[str, Any]],
    output_path: str,
) -> Dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    pending_dir = os.path.join(out_dir, "pending_chunks")
    os.makedirs(pending_dir, exist_ok=True)

    for entry in os.listdir(pending_dir):
        if entry.startswith("pending_chunk_") and entry.endswith(".csv"):
            try:
                os.remove(os.path.join(pending_dir, entry))
            except OSError:
                pass

    pending_files: List[str] = []
    for idx, chunk_rows in enumerate(pending_chunks, start=1):
        pending_csv = os.path.join(pending_dir, f"pending_chunk_{idx:04d}.csv")
        _write_raw_rows_csv(chunk_rows, pending_csv)
        pending_files.append(pending_csv)

    partial_output_path = os.path.join(out_dir, "partial_enriched.csv")
    if partial_rows:
        write_csv(partial_rows, partial_output_path)

    checkpoint = {
        "status": "paused",
        "reason": "org_limit",
        "completed_chunks": completed_chunks,
        "pending_chunks": len(pending_chunks),
        "pending_chunk_files": pending_files,
        "partial_output_path": partial_output_path if partial_rows else "",
        "target_output_path": output_path,
    }
    checkpoint_path = os.path.join(out_dir, "auto_chunk_checkpoint.json")
    with open(checkpoint_path, "w", encoding="utf-8") as checkpoint_file:
        json.dump(checkpoint, checkpoint_file, ensure_ascii=True, indent=2)
    checkpoint["checkpoint_path"] = checkpoint_path
    return checkpoint


def _load_resume_checkpoint(
    *,
    out_dir: str,
    target_output_path: str,
) -> Tuple[List[Dict[str, Any]], List[List[Dict[str, str]]], int]:
    checkpoint_path = os.path.join(out_dir, "auto_chunk_checkpoint.json")
    if not os.path.exists(checkpoint_path):
        return [], [], 0

    with open(checkpoint_path, "r", encoding="utf-8") as checkpoint_file:
        checkpoint = json.load(checkpoint_file)

    if checkpoint.get("status") != "paused":
        return [], [], 0

    expected_target = os.path.normpath(str(checkpoint.get("target_output_path", "")))
    incoming_target = os.path.normpath(target_output_path)
    if expected_target and expected_target != incoming_target:
        return [], [], 0

    partial_rows: List[Dict[str, Any]] = []
    partial_path = str(checkpoint.get("partial_output_path", "") or "")
    if partial_path and os.path.exists(partial_path):
        partial_rows = _read_any_csv_rows(partial_path)

    pending_chunks: List[List[Dict[str, str]]] = []
    for pending_file in checkpoint.get("pending_chunk_files") or []:
        if isinstance(pending_file, str) and os.path.exists(pending_file):
            pending_chunks.append(read_csv_rows(pending_file))

    if not pending_chunks:
        return [], [], 0

    completed_chunks = int(checkpoint.get("completed_chunks") or 0)
    return partial_rows, pending_chunks, completed_chunks


def _cleanup_resume_artifacts(out_dir: str) -> None:
    checkpoint_path = os.path.join(out_dir, "auto_chunk_checkpoint.json")
    pending_dir = os.path.join(out_dir, "pending_chunks")
    if os.path.exists(checkpoint_path):
        try:
            os.remove(checkpoint_path)
        except OSError:
            pass
    if os.path.isdir(pending_dir):
        for entry in os.listdir(pending_dir):
            if entry.startswith("pending_chunk_") and entry.endswith(".csv"):
                try:
                    os.remove(os.path.join(pending_dir, entry))
                except OSError:
                    pass


def _split_rows_for_max_batch_bytes(
    rows: List[Dict[str, str]],
    config: PipelineConfig,
    max_batch_bytes: int,
) -> List[List[Dict[str, str]]]:
    if max_batch_bytes <= 0:
        raise ValueError("--max-batch-bytes must be greater than 0.")

    chunks: List[List[Dict[str, str]]] = []
    current_rows: List[Dict[str, str]] = []
    current_bytes = 0

    for row in rows:
        request_bytes = _request_line_bytes(row=row, idx=len(current_rows), config=config)
        if request_bytes > max_batch_bytes:
            raise RuntimeError(
                "A single row request exceeds --max-batch-bytes. "
                "Try using a larger --max-batch-bytes or shorten row content."
            )

        if current_rows and (current_bytes + request_bytes > max_batch_bytes):
            chunks.append(current_rows)
            current_rows = [row]
            current_bytes = request_bytes
            continue

        current_rows.append(row)
        current_bytes += request_bytes

    if current_rows:
        chunks.append(current_rows)
    return chunks


def _run_auto_chunk_pipeline(
    *,
    rows: List[Dict[str, str]],
    args: argparse.Namespace,
    config: PipelineConfig,
    report_json: str,
    schema_audit_json: str,
) -> None:
    if args.mode != "all":
        raise ValueError("--auto-chunk currently supports only --mode all.")
    if args.batch_input_jsonl or args.batch_output_jsonl:
        raise ValueError("--auto-chunk does not support --batch-input-jsonl/--batch-output-jsonl overrides.")

    if not rows:
        raise ValueError("Input CSV has no rows to process.")

    if not args.skip_audit:
        audit_report = run_schema_audit()
        write_audit_report(audit_report, schema_audit_json)
        if audit_report["status"] != "pass":
            raise RuntimeError(f"Schema audit failed. See {schema_audit_json} for details.")

    chunk_root_dir = os.path.join(args.out_dir, "chunk_runs")
    os.makedirs(chunk_root_dir, exist_ok=True)

    resumed_rows, resumed_pending_chunks, resumed_completed_chunks = _load_resume_checkpoint(
        out_dir=args.out_dir,
        target_output_path=args.output,
    )

    if resumed_pending_chunks:
        merged_all_rows: List[Dict[str, Any]] = resumed_rows
        pending_chunks = resumed_pending_chunks
        completed_chunks = resumed_completed_chunks
    else:
        merged_all_rows = []
        pending_chunks = _split_rows_for_max_batch_bytes(
            rows=rows,
            config=config,
            max_batch_bytes=args.max_batch_bytes,
        )
        completed_chunks = 0

    api_key = get_api_key()
    runner = BatchRunner(api_key=api_key, config=config)

    chunk_manifest: List[Dict[str, Any]] = []
    chunk_index = completed_chunks

    while pending_chunks:
        chunk_rows = pending_chunks.pop(0)
        chunk_index += 1
        chunk_name = f"chunk_{chunk_index:04d}"
        chunk_out_dir = os.path.join(chunk_root_dir, chunk_name)
        os.makedirs(chunk_out_dir, exist_ok=True)

        batch_input_jsonl = os.path.join(chunk_out_dir, "batch_input.jsonl")
        batch_output_jsonl = os.path.join(chunk_out_dir, "batch_output.jsonl")
        batch_errors_jsonl = os.path.join(chunk_out_dir, "batch_errors.jsonl")
        batch_meta_json = os.path.join(chunk_out_dir, "batch_metadata.json")
        chunk_retry_jsonl = os.path.join(chunk_out_dir, "retry_batch_input.jsonl")
        chunk_output_csv = os.path.join(chunk_out_dir, "enriched_chunk.csv")
        chunk_report_json = os.path.join(chunk_out_dir, "run_report.json")

        build_batch_input_jsonl(chunk_rows, batch_input_jsonl, config)

        try:
            input_file_id = runner.upload_batch_file(batch_input_jsonl)
            batch_id = runner.create_batch(input_file_id)
            batch_data = runner.wait_for_completion(batch_id)
            save_batch_metadata(batch_data, batch_meta_json)
        except Exception as exc:
            error_message = str(exc)
            if _is_billing_hard_limit_error(error_message):
                pending_chunks = [chunk_rows] + pending_chunks
                resume = _write_resume_artifacts(
                    out_dir=args.out_dir,
                    pending_chunks=pending_chunks,
                    completed_chunks=chunk_index - 1,
                    partial_rows=merged_all_rows,
                    output_path=args.output,
                )
                raise RuntimeError(
                    "Billing hard limit reached. Progress checkpointed. "
                    f"Completed chunks: {resume['completed_chunks']}, pending chunks: {resume['pending_chunks']}. "
                    f"Checkpoint: {resume['checkpoint_path']}. "
                    "After topping up billing, rerun the same command to resume."
                ) from exc
            if _is_enqueued_token_limit_error(error_message):
                split_chunks = _split_chunk_for_retry(chunk_rows)
                if split_chunks:
                    pending_chunks = split_chunks + pending_chunks
                    chunk_index -= 1
                    continue
                pending_chunks = [chunk_rows] + pending_chunks
                resume = _write_resume_artifacts(
                    out_dir=args.out_dir,
                    pending_chunks=pending_chunks,
                    completed_chunks=chunk_index - 1,
                    partial_rows=merged_all_rows,
                    output_path=args.output,
                )
                raise RuntimeError(
                    "Organization enqueued token limit reached. Progress checkpointed. "
                    f"Completed chunks: {resume['completed_chunks']}, pending chunks: {resume['pending_chunks']}. "
                    f"Checkpoint: {resume['checkpoint_path']}. "
                    "Rerun the same command after in-progress batches complete."
                ) from exc
            raise

        file_ids = extract_file_ids(batch_data)
        if not file_ids["output_file_id"]:
            batch_error = _extract_batch_error_message(batch_data)
            status = str(batch_data.get("status", "unknown"))
            if _is_enqueued_token_limit_error(batch_error):
                split_chunks = _split_chunk_for_retry(chunk_rows)
                if split_chunks:
                    pending_chunks = split_chunks + pending_chunks
                    chunk_index -= 1
                    continue
                pending_chunks = [chunk_rows] + pending_chunks
                resume = _write_resume_artifacts(
                    out_dir=args.out_dir,
                    pending_chunks=pending_chunks,
                    completed_chunks=chunk_index - 1,
                    partial_rows=merged_all_rows,
                    output_path=args.output,
                )
                raise RuntimeError(
                    "Organization enqueued token limit reached. Progress checkpointed. "
                    f"Completed chunks: {resume['completed_chunks']}, pending chunks: {resume['pending_chunks']}. "
                    f"Checkpoint: {resume['checkpoint_path']}. "
                    "Rerun the same command after in-progress batches complete."
                )
            if _is_billing_hard_limit_error(batch_error):
                pending_chunks = [chunk_rows] + pending_chunks
                resume = _write_resume_artifacts(
                    out_dir=args.out_dir,
                    pending_chunks=pending_chunks,
                    completed_chunks=chunk_index - 1,
                    partial_rows=merged_all_rows,
                    output_path=args.output,
                )
                raise RuntimeError(
                    "Billing hard limit reached. Progress checkpointed. "
                    f"Completed chunks: {resume['completed_chunks']}, pending chunks: {resume['pending_chunks']}. "
                    f"Checkpoint: {resume['checkpoint_path']}. "
                    "After topping up billing, rerun the same command to resume."
                )
            raise RuntimeError(
                f"Batch chunk {chunk_name} completed without output file. status={status}. error={batch_error}"
            )

        runner.download_file_content(file_ids["output_file_id"], batch_output_jsonl)
        if file_ids["error_file_id"]:
            runner.download_file_content(file_ids["error_file_id"], batch_errors_jsonl)

        parsed = parse_batch_output_jsonl(batch_output_jsonl)
        chunk_merged_rows = merge_rows(chunk_rows, parsed)
        write_csv(chunk_merged_rows, chunk_output_csv)

        chunk_report = build_run_report(chunk_merged_rows)
        write_report(chunk_report, chunk_report_json)

        failed_indices = [i for i, row in enumerate(chunk_merged_rows) if row.get("row_status") != "ok"]
        if failed_indices:
            build_retry_batch_input_jsonl(chunk_rows, failed_indices, chunk_retry_jsonl, config)

        merged_all_rows.extend(chunk_merged_rows)
        chunk_manifest.append(
            {
                "chunk_name": chunk_name,
                "rows": len(chunk_rows),
                "ok_rows": chunk_report["ok_rows"],
                "errored_rows": chunk_report["errored_rows"],
                "batch_id": batch_id,
                "output_csv": chunk_output_csv,
                "out_dir": chunk_out_dir,
            }
        )

    write_csv(merged_all_rows, args.output)
    final_report = build_run_report(merged_all_rows)
    final_report["auto_chunk"] = {
        "enabled": True,
        "max_batch_bytes": args.max_batch_bytes,
        "retry_split_on_token_limit": True,
        "checkpoint_on_org_limits": True,
        "resumed_from_checkpoint": resumed_completed_chunks > 0,
        "chunk_count": len(chunk_manifest) + resumed_completed_chunks,
    }
    write_report(final_report, report_json)

    chunk_manifest_json = os.path.join(args.out_dir, "chunk_manifest.json")
    with open(chunk_manifest_json, "w", encoding="utf-8") as manifest_file:
        json.dump({"chunks": chunk_manifest, "resumed_completed_chunks": resumed_completed_chunks}, manifest_file, ensure_ascii=True, indent=2)

    _cleanup_resume_artifacts(args.out_dir)


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
    schema_audit_json = os.path.join(args.out_dir, "schema_audit.json")

    rows = read_csv_rows(args.input)
    if args.num_products == "5":
        rows = rows[:5]

    if args.auto_chunk:
        _run_auto_chunk_pipeline(
            rows=rows,
            args=args,
            config=config,
            report_json=report_json,
            schema_audit_json=schema_audit_json,
        )
        return

    if args.mode in {"prepare", "run_batch", "all"} and not args.skip_audit:
        audit_report = run_schema_audit()
        write_audit_report(audit_report, schema_audit_json)
        if audit_report["status"] != "pass":
            raise RuntimeError(
                "Schema audit failed. See "
                f"{schema_audit_json} for details."
            )

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
