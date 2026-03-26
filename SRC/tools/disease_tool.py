
# SRC/tools/disease_tool.py

from __future__ import annotations

import json
import os
import re
import difflib
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

import pandas as pd
from dotenv import load_dotenv

# Load .env for DISEASE_DB_PATH (if present)
load_dotenv()

# In-memory cache so Excel/CSV is not loaded repeatedly
_DF_CACHE: Optional[pd.DataFrame] = None
_DB_PATH_CACHE: Optional[str] = None


def _j(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False)


def _norm(s: str) -> str:
    """Normalize text keys for matching."""
    s = (s or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _split_synonyms(disease_name: str) -> List[str]:
    """
    Convert disease cell names into searchable keys.
    Examples:
      'Stripe Rust / Yellow Rust' -> ['stripe rust', 'yellow rust']
      'Hill Bunt (Stinking Smut)' -> ['hill bunt', 'stinking smut']
    """
    s = (disease_name or "").strip()

    # capture text inside parentheses as separate synonym(s)
    paren_terms = re.findall(r"\(([^)]+)\)", s)

    # remove parenthetical content from base string
    base = re.sub(r"\([^)]+\)", "", s)

    # split base on slashes and commas
    parts = re.split(r"[\/,]", base)

    # combine + normalize
    raw = parts + paren_terms
    out: List[str] = []
    seen = set()

    for x in raw:
        nx = _norm(x)
        if nx and nx not in seen:
            out.append(nx)
            seen.add(nx)

    return out


def _best_fuzzy_match(query: str, choices: List[str], cutoff: float = 0.84) -> Optional[str]:
    """
    Fuzzy match for spelling mistakes.
    cutoff=0.84 keeps it strict so we don't match wrong diseases.
    """
    if not query or not choices:
        return None
    matches = difflib.get_close_matches(query, choices, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def _resolve_db_path(base_path: str) -> str:
    """
    Supports:
      - exact path with extension: data/Wheat_disease_data.xlsx or .csv
      - base path without extension: data/Wheat_disease_data -> tries .xlsx then .csv
    """
    base_path = base_path.strip()

    if os.path.exists(base_path) and os.path.isfile(base_path):
        return base_path

    # Try common extensions if user provided no extension
    candidates = [base_path + ".xlsx", base_path + ".xls", base_path + ".csv"]
    for p in candidates:
        if os.path.exists(p) and os.path.isfile(p):
            return p

    return base_path


def _load_db(path: str) -> pd.DataFrame:
    global _DF_CACHE, _DB_PATH_CACHE

    resolved = _resolve_db_path(path)

    # Return cached if same file
    if _DF_CACHE is not None and _DB_PATH_CACHE == resolved:
        return _DF_CACHE

    if not os.path.exists(resolved):
        raise FileNotFoundError(
            f"Disease knowledge file not found. Tried: {resolved} "
            f"(also supports .xlsx/.csv if you provided base name)"
        )

    if resolved.lower().endswith(".csv"):
        # Try different encodings for CSV files
        encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
        df = None
        for enc in encodings:
            try:
                df = pd.read_csv(resolved, encoding=enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if df is None:
            raise ValueError(f"Could not read CSV with any supported encoding: {encodings}")
    else:
        df = pd.read_excel(resolved)

    # Normalize columns
    df.columns = [c.strip().lower() for c in df.columns]

    # Support alternative column names commonly found in user datasets.
    def find_col(candidates: list) -> Optional[str]:
        for cand in candidates:
            cand_norm = cand.strip().lower()
            if cand_norm in df.columns:
                return cand_norm
        return None

    disease_candidates = [
        "disease",
        "disease name",
        "disease_type",
        "disease type",
        "wheat disease type",
        "disease_name",
    ]
    symptoms_candidates = [
        "symptoms",
        "symptom",
        "symptoms, survival, spread, and favorable conditions",
        "symptoms/survival/spread",
    ]
    control_candidates = ["control", "management", "control measures", "treatment"]
    crop_candidates = ["crop", "crops"]

    mapped_crop = find_col(crop_candidates)
    mapped_disease = find_col(disease_candidates)
    mapped_symptoms = find_col(symptoms_candidates)
    mapped_control = find_col(control_candidates)

    required_missing = []
    if not mapped_crop:
        required_missing.append("crop")
    if not mapped_disease:
        required_missing.append("disease")
    if not mapped_symptoms:
        required_missing.append("symptoms")
    if not mapped_control:
        required_missing.append("control")

    if required_missing:
        raise ValueError(
            f"Missing required columns. Found={df.columns.tolist()} required={['crop','disease','symptoms','control']} missing={required_missing}"
        )

    # Rename to canonical column names
    rename_map = {
        mapped_crop: "crop",
        mapped_disease: "disease",
        mapped_symptoms: "symptoms",
        mapped_control: "control",
    }
    df = df.rename(columns=rename_map)

    # Add normalized matching columns
    df["crop_norm"] = df["crop"].astype(str).map(_norm)
    df["disease_norm"] = df["disease"].astype(str).map(_norm)

    # NEW: Build disease synonym keys (handles "/" and "(...)" forms)
    df["disease_keys"] = df["disease"].astype(str).apply(_split_synonyms)

    # Cache
    _DF_CACHE = df
    _DB_PATH_CACHE = resolved
    return df


def _candidates_for_crop(df: pd.DataFrame, crop_norm: str, limit: int = 10) -> List[str]:
    sub = df[df["crop_norm"] == crop_norm]
    if sub.empty:
        return []
    return sub["disease"].astype(str).dropna().unique().tolist()[:limit]


@dataclass
class DiseaseInfoTool:
    """
    Deterministic lookup tool:
    Given crop + disease, return symptoms + control from Excel/CSV.

    Enhancements:
      - Supports disease names containing "/" and "(...)" via synonym keys
      - Supports spelling mistakes via fuzzy matching (difflib)
    """

    name: str = "disease_info_tool"

    def run(self, inputs: Optional[Dict[str, Any]] = None) -> str:
        inputs = inputs or {}

        crop = inputs.get("crop")
        disease = inputs.get("disease")

        missing = []
        if not crop:
            missing.append("crop")
        if not disease:
            missing.append("disease")

        if missing:
            return _j(
                {
                    "tool": self.name,
                    "status": "missing_data",
                    "message": "crop and disease are required.",
                    "inputs_received": inputs,
                    "missing_data": missing,
                    "data": {},
                    "sources": [],
                }
            )

        # IMPORTANT: set default exactly as your path
        db_path = os.getenv("DISEASE_DB_PATH", "data/Wheat_Diseases_Data")

        try:
            df = _load_db(db_path)
        except Exception as e:
            return _j(
                {
                    "tool": self.name,
                    "status": "error",
                    "message": f"Failed to load disease knowledge base: {e}",
                    "inputs_received": {"crop": crop, "disease": disease},
                    "missing_data": ["fix_disease_db_path_or_format"],
                    "data": {"db_path": db_path},
                    "sources": [db_path],
                }
            )

        crop_norm = _norm(str(crop))
        disease_norm = _norm(str(disease))

        # Optional alias map (CNN label mismatches)
        alias = {
            # "yellow rust": "stripe rust",
        }
        if disease_norm in alias:
            disease_norm = _norm(alias[disease_norm])

        # Work on only this crop rows (faster + safer)
        sub = df[df["crop_norm"] == crop_norm].copy()

        if sub.empty:
            return _j(
                {
                    "tool": self.name,
                    "status": "missing_data",
                    "message": "Crop not found in knowledge base.",
                    "inputs_received": {"crop": crop, "disease": disease},
                    "missing_data": ["crop_not_found_in_knowledge_base"],
                    "data": {"crop": crop},
                    "sources": [db_path],
                }
            )

        # 1) Exact match on disease_norm (canonical column)
        match = sub[sub["disease_norm"] == disease_norm]
        matched_on = "exact"

        # 2) Synonym match (handles slash/parenthesis)
        if match.empty:
            match = sub[sub["disease_keys"].apply(lambda keys: disease_norm in keys)]
            if not match.empty:
                matched_on = "synonym"

        # 3) Fuzzy match for spelling mistakes
        if match.empty:
            all_keys = sorted({k for keys in sub["disease_keys"].tolist() for k in keys})
            best = _best_fuzzy_match(disease_norm, all_keys, cutoff=0.84)
            if best:
                match = sub[sub["disease_keys"].apply(lambda keys: best in keys)]
                if not match.empty:
                    matched_on = "fuzzy"
                    disease_norm = best  # record matched key

        if match.empty:
            candidates = _candidates_for_crop(df, crop_norm)
            return _j(
                {
                    "tool": self.name,
                    "status": "missing_data",
                    "message": "Disease not found in knowledge base for this crop (even after synonym/fuzzy matching).",
                    "inputs_received": {"crop": crop, "disease": disease},
                    "missing_data": ["disease_not_found_in_knowledge_base"],
                    "data": {
                        "crop": crop,
                        "disease": disease,
                        "candidates_for_crop": candidates,
                    },
                    "sources": [db_path],
                }
            )

        row = match.iloc[0]

        return _j(
            {
                "tool": self.name,
                "status": "ok",
                "message": "Disease advisory fetched from knowledge base.",
                "inputs_received": {"crop": crop, "disease": disease},
                "missing_data": [],
                "data": {
                    "crop": str(row["crop"]),
                    "disease": str(row["disease"]),
                    "symptoms": str(row["symptoms"]),
                    "control": str(row["control"]),
                    "matched_on": matched_on,
                    "matched_key": disease_norm,
                },
                "sources": [_resolve_db_path(db_path)],
            }
        )
