# Pierwsze kroki

## Uruchom jednym poleceniem

Użyj macOS lub Linux z [uv](https://docs.astral.sh/uv/getting-started/installation/), Git i `sh`. Zainstaluj [Ollama](https://ollama.com/) i pozostaw usługę uruchomioną (`ollama serve` w drugim terminalu albo aplikacja desktopowa). W wybranym katalogu roboczym wykonaj:

```sh
uv tool run fastfence
```

Od FastFence **1.0.2** uruchomienie bez podkomendy przygotowuje wymagane komponenty i startuje bramkę. Nie potrzebujesz repozytorium, aktywowanego środowiska ani osobnych poleceń `init` i `serve`. uv wybiera zgodny interpreter Python i przechowuje pakiet w swojej pamięci podręcznej. Korzystaj dalej z tego samego katalogu: tutaj pozostają `config/`, dane dostępu i klucze.

Jeśli uv ma już starszą wersję FastFence, odśwież ją poleceniem `uv tool run fastfence@latest`. Aby wybrać dokładnie to wydanie i interpreter:

```sh
uv tool run --python 3.12 fastfence@1.0.2
```

### Alternatywa: pip i środowisko wirtualne

Jeśli wolisz bezpośrednio zainstalowane polecenie, utwórz środowisko Python 3.12 w tym samym katalogu roboczym:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install fastfence uv
fastfence
```

Otwórz **http://127.0.0.1:8000**. W **Connection** wpisz tokeny `local-agent` i `local-admin` z prywatnego pliku `state/credentials.json`. Token agenta wysyła chronione żądania, a token administratora umożliwia przegląd i zmianę polityk. Panel trzyma tokeny tylko w pamięci strony.

Pierwsze uruchomienie tworzy `config/`, prywatne dane dostępu i zestaw kluczy wystawcy tokenów anonimizacji w katalogu roboczym. Instaluje też przypięty silnik Laya oraz sprawdza dostępność modelu oceniającego w Ollama, pobierając go tylko wtedy, gdy go brakuje. Przygotowuje też zależności i modele OCR, jeśli nie są gotowe. Ponowne uruchomienie zachowuje poprawne dane dostępu, polityki i klucze. Zachowaj ten katalog podczas aktualizacji. Starsze instalacje z `state/demo-tokens.json` zachowują tożsamości `security-admin` i `analyst-blue`.

Rozróżnij trzy role:

- **Laya** to silnik Python uruchamiający oceny bezpieczeństwa i pomagający tworzyć reguły. Instaluje go pierwsze uruchomienie.
- **Model oceniający** interpretuje sprawdzany tekst. Domyślnie to **Qwen3:4b** obsługiwany przez Ollama. Start sprawdza i pobiera skonfigurowany model.
- **Model lub narzędzie Twojej aplikacji** wykonuje właściwą pracę po kontroli wejścia. Nowa polityka dopuszcza również Qwen3:4b do generowania odpowiedzi, więc wystarczy jedno pobranie. Możesz wybrać inny dozwolony model lub [usługę zgodną z OpenAI](examples/openai-upstream.md).

Ocena i generowanie odpowiedzi to osobne wywołania, nawet jeśli używają tego samego modelu. Agent korzystający tylko z narzędzi lub ACP nie wymaga osobnego modelu do odpowiedzi. Inicjalizacja zachowuje istniejący wybór modelu i nie pobiera dodatkowego modelu biznesowego. Brak oceny blokuje żądanie; dokładne reguły literalne są sprawdzane lokalnie wcześniej.

Do przygotowania samej konfiguracji użyj `uv tool run --python 3.12 fastfence@1.0.2 init --config-only` lub `fastfence init --config-only` w środowisku pip. Polecenie zapisuje konfigurację i stan prywatny bez instalowania Laya i kontaktowania się z Ollama. Uruchom zwykłe polecenie startu, gdy wymagane usługi będą dostępne. `setup-laya` pozostaje zaawansowanym poleceniem instalacji lub naprawy silnika; nie jest osobnym krokiem standardowego startu.

## Wyślij chronione żądanie

W drugim terminalu przejdź do tego samego katalogu roboczego. Ten kompletny klient korzysta z izolowanego środowiska z HTTPX i odczytuje prywatny token bez zapisywania go w historii powłoki:

```sh
uv run --no-project --python 3.12 --with httpx python - <<'PY'
import json
from pathlib import Path
import httpx

credentials = json.loads(Path("state/credentials.json").read_text())
with httpx.Client(timeout=120, trust_env=False) as client:
    response = client.post(
        "http://127.0.0.1:8000/api/models/complete",
        headers={"Authorization": "Bearer " + credentials["local-agent"]},
        json={"model": "qwen3:4b", "prompt": "Hello", "max_output_tokens": 256},
    )
    response.raise_for_status()
    print(response.json())
PY
```

Sprawdź `decision`, `reason`, `upstream_executed` i statusy etapów semantycznych. Sam HTTP 200 nie oznacza zgody. Znajdź identyfikator żądania w **Activity**. Interaktywne schematy API są dostępne pod **http://127.0.0.1:8000/docs**.

## Pobierz działające przykłady {#download-runnable-examples}

Pobierz [archiwum przykładów](downloads/fastfence-examples.zip) i rozpakuj je do `examples/` w katalogu instalacji. Zawiera wykonywalne pliki Python, politykę i sygnatury FastMCP oraz pięć syntetycznych dokumentów OCR w `documents/`. Nie zawiera danych dostępu ani stanu prywatnego.

```sh
curl -fL https://fastfence.dev/downloads/fastfence-examples.zip -o fastfence-examples.zip
uv run --no-project --python 3.12 python -m zipfile -e fastfence-examples.zip examples
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/protected_request.py --prompt 'Hello'
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/mcp_client.py --prompt 'Hello'
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/semantic_policy.py
```

Na innych stronach przykładów zastąp prefiks `python` poleceniem `uv run --no-project --python 3.12 --with fastfence==1.0.1 python`, jeśli korzystasz z instalacji przez narzędzia uv. Przykłady wymagające dodatkowych SDK wymieniają je osobno. Przy instalacji pip możesz uruchamiać skrypty w aktywowanym środowisku.

Ostatnie polecenie testuje nazwaną regułę języka naturalnego przy użyciu rzeczywistego modelu Laya i pokazuje różnice. Niczego nie aktywuje, dopóki po przeglądzie nie uruchomisz go z `--activate`. Każda [strona przykładu](examples/protected-request.md) zawiera pełny kod i bezpośredni odnośnik do pliku.

## Opisz regułę i sprawdź ją przez MCP

Dla ograniczeń semantycznych skorzystaj z [przykładu nazwanej reguły Laya](examples/semantic-policy.md). Dla dokładnego zakazu litery otwórz **Policies → Add content rule** i wybierz **Word contains**, wartość `a`, **Input only**, **Models** oraz dopasowanie bez rozróżniania wielkości liter. Sprawdź `Hi` i `Cat`, przejrzyj zmianę i aktywuj ją.

Możesz też użyć **Describe a fast rule**, aby Laya przygotowała ograniczoną propozycję deterministycznej konfiguracji z Twojego opisu. Przed aktywacją sprawdź operator, wartość i zakres; lokalne dopasowanie takiej reguły działa inaczej niż ocena semantyczna podczas żądania.

```sh
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/mcp_client.py --prompt 'Cat'
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/mcp_client.py --prompt 'Hi'
```

`Cat` musi zostać zablokowane przed wykonaniem modelu. `Hi` przechodzi tę regułę i może dotrzeć do Qwen, jeśli pozwalają na to pozostałe kontrole. Wybierz oba kierunki, jeśli reguła ma sprawdzać także odpowiedź. Blokada wyjścia nie cofa wykonanej operacji.

## OCR dokumentów i zaawansowana diagnostyka

Zwykły start przygotowuje OCR automatycznie. Aby naprawić je osobno lub uruchomić pełną diagnostykę:

```sh
uv tool run --python 3.12 fastfence@1.0.2 setup-ocr
uv tool run --python 3.12 fastfence@1.0.2 doctor --full
```

Przejdź do [testów ręcznych](manual-testing.md). OCR obsługuje obrazy i wielostronicowe PDF, zwracając Markdown sprawdzony przez polityki. Nie edytuje pikseli dokumentu. Po naprawie komponentów uruchom bramkę ponownie, a następnie wykonaj `fastfence doctor --full` odpowiednim prefiksem uv lub pip.

## Aktualizacja FastFence

Zatrzymaj bramkę. Dla instalacji przez uv jawnie wybierz najnowsze opublikowane wydanie:

```sh
uv tool run fastfence@latest
```

Zwykłe polecenie bez wersji może użyć wersji z pamięci podręcznej; `@latest` odświeża ją. Polecenie z `@1.0.2` pozostaje przypięte do tej wersji. [Dokumentacja uv opisuje te zasady](https://docs.astral.sh/uv/concepts/tools/#tool-versions). Polecenie z pobraną wcześniej dokładną wersją może działać z opcją uv `--offline`, ale wyłącza ona jedynie pobieranie przez uv: FastFence nadal potrzebuje skonfigurowanej usługi modelu, a zwykła inicjalizacja może pobierać komponenty.

Dla pip aktywuj istniejące środowisko i wykonaj:

```sh
python -m pip install --upgrade fastfence
fastfence
```

Po restarcie odśwież panel. `config/` i `state/` w katalogu roboczym są oddzielone od zainstalowanego pakietu. Twórz ich kopie i zachowuj je podczas aktualizacji. Jeśli wydanie zmienia przypięte pliki pomocnicze Laya, zastosuj instrukcję tego wydania; instalator odmawia nadpisania zmienionych plików.

Same polityki aktualizuj przez przegląd i aktywację wyższej wersji w **Policies**. Poprawne zmiany z wyższą wersją w `config/policy.yaml` także przeładowują się automatycznie. Błędne zmiany zachowują ostatnią poprawną konfigurację. Zmiana `.env` wymaga restartu.
