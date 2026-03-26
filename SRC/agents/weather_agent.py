import os
from pathlib import Path
import yaml
from dotenv import load_dotenv
from typing import Type

from crewai import Agent, Task, Crew, Process
from crewai.project import CrewBase, agent, task, crew
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

# Custom Tool Import
from SRC.tools.weather_tool import WeatherTool

# --- PATH SETUP ---
current_dir = Path(__file__).resolve().parent
project_root = current_dir
while not (project_root / ".env").exists():
    if project_root == project_root.parent:
        project_root = Path.cwd()
        break
    project_root = project_root.parent
load_dotenv(project_root / ".env")

# --- CONFIG LOADING ---
try:
    with open(project_root / "config" / "agents.yaml", "r", encoding="utf-8") as f:
        AGENTS_CONFIG = yaml.safe_load(f) or {}
    with open(project_root / "config" / "tasks.yaml", "r", encoding="utf-8") as f:
        TASKS_CONFIG = yaml.safe_load(f) or {}
except Exception as e:
    print(f"Config Error: {e}")
    AGENTS_CONFIG = {}
    TASKS_CONFIG = {}

llm = ChatGoogleGenerativeAI(
    model="gemini-3-flash",
    temperature=0.1,
    google_api_key=os.getenv("GEMINI_API_KEY1"),
    max_tokens=200,
    request_timeout=40,
    max_retries=1,
    streaming=False
)

# =======================================================
# 1. THE TOOL CLASS (Must inherit from BaseTool)
# =======================================================

class WeatherInput(BaseModel):
    """Input schema for WeatherTool."""
    location: str = Field(..., description="The city and state, e.g. 'Bhilwara, Rajasthan'.")
    days: int = Field(3, description="Number of days for forecast (1 to 5). Default is 3.")

class WeatherCrewTool(BaseTool):
    """
    The actual tool instance that the Agent uses.
    """
    name: str = "weather_tool"
    description: str = "Get weather forecast. Requires 'location' and 'days'."
    args_schema: Type[BaseModel] = WeatherInput

    def _run(self, location: str, days: int = 3) -> str:
        # Calls your original logic
        return WeatherTool().run(location=location, days=days)

# =======================================================
# 2. THE CREW CLASS (Must be decorated with @CrewBase)
# =======================================================

@CrewBase
class WeatherCrew:
    """Weather Forecast Crew"""
    
    @agent
    def weather_analyst(self) -> Agent:
        return Agent(
            config=AGENTS_CONFIG.get('weather_analyst', {}),
            llm=llm,
            # ✅ We instantiate the Tool Class here
            tools=[WeatherCrewTool()],
            verbose=True,
            allow_delegation=False,
            max_iter=1,
            max_execution_time=30
        )

    @task
    def weather_task(self) -> Task:
        return Task(
            config=TASKS_CONFIG.get('weather_task', {}),
            agent=self.weather_analyst()
        )

    @crew
    def crew(self) -> Crew:
        
        return Crew(
            agents=[self.weather_analyst()],
            tasks=[self.weather_task()],
            process=Process.sequential,
            verbose=True,
            max_rpm=10
        )