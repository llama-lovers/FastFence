# Wybierz backend modelu zgodny z OpenAI {#choose-an-openai-compatible-model-upstream}

FastFence może wysyłać chronione zadania do natywnego Ollama albo serwera Chat Completions zgodnego z OpenAI. Identyfikator modelu w żądaniu musi być dozwolony przez politykę i dostępny w wybranym backendzie.

Laya pozostaje niezależna: ocena bezpieczeństwa nadal używa lokalnego adresu Ollama z `FASTFENCE_OLLAMA_URL`. Wybór innego dostawcy wykonującego zadania nie wyłącza kontroli wejścia ani wyjścia.

| Ustawienie | Znaczenie |
| --- | --- |
| `FASTFENCE_MODEL_PROVIDER=ollama` | Domyślny natywny transport Ollama dla wykonywania zadań. |
| `FASTFENCE_MODEL_PROVIDER=openai` | Użyj zgodnego transportu `/chat/completions`. |
| `FASTFENCE_OPENAI_BASE_URL` | Bazowy adres API upstream z `/v1`, np. `http://127.0.0.1:11434/v1`. |
| `FASTFENCE_OPENAI_API_KEY` | Opcjonalny token Bearer upstream, przekazywany wyłącznie serwerowi FastFence. |
| `FASTFENCE_OLLAMA_URL` | Adres Ollama dla Laya i natywnego Ollama, domyślnie `http://127.0.0.1:11434`. |

Klucz upstream jest osobny od tokenów agenta i administracji służących do wywoływania FastFence. Trzymaj go w środowisku sekretów serwera. Żądania klienta nie mogą wybierać innego adresu upstream ani przekazywać jego tokenu. Zdalne adresy wymagają HTTPS; HTTP jest dopuszczony tylko dla loopback. Dane logowania w URL, query string, fragmenty, przekierowania i ustawienia proxy ze środowiska są odrzucane lub wyłączone.

Pobierz [komplet przykładów](../downloads/fastfence-examples.zip) do katalogu `examples/` swojej instalacji. Polecenia wykonuj z katalogu instalacji; `uv run` zapewnia Python 3.12 i pakiet FastFence dla każdego przykładu, bez aktywowania środowiska wirtualnego.

## Uruchom ze zgodnym API Ollama {#run-against-ollamas-compatible-api}

Po [zainstalowaniu pakietu](../getting-started.md) wykonaj z katalogu instalacji, przy `ollama serve` działającym w drugim terminalu:

```sh
uv tool run --python 3.12 fastfence@1.0.1 init --anonymization
FASTFENCE_MODEL_PROVIDER=openai \
FASTFENCE_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
uv tool run --python 3.12 fastfence@1.0.1 serve --port 8002
```

Ollama udostępnia zgodną trasę Chat Completions pod `/v1`; trasa natywna pozostaje dostępna niezależnie. Zobacz [dokumentację zgodności Ollama](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx).

W drugim terminalu wykonaj kompletne chronione żądanie kontrolne. Odczytuje lokalny token agenta bez wypisywania go, prosi o odpowiedź z limitem 256 tokenów i sprawdza zarówno decyzję bramki, jak i wykonanie upstream:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python - <<'PY'
import json
import os
from pathlib import Path
import httpx

token = os.environ.get("FASTFENCE_AGENT_TOKEN")
if not token:
    path = Path("state/credentials.json")
    if not path.exists():
        path = Path("state/demo-tokens.json")
    credentials = json.loads(path.read_text())
    token = credentials.get("local-agent") or credentials["analyst-blue"]
with httpx.Client(timeout=120, trust_env=False) as client:
    response = client.post(
        "http://127.0.0.1:8002/api/models/complete",
        headers={"Authorization": "Bearer " + token},
        json={
            "model": "qwen3:4b",
            "prompt": "Say hello in one sentence.",
            "max_output_tokens": 256,
        },
    )
    response.raise_for_status()
    verdict = response.json()
print(json.dumps({key: verdict[key] for key in (
    "decision", "reason", "semantic_input_status", "semantic_output_status",
    "upstream_executed", "output",
)}, indent=2))
assert verdict["decision"] in {"allowed", "redacted"}, verdict["reason"]
assert verdict["upstream_executed"]
assert verdict["output"]["text"].strip()
PY
```

Ustaw `FASTFENCE_MODEL_PROVIDER=ollama`, aby wrócić do transportu natywnego. Zwykłe interfejsy REST, MCP i zgodnego klienta pozostają takie same. Klasyfikacje modelu mogą się różnić; HTTP 200 nie oznacza samo w sobie, że bramka dopuściła żądanie. Modele rozumujące mogą zużyć krótki limit odpowiedzi wyłącznie na rozumowanie i zwrócić pusty tekst z `finish_reason: length`; w takim przypadku dostosuj dozwolony budżet tokenów lub konfigurację modelu upstream.

## Użyj vLLM {#use-vllm}

Na maszynie z zainstalowanym vLLM i zasobami wystarczającymi dla wybranego modelu uruchom zgodny serwer ze stałym aliasem modelu:

```sh
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --host 127.0.0.1 --port 8001 --served-model-name business-model
```

To korzysta z serwera Chat Completions vLLM; wymagania modelu i sprzętu opisuje [dokumentacja serwera vLLM](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/).

W FastFence dodaj `business-model` do listy dozwolonych modeli zgodnie z opisem poniżej, a następnie uruchom bramkę:

```sh
FASTFENCE_MODEL_PROVIDER=openai \
FASTFENCE_OPENAI_BASE_URL=http://127.0.0.1:8001/v1 \
uv tool run --python 3.12 fastfence@1.0.1 serve --port 8002
```

Dla serwera z uwierzytelnianiem ustaw jego token przez opcję vLLM `--api-key` lub zmienną `VLLM_API_KEY`, a tę samą wartość przekaż jako `FASTFENCE_OPENAI_API_KEY` w środowisku bramki. Przy wdrożeniu zdalnym użyj adresu HTTPS API serwera zamiast loopback.

## Użyj llama.cpp {#use-llamacpp}

Mając zainstalowany `llama-server` i dostępny plik GGUF zgodnego modelu instrukcyjnego, ustaw `LLAMA_MODEL_PATH` na ten plik:

```sh
export LLAMA_MODEL_PATH=/absolute/path/to/your-instruct-model.gguf
llama-server --model "$LLAMA_MODEL_PATH" --alias business-model \
  --host 127.0.0.1 --port 8080
```

Alias staje się identyfikatorem modelu w API. Serwer obsługuje zgodne Chat Completions; zobacz [dokumentację serwera llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

Uruchom FastFence następująco:

```sh
FASTFENCE_MODEL_PROVIDER=openai \
FASTFENCE_OPENAI_BASE_URL=http://127.0.0.1:8080/v1 \
uv tool run --python 3.12 fastfence@1.0.1 serve --port 8002
```

## Dopuść i wywołaj udostępniony model {#allow-and-call-the-served-model}

Połącz tożsamość administracyjną w konsoli, otwórz **Policies → Edit configuration** i dodaj model pod `models` w konfiguracji zaawansowanej. Dla domyślnie inicjalizowanych budżetów analyst/operator ten wpis dopuszcza obie role:

```yaml
business-model:
  roles: [analyst, operator]
  max_output_tokens: 256
  timeout_ms: 30000
  cost_microusd: 0
```

Edytor zaawansowany przyjmuje kompletną politykę jako JSON; ten fragment YAML przedstawia wpis do dodania pod `models`, a nie samodzielną politykę zastępczą. Używaj ról z budżetami w swojej instalacji. Sprawdź pełną zmianę i aktywuj następną wersję polityki. Następnie wywołaj wykonywalny klient:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/protected_request.py \
  --url http://127.0.0.1:8002 --model business-model --prompt 'Hello'
```

Ten sam dozwolony model jest dostępny przez [zgodnego klienta SDK](openai-client.md) i [klienta MCP](mcp-client.md).

## Zakres zgodności i weryfikacja {#compatibility-contract-and-verification}

Adapter wysyła pojedyncze tekstowe żądanie czatu bez strumieniowania, z `model`, `messages`, `max_tokens`, `temperature: 0` i opcjonalnymi ciągami stop. Wywołania zawierające tylko prompt stają się jedną wiadomością użytkownika. Upstream musi zwrócić jeden tekstowy wariant odpowiedzi asystenta, jawny powód zakończenia `stop` lub `length` i nieujemne całkowite `prompt_tokens`, `completion_tokens` oraz `total_tokens` o zgodnej sumie. Wywołania narzędzi i funkcji, odmowy, treść nietekstowa, brakujące lub nadmierne zużycie, zakodowane lub zbyt duże ciała odpowiedzi i niepoprawne stany zakończenia powodują odmowę. Nie ma automatycznego ponawiania wywołań dostawcy.

JSON odpowiedzi ma limit 262 144 bajtów, a tekst 65 536 bajtów UTF-8; nadal obowiązuje mniejszy limit wyjścia z polityki. Cała wymiana korzysta z terminu wykonania określonego w polityce modelu. Interfejs nie implementuje wykonywania narzędzi dostawcy, strumieniowania, wiadomości multimodalnych ani Responses API.
