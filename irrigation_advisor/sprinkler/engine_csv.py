import pandas as pd
import re
from difflib import get_close_matches


class SprinklerCSVEngine:
    def __init__(self, cost_path, response_path, water_path):
        # Load data
        self.cost_df = self._read_csv_with_fallback(cost_path)
        self.response_df = self._read_csv_with_fallback(response_path)
        self.water_df = self._read_csv_with_fallback(water_path)

        # Clean crop columns
        self.response_df.columns = ["crop", "water_saving_percent", "yield_increase_percent"]
        self.water_df.columns = ["crop", "duration", "total_water_requirement_mm"]

        self.response_df["crop"] = self.response_df["crop"].str.lower().str.strip()
        self.water_df["crop"] = self.water_df["crop"].str.lower().str.strip()

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

    # -----------------------------------
    # COST EXTRACTION FROM WIDE FORMAT
    # -----------------------------------
    def _extract_cost_mapping(self):
        cost_row = self.cost_df[
            self.cost_df["Component"].str.contains("Basic system cost", case=False, na=False)
        ]

        if cost_row.empty:
            raise ValueError("Basic system cost row not found in cost CSV")

        cost_row = cost_row.iloc[0]

        cost_map = {
            1: cost_row["Amt_1ha_50mm dia"] if "Amt_1ha_50mm dia" in cost_row else cost_row["Amt_1ha"],
            2: cost_row["Amt_2ha_(63mmdia)"] if "Amt_2ha_(63mmdia)" in cost_row else cost_row["Amt_2ha"],
            3: cost_row["Amt_3ha_75mm dia"] if "Amt_3ha_75mm dia" in cost_row else cost_row["Amt_3ha"],
            4: cost_row["Amt_4ha_75mm dia"] if "Amt_4ha_75mm dia" in cost_row else cost_row["Amt_4ha"],
        }

        return cost_map

    # -----------------------------------
    # COST QUERY
    # -----------------------------------
    def get_cost(self, hectare):
        hectare = float(hectare)

        if hectare in self.cost_mapping:
            return round(self.cost_mapping[hectare], 2)

        # If decimal hectare, approximate using per hectare average
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

        return {
            "crop": crop_name,
            "water_saving_percent": int(row["water_saving_percent"]),
            "yield_increase_percent": int(row["yield_increase_percent"]),
        }

    # -----------------------------------
    # WATER REQUIREMENT QUERY
    # -----------------------------------
    def get_water_requirement(self, crop_name):
        crop_name = crop_name.lower().strip()

        if crop_name not in self.water_df["crop"].values:
            suggestion = get_close_matches(crop_name, self.water_df["crop"], n=1)
            if suggestion:
                crop_name = suggestion[0]
            else:
                return None

        row = self.water_df[self.water_df["crop"] == crop_name].iloc[0]

        return {
            "crop": crop_name,
            "duration_days": int(row["duration"]),
            "total_water_requirement_mm": int(row["total_water_requirement_mm"]),
        }
