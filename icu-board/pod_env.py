"""Load only the Pod demo's small configuration file, without shell execution."""
import os
from pathlib import Path

FIELDS = {"OFFLINE_DEMO", "PLANNER_MODE", "HOST", "PORT", "POOL", "LLM_BASE_URL", "LLM_MODEL",
          "LLM_API_KEY", "KHDP_BASE_URL", "KHDP_MODEL", "KHDP_MODELS", "KHDP_API_KEY"}


def load_pod_env(path=None):
    selected = path or os.getenv("POD_ENV_FILE") or Path(__file__).parent / ".env.pod"
    file = Path(selected)
    if not file.is_file():
        return False
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise ValueError("Pod 설정에는 KEY=VALUE 형식을 사용하세요.")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in FIELDS:
            raise ValueError("Pod 설정에 지원하지 않는 키가 있습니다.")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        # Shell variables, commands and substitutions are never evaluated.
        os.environ.setdefault(key, value)
    return True
