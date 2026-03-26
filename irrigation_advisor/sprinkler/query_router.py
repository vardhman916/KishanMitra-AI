import re
from irrigation_advisor.sprinkler.engine_csv import SprinklerCSVEngine


class QueryRouter:
    def __init__(self, engine: SprinklerCSVEngine):
        self.engine = engine

    # ------------------------------
    # Extract hectare from question
    # ------------------------------
    def extract_hectare(self, question):
        match = re.search(r"(\d+(\.\d+)?)\s*(ha|hectare)", question.lower())
        if match:
            return float(match.group(1))
        return None

    # ------------------------------
    # Extract crop name
    # ------------------------------
    def extract_crop(self, question):
        question = question.lower()
        for crop in self.engine.response_df["crop"].values:
            if crop in question:
                return crop
        return None

    # ------------------------------
    # Main Router
    # ------------------------------
    def handle_query(self, question):
        question_lower = question.lower()

        hectare = self.extract_hectare(question)
        crop = self.extract_crop(question)

        response = {}

        # COST RELATED
        if "cost" in question_lower or "price" in question_lower:
            if hectare:
                cost = self.engine.get_cost(hectare)
                response["cost"] = f"Estimated sprinkler cost for {hectare} hectare is ₹{cost}"
            else:
                response["cost"] = "Please specify land size in hectare."

        # WATER REQUIREMENT
        if "water requirement" in question_lower or "how much water" in question_lower:
            if crop:
                water = self.engine.get_water_requirement(crop)
                if water:
                    response["water_requirement"] = (
                        f"{crop.capitalize()} requires approximately "
                        f"{water['total_water_requirement_mm']} mm of water "
                        f"over {water['duration_days']} days."
                    )
            else:
                response["water_requirement"] = "Please specify crop name."

        # CROP RESPONSE
        if "yield" in question_lower or "water saving" in question_lower or "increase" in question_lower:
            if crop:
                crop_data = self.engine.get_crop_response(crop)
                if crop_data:
                    response["crop_response"] = (
                        f"Under sprinkler irrigation, {crop.capitalize()} can save "
                        f"{crop_data['water_saving_percent']}% water and "
                        f"increase yield by {crop_data['yield_increase_percent']}%."
                    )
            else:
                response["crop_response"] = "Please specify crop name."

        if not response:
            response["message"] = "This question is outside structured data. It should go to PDF knowledge system."

        return response