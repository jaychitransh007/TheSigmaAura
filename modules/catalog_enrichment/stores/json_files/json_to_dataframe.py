from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import json
import pandas as pd


def _flatten_list_columns(df: pd.DataFrame, sep: str = "__") -> pd.DataFrame:
    """
    Expand list columns into numbered flat columns.

    Examples:
    - variants -> variants__0__id, variants__0__price, variants__1__id, ...
    - tags -> tags__0, tags__1, ...
    """
    result = df.copy()

    list_cols = []
    for col in result.columns:
        if result[col].map(lambda v: isinstance(v, list)).any():
            list_cols.append(col)

    for col in list_cols:
        series = result[col]
        new_data: dict[str, pd.Series] = {}

        max_len = int(
            series.map(lambda v: len(v) if isinstance(v, list) else 0).max()
        )
        if max_len == 0:
            result = result.drop(columns=[col])
            continue

        # List of dicts: expand each object key into numbered columns.
        has_dict_items = series.map(
            lambda v: isinstance(v, list) and any(isinstance(x, dict) for x in v)
        ).any()

        if has_dict_items:
            key_set = set()
            for value in series:
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            key_set.update(item.keys())
            keys = sorted(key_set)

            for idx in range(max_len):
                for key in keys:
                    new_col = f"{col}{sep}{idx}{sep}{key}"
                    new_data[new_col] = series.map(
                        lambda v, i=idx, k=key: (
                            v[i].get(k)
                            if isinstance(v, list)
                            and i < len(v)
                            and isinstance(v[i], dict)
                            else None
                        )
                    )
        else:
            # List of primitives.
            for idx in range(max_len):
                new_col = f"{col}{sep}{idx}"
                new_data[new_col] = series.map(
                    lambda v, i=idx: (
                        v[i] if isinstance(v, list) and i < len(v) else None
                    )
                )

        result = pd.concat(
            [result.drop(columns=[col]), pd.DataFrame(new_data, index=result.index)],
            axis=1,
        )

    return result


def load_store_products_flat(
    file_name: str = "andamen.json",
    stores_dir: str | Path = "stores/json_files",
    sep: str = "__",
) -> pd.DataFrame:
    """
    Read a store JSON export and return a flattened DataFrame.

    The function keeps one row per product and flattens nested dict/list fields.
    List fields (for example, variants/images/options/tags) are expanded to
    numbered columns like variants__0__id, tags__0, etc.
    """
    file_path = Path(file_name)
    if file_path.is_absolute():
        path = file_path
    elif file_path.exists():
        # Support caller passing relative path like "stores/andamen.json".
        path = file_path
    else:
        # Default behavior for bare filenames like "andamen.json".
        path = Path(stores_dir) / file_path
    with path.open("r", encoding="utf-8") as f:
        payload: dict[str, Any] = json.load(f)

    products = payload.get("products", [])
    if not isinstance(products, list):
        raise ValueError("Expected top-level key 'products' to be a list.")

    df = pd.json_normalize(products, sep=sep)

    # Re-run list expansion until no list-like columns remain.
    while True:
        has_list_cols = any(
            df[col].map(lambda v: isinstance(v, list)).any() for col in df.columns
        )
        if not has_list_cols:
            break
        df = _flatten_list_columns(df, sep=sep)

    # De-fragment DataFrame after many column inserts.
    df = df.copy()
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flatten a store products JSON file.")
    parser.add_argument(
        "--file-name",
        default="andamen.json",
        help="JSON filename inside stores directory (default: andamen.json)",
    )
    parser.add_argument(
        "--stores-dir",
        default="stores/json_files",
        help="Directory containing store JSON files (default: stores/json_files)",
    )
    args = parser.parse_args()

    dataframe = load_store_products_flat(
        file_name=args.file_name,
        stores_dir=args.stores_dir,
    )
    print(f"Rows: {len(dataframe)}, Columns: {len(dataframe.columns)}")
    print(dataframe.head(3).to_string(index=False))
