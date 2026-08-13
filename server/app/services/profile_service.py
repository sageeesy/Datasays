"""Compact, JSON-safe dataset profiling used by planning and validation."""

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd


PROFILE_VERSION = "1.0"
MAX_SAMPLE_VALUES = 5


def _json_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def _normalized_name(name: str) -> str:
    return "".join(character.lower() for character in str(name) if character.isalnum())


def _looks_like_identifier(name: str, series: pd.Series, row_count: int) -> bool:
    normalized = _normalized_name(name)
    name_signal = normalized.endswith("id") or normalized in {
        "id", "userid", "customerid", "accountid", "orderid", "transactionid", "subscriptionid"
    }
    uniqueness = series.nunique(dropna=True) / max(row_count, 1)
    return name_signal or (uniqueness >= 0.98 and not pd.api.types.is_float_dtype(series))


def _date_profile(series: pd.Series) -> Dict[str, Any] | None:
    if pd.api.types.is_datetime64_any_dtype(series):
        parsed = pd.to_datetime(series, errors="coerce")
    elif pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        non_null = series.dropna()
        if non_null.empty:
            return None
        sample = non_null.head(500)
        try:
            parsed_sample = pd.to_datetime(sample, errors="coerce", format="mixed")
        except (TypeError, ValueError):
            parsed_sample = pd.to_datetime(sample, errors="coerce")
        if float(parsed_sample.notna().mean()) < 0.8:
            return None
        try:
            parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        except (TypeError, ValueError):
            parsed = pd.to_datetime(series, errors="coerce")
    else:
        return None

    valid = parsed.dropna()
    if valid.empty:
        return None
    return {
        "parse_rate": round(float(parsed.notna().mean()), 4),
        "min": valid.min().isoformat(),
        "max": valid.max().isoformat(),
    }


def _column_profile(name: str, series: pd.Series, row_count: int) -> Dict[str, Any]:
    non_null = series.dropna()
    distinct_count = int(series.nunique(dropna=True))
    null_count = int(series.isna().sum())
    date_info = _date_profile(series)
    is_identifier = _looks_like_identifier(name, series, row_count)
    is_numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)

    if is_identifier:
        role = "identifier"
    elif date_info:
        role = "time"
    elif is_numeric:
        role = "measure"
    elif distinct_count <= max(50, int(row_count * 0.2)):
        role = "dimension"
    else:
        role = "text"

    profile: Dict[str, Any] = {
        "name": str(name),
        "dtype": str(series.dtype),
        "semantic_role": role,
        "null_count": null_count,
        "null_rate": round(null_count / max(row_count, 1), 4),
        "distinct_count": distinct_count,
        "distinct_rate": round(distinct_count / max(row_count, 1), 4),
        "sample_values": [_json_value(value) for value in non_null.drop_duplicates().head(MAX_SAMPLE_VALUES)],
    }

    if is_numeric and not non_null.empty:
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
        if not numeric.empty:
            profile["numeric_summary"] = {
                "min": _json_value(numeric.min()),
                "max": _json_value(numeric.max()),
                "mean": _json_value(numeric.mean()),
                "median": _json_value(numeric.median()),
            }
    if date_info:
        profile["date_summary"] = date_info
    return profile


def build_dataset_profile(file_path: str | Path, file_name: str | None = None) -> Dict[str, Any]:
    path = Path(file_path)
    dataframe = pd.read_csv(path, low_memory=False)
    row_count = len(dataframe)
    columns = [_column_profile(str(name), dataframe[name], row_count) for name in dataframe.columns]
    duplicate_rows = int(dataframe.duplicated().sum())

    return {
        "profile_version": PROFILE_VERSION,
        "file_name": file_name or path.name,
        "row_count": row_count,
        "column_count": len(dataframe.columns),
        "duplicate_rows": duplicate_rows,
        "duplicate_rate": round(duplicate_rows / max(row_count, 1), 4),
        "candidate_keys": [item["name"] for item in columns if item["semantic_role"] == "identifier"],
        "candidate_measures": [item["name"] for item in columns if item["semantic_role"] == "measure"],
        "candidate_dimensions": [item["name"] for item in columns if item["semantic_role"] == "dimension"],
        "date_columns": [item["name"] for item in columns if item["semantic_role"] == "time"],
        "columns": columns,
    }


def compact_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Keep prompt context informative without sending an exhaustive report."""
    return {
        "file_name": profile.get("file_name"),
        "row_count": profile.get("row_count"),
        "column_count": profile.get("column_count"),
        "duplicate_rate": profile.get("duplicate_rate"),
        "candidate_keys": profile.get("candidate_keys", []),
        "candidate_measures": profile.get("candidate_measures", []),
        "candidate_dimensions": profile.get("candidate_dimensions", []),
        "date_columns": profile.get("date_columns", []),
        "columns": [
            {
                "name": item.get("name"),
                "dtype": item.get("dtype"),
                "semantic_role": item.get("semantic_role"),
                "null_rate": item.get("null_rate"),
                "distinct_count": item.get("distinct_count"),
                "sample_values": item.get("sample_values", [])[:3],
                **({"numeric_summary": item["numeric_summary"]} if item.get("numeric_summary") else {}),
                **({"date_summary": item["date_summary"]} if item.get("date_summary") else {}),
            }
            for item in profile.get("columns", [])
        ],
    }
