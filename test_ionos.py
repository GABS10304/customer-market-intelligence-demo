"""IONOS-Verbindungstest — nutzt IONOS_TOKEN aus .env."""
from langchain_openai import ChatOpenAI

from config import IONOS_BASE_URL, IONOS_MODEL, get_ionos_token

token = get_ionos_token()
if not token:
    raise SystemExit("IONOS_TOKEN fehlt in .env")

print("Sende Test-Signal an IONOS (Berlin)...")

try:
    llm = ChatOpenAI(
        api_key=token,
        base_url=IONOS_BASE_URL,
        model=IONOS_MODEL,
        temperature=0.0,
    )
    response = llm.invoke("Antworte bitte exakt mit diesem einen Satz: 'Verbindung steht!'")
    print("\nERFOLG — Antwort:")
    print(response.content)
except Exception as exc:
    print(f"\nFEHLER: {exc}")
