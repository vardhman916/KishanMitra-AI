import base64
import json
import os
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

class DiseaseDetectionTool:
    """
    Tool to detect crop diseases using Kindwise (Plant.id) API.
    Supports both 'plant.id' (v3) and 'crop.health' (v1) endpoints.
    """
    
    def __init__(self):
        # .strip() handles accidental spaces in .env
        self.api_key = os.getenv("KINDWISE_API_KEY", "").strip()
        
        # --- DYNAMIC ENDPOINT SELECTION ---
        # Default to plant.id unless explicitly configured.
        product = (os.getenv("KINDWISE_PRODUCT") or "plant.id").strip().lower()
        base_url = os.getenv("KINDWISE_BASE_URL")

        if base_url:
            self.api_url = base_url.rstrip("/") + "/identification"
        elif product in ("crop.health", "crop", "crophealth"):
            self.api_url = "https://crop.kindwise.com/api/v1/identification"
        else:
            # Default to Plant.id V3
            self.api_url = "https://api.plant.id/v3/identification"
        
        if not self.api_key:
            raise ValueError("❌ KINDWISE_API_KEY not found in .env file")

    def _encode_image(self, image_path: str) -> str:
        """Encodes an image file to Base64 string."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def analyze_crop(self, image_path: str) -> Dict[str, Any]:
        """
        Sends image to Kindwise API and returns disease analysis.
        """
        if not os.path.exists(image_path):
            return {"error": f"Image file not found: {image_path}"}

        # 1. Prepare Payload
        b64_image = self._encode_image(image_path)
        
        payload = {
            "images": [b64_image],
            "latitude": 49.207, # Optional: Lat/Lon helps accuracy
            "longitude": 16.608,
            "similar_images": True 
        }
        
        # 'plant.id' supports the "health" modifier; 'crop.health' implies it.
        if "plant.id" in self.api_url:
            payload["health"] = "all" 

        headers = {
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

        # 2. Call API
        try:
            response = requests.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status() 
            data = response.json()
        except requests.exceptions.HTTPError as e:
            # Provide actionable hint for 401s (common mismatch error)
            status = e.response.status_code if e.response is not None else "unknown"
            body = e.response.text.strip()[:300] if e.response is not None else ""
            
            hint = ""
            if status == 401:
                hint = (
                    "\n💡 HINT: Check KINDWISE_API_KEY. If your key is for 'Crop Health', "
                    "set KINDWISE_PRODUCT=crop.health in .env. "
                    "If it is for 'Plant.id', set KINDWISE_PRODUCT=plant.id."
                )
            return {"error": f"API Request Failed: HTTP {status}. {body}{hint}"}
        except requests.exceptions.RequestException as e:
            return {"error": f"API Request Failed: {str(e)}"}

        # 3. Parse Results (Focus on Top 1 High Probability)
        result = data.get("result", {})
        
        # Check if plant is healthy (Binary check)
        is_healthy_data = result.get("is_healthy", {})
        is_healthy = is_healthy_data.get("binary", False)
        healthy_prob = is_healthy_data.get("probability", 0)
        
        # Get Disease Suggestions
        # Note: crop.health vs plant.id might structure this slightly differently,
        # but usually it is under result.disease.suggestions
        disease_suggestions = result.get("disease", {}).get("suggestions", [])
        
        top_disease = None
        if disease_suggestions:
            # Sort by probability descending
            disease_suggestions.sort(key=lambda x: x["probability"], reverse=True)
            best_match = disease_suggestions[0]
            
            # Filter: Only report if probability is significant (> 10%)
            # Otherwise it might just be noise.
            if best_match["probability"] > 0.1:
                top_disease = {
                    "name": best_match["name"],
                    "probability": round(best_match["probability"] * 100, 2),
                    "description": best_match.get("details", {}).get("description", "No description available."),
                    "treatment": best_match.get("details", {}).get("treatment", {}),
                    "url": best_match.get("details", {}).get("url")
                }

        return {
            "is_healthy_probability": round(healthy_prob * 100, 2),
            "is_healthy": is_healthy,
            "top_disease": top_disease, # Returning Single Top Disease
            "scan_id": data.get("access_token")
        }

if __name__ == "__main__":
    tool = DiseaseDetectionTool()
    print(f"Tool initialized using Endpoint: {tool.api_url}")