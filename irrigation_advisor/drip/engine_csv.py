import pandas as pd
import re
from difflib import get_close_matches


class DripCSVEngine:
    def __init__(self, cost_path, response_path):
        # Load data
        self.cost_df = self._read_csv_with_fallback(cost_path)
        self.response_df = self._read_csv_with_fallback(response_path)

        # Clean crop response columns
        self.response_df.columns = ["crop", "water_saving_percent", "yield_increase_percent"]
        self.response_df["crop"] = self.response_df["crop"].str.lower().str.strip()

        # Extract cost mapping
        self.cost_mapping = self._extract_cost_mapping()

    @staticmethod
    def _read_csv_with_fallback(path):
        encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
        last_error = None
        for encoding in encodings:
            try:
                return pd.read_csv(path, encoding=encoding)
            except UnicodeDecodeError as exc:
                last_error = exc
        raise last_error

    @staticmethod
    def _find_component_column(columns):
        for col in columns:
            if str(col).strip().lower() == "component":
                return col
        return columns[0]

    @staticmethod
    def _find_amount_column(columns, hectare):
        target_prefix = f"amt_{hectare}ha"
        for col in columns:
            normalized = str(col).strip().lower().replace(" ", "")
            if normalized.startswith(target_prefix):
                return col
        return None

    @staticmethod
    def _to_number(value):
        if pd.isna(value):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[^\d.\-]", "", str(value))
        if not cleaned:
            return None
        return float(cleaned)

    # -----------------------------------
    # COST EXTRACTION FROM WIDE FORMAT
    # -----------------------------------
    def _extract_cost_mapping(self):
        component_col = self._find_component_column(self.cost_df.columns)
        component_series = self.cost_df[component_col].astype(str)
        cost_row = self.cost_df[
            component_series.str.contains("Basic System Cost", case=False, na=False)
        ]

        if cost_row.empty:
            raise ValueError("Basic System Cost row not found in drip cost CSV")

        cost_row = cost_row.iloc[0]

        cost_map = {}
        missing_values = False
        for hectare in (1, 2, 3, 4):
            amt_col = self._find_amount_column(self.cost_df.columns, hectare)
            if amt_col is None:
                missing_values = True
                continue
            amount = self._to_number(cost_row[amt_col])
            if amount is None:
                missing_values = True
                continue
            cost_map[hectare] = amount

        if missing_values or len(cost_map) < 4:
            extracted_values = []
            for col in self.cost_df.columns:
                if col == component_col:
                    continue
                value = self._to_number(cost_row[col])
                if value is not None:
                    extracted_values.append(value)

            if len(extracted_values) >= 4:
                cost_map = {1: extracted_values[0], 2: extracted_values[1], 3: extracted_values[2], 4: extracted_values[3]}
            else:
                raise ValueError("Could not extract 1-4 hectare costs from drip cost CSV")

        return cost_map

    # -----------------------------------
    # COST QUERY
    # -----------------------------------
    def get_cost(self, hectare):
        hectare = float(hectare)

        if hectare in self.cost_mapping:
            return round(self.cost_mapping[hectare], 2)

        # Approximation for decimal hectare
        max_hectare = max(self.cost_mapping.keys())
        approx_per_hectare = self.cost_mapping[max_hectare] / max_hectare
        return round(hectare * approx_per_hectare, 2)

    # -----------------------------------
    # CROP RESPONSE QUERY
    # -----------------------------------
    def get_crop_response(self, crop_name):
        crop_name = crop_name.lower().strip()

        if crop_name not in self.response_df["crop"].values:
            suggestion = get_close_matches(crop_name, self.response_df["crop"], n=1)
            if suggestion:
                crop_name = suggestion[0]
            else:
                return None

        row = self.response_df[self.response_df["crop"] == crop_name].iloc[0]
        water_saving = self._to_number(row["water_saving_percent"])
        yield_increase = self._to_number(row["yield_increase_percent"])
        if water_saving is None or yield_increase is None:
            raise ValueError(f"Invalid crop response values for crop '{crop_name}'")

        return {
            "crop": crop_name,
            "water_saving_percent": int(round(water_saving)),
            "yield_increase_percent": int(round(yield_increase)),
        }
