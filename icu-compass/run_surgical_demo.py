"""Launch the English surgical-only dashboard with a paused fictional bleeding case."""
import os
import runpy
from pathlib import Path

os.environ["ICU_COHORT"] = "surgical"
os.environ["ICU_DEMO_SCENARIO"] = "bleeding"
os.environ.setdefault("ICU_LLM_CONFIG", str(Path.home() / ".config/icu-board/khdp-api.json"))
os.environ.setdefault("LLM_BASE_URL", "https://api.khdp.net/v1")
os.environ.setdefault("LLM_MODEL", "qwen3-8-flash-next-ax")
os.environ["ICU_REQUIRE_LIVE_MODEL"] = "1"
runpy.run_path(str(Path(__file__).with_name("server.py")), run_name="__main__")
