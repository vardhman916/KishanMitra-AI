from pathlib import Path
import pandas as pd
from openpyxl import load_workbook

class PestInfoTool:

    def __init__(self, excel_path):
        self.project_root = Path(__file__).resolve().parents[2]
        candidate_path = Path(excel_path)
        if not candidate_path.is_absolute():
            candidate_path = self.project_root / candidate_path
        self.excel_path = candidate_path

        if not self.excel_path.exists():
            raise FileNotFoundError(f"Pest data file not found: {self.excel_path}")

        self.df = pd.read_excel(self.excel_path, engine="openpyxl")
        self.embedded_images_by_row = self._load_embedded_images()

        # Normalize columns
        self.df.columns = self.df.columns.str.lower()
        self.df["crop"] = self.df["crop"].str.lower()
        self.df["pest"] = self.df["pest"].str.lower()

    def get_pest_info(self, crop_name, pest_name):
        crop_name = crop_name.lower().strip()
        pest_name = pest_name.lower().strip()

        result = self.df[
            (self.df["crop"] == crop_name) &
            (self.df["pest"] == pest_name)
        ]

        if result.empty:
            return None

        row = result.iloc[0]
        image_value = row.get("image")
        image_path = self._resolve_image_path(image_value)
        if not image_path:
            # DataFrame index 0 corresponds to Excel row 2 (row 1 is header).
            excel_row = int(row.name) + 2
            image_path = self.embedded_images_by_row.get(excel_row)

        return {
            "crop": row["crop"],
            "pest": row["pest"],
            "symptoms": row["symptoms"],
            "control": row["control"],
            "image": image_path
        }

    def _resolve_image_path(self, image_value):
        if pd.isna(image_value):
            return None

        image_text = str(image_value).strip()
        if not image_text:
            return None

        if image_text.startswith(("http://", "https://")):
            return image_text

        path = Path(image_text)
        if not path.is_absolute():
            path = self.project_root / path

        return str(path) if path.exists() else None

    def _load_embedded_images(self):
        images_by_row = {}
        cache_dir = self.project_root / "data" / ".pest_images_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        try:
            workbook = load_workbook(self.excel_path)
            sheet = workbook.active
            for idx, image in enumerate(getattr(sheet, "_images", [])):
                try:
                    row = image.anchor._from.row + 1
                except Exception:
                    continue

                file_ext = (getattr(image, "format", None) or "png").lower()
                output_path = cache_dir / f"row_{row}_{idx}.{file_ext}"
                with open(output_path, "wb") as f:
                    f.write(image._data())
                images_by_row[row] = str(output_path)
        except Exception:
            return {}

        return images_by_row
