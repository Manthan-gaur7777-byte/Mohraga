import os
from pathlib import Path

from sarvamai import SarvamAI

for line in Path(".env").read_text().splitlines():
    if line.startswith("SARVAM_API_KEY="):
        os.environ.setdefault("SARVAM_API_KEY", line.split("=", 1)[1].strip())

api_key = os.environ.get("SARVAM_API_KEY")
if not api_key:
    raise SystemExit("Set SARVAM_API_KEY in .env before running this script.")

client = SarvamAI(api_subscription_key=api_key)
response = client.chat.completions(
    model="sarvam-105b-conversations",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
