"""Exercise the actual GPU API with text and a bundled public example image."""
import base64
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
MODEL = "Qwen/Qwen3-VL-8B-Instruct-FP8"


def request(messages):
    body = json.dumps({"model": MODEL, "messages": messages,
                       "max_tokens": 100, "temperature": 0}).encode()
    req = urllib.request.Request("http://127.0.0.1:8091/v1/chat/completions", body,
                                 {"Content-Type": "application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=240) as response:
        result = json.load(response)
    text = result["choices"][0]["message"]["content"]
    assert text.strip(), result
    return {"model": result["model"], "seconds": round(time.monotonic()-started, 2),
            "text": text, "usage": result.get("usage")}


if __name__ == "__main__":
    image = next((ROOT / "static" / "cxr").glob("*.jpg"))
    encoded = base64.b64encode(image.read_bytes()).decode()
    report = {
        "text": request([{"role": "user", "content": "한국어로 서버 연결 확인이라고 짧게 답하세요."}]),
        "image": request([{"role": "user", "content": [
            {"type": "text", "text": "This is a public demonstration image, not a current patient's study. Describe only its image type in one sentence. Do not diagnose."},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}},
        ]}]),
    }
    output = ROOT / "verification" / "gpu-live.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
