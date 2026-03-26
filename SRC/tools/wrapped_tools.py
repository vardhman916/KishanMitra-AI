from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import Optional

# Import your existing classes
from SRC.tools.weather_tool import WeatherTool
from SRC.tools.market_tool import MarketTool

# --- 1. Weather Tool Wrapper ---

class WeatherInput(BaseModel):
    location: str = Field(..., description="City name, e.g., 'Kota, Rajasthan' or 'Pune'.")

def get_weather(location: str) -> str:
    """Fetches weather forecast for a specific location."""
    t = WeatherTool()
    # We strip 'units' and 'days' to defaults for simplicity, 
    # but the agent can be taught to use them if needed.
    return t.run(location=location)

weather_langchain_tool = StructuredTool.from_function(
    func=get_weather,
    name="CheckWeather",
    description="Useful for getting rain, temperature, and forecast. Input should be a city name.",
    args_schema=WeatherInput
)

# --- 2. Market Price Tool Wrapper ---

class MarketInput(BaseModel):
    commodity: str = Field(..., description="Crop name, e.g., 'Wheat', 'Mustard'.")
    state: str = Field(..., description="State name, e.g., 'Rajasthan', 'Madhya Pradesh'.")
    market: str = Field(..., description="Mandi/Market name, e.g., 'Kota', 'Indore'.")

def get_market_price(commodity: str, state: str, market: str) -> str:
    """Fetches current mandi prices for a crop."""
    t = MarketTool()
    return t.run({"commodity": commodity, "state": state, "market": market})

market_langchain_tool = StructuredTool.from_function(
    func=get_market_price,
    name="CheckMandiPrice",
    description="Useful for getting current crop prices. REQUIRES 3 inputs: commodity, state, and market.",
    args_schema=MarketInput
)