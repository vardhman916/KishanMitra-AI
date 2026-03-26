import os
from pathlib import Path
import yaml
from dotenv import load_dotenv
from typing import Type

# ✅ CREWAI IMPORTS
from crewai import Agent, Task, Crew, Process
from crewai.project import CrewBase, agent, task, crew
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# ✅ CUSTOM TOOL IMPORT
from SRC.tools.market_tool import MarketTool

# ---------------- ROBUST PATH CONFIG ----------------
current_dir = Path(__file__).resolve().parent
project_root = current_dir
while not (project_root / ".env").exists():
    if project_root == project_root.parent:
        project_root = Path.cwd()
        break
    project_root = project_root.parent

load_dotenv(project_root / ".env")

# Load Configs
agents_config_path = project_root / "config" / "agents.yaml"
tasks_config_path = project_root / "config" / "tasks.yaml"

with open(agents_config_path, "r", encoding="utf-8") as f:
    AGENTS_CONFIG = yaml.safe_load(f) or {}

with open(tasks_config_path, "r", encoding="utf-8") as f:
    TASKS_CONFIG = yaml.safe_load(f) or {}

# ---------------- LLM ----------------
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-3-flash",
    temperature=0.1,
    google_api_key=os.getenv("GEMINI_API_KEY2"),
    max_tokens=200,
    request_timeout=40,
    max_retries=1,
    streaming=False
)

# ---------------- TOOL INPUT SCHEMA ----------------
# This tells the Agent: "You MUST find these 3 strings"
class MarketInput(BaseModel):
    commodity: str = Field(..., description="The crop name, e.g., 'Wheat', 'Rice'.")
    state: str = Field(..., description="The Indian state, e.g., 'Rajasthan'.")
    market: str = Field(..., description="The specific Mandi name, e.g., 'Kota', 'Azadpur'.")

# ---------------- TOOL WRAPPER ----------------
class MarketCrewTool(BaseTool):
    name: str = "market_tool"
    description: str = (
        "Fetches current Mandi prices. "
        "Requires 3 inputs: 'commodity', 'state', and 'market'. "
        "Example: commodity='Wheat', state='Rajasthan', market='Kota'"
    )
    args_schema: Type[BaseModel] = MarketInput

    def _run(self, commodity: str, state: str, market: str) -> str:
        # Instantiate your original tool
        tool_instance = MarketTool()
        inputs = {
            "commodity": commodity,
            "state": state,
            "market": market
        }
        return tool_instance.run(inputs)

# Instantiate
market_tool_instance = MarketCrewTool()

# ================= CREW =================
@CrewBase
class MarketPriceCrew:
    """Market Price Analysis Crew"""
    
    agent_config = AGENTS_CONFIG
    task_config = TASKS_CONFIG

    @agent
    def market_analyst(self) -> Agent:
        return Agent(
            config=self.agent_config.get('market_analyst', {}),
            llm=llm,
            tools=[market_tool_instance],
            verbose=True,
            allow_delegation=False,
            max_iter=1,
            max_execution_time=30
        )

    @task
    def market_price_task(self) -> Task:
        return Task(
            config=self.task_config.get('market_price_task', {}),
            agent=self.market_analyst()
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[self.market_analyst()],
            tasks=[self.market_price_task()],
            process=Process.sequential,
            verbose=True,
            max_rpm=10
        )