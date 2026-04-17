import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
E2B_API_KEY: str = os.environ["E2B_API_KEY"]
GITHUB_PAT: str = os.environ["GITHUB_PAT"]
