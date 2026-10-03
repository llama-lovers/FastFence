# OpenAI Python SDK przez FastFence {#openai-python-sdk-through-fastfence}

Ten klient wysyła czat tekstowy do `/v1/chat/completions` w FastFence. FastFence stosuje politykę przed wywołaniem skonfigurowanego dostawcy modelu. Token klienta to **token agenta FastFence**, a nie klucz dostawcy upstream.

Pobierz [komplet przykładów](../downloads/fastfence-examples.zip) do katalogu `examples/` swojej instalacji. Polecenia wykonuj z katalogu instalacji; `uv run` zapewnia Python 3.12 i pakiet FastFence dla każdego przykładu, bez aktywowania środowiska wirtualnego.

## Uruchom z Ollama {#run-with-ollama}

Wykonaj kroki [instalacji](../getting-started.md): uruchom Ollama, wykonaj `uv tool run --python 3.12 fastfence@1.0.1 init --anonymization`, a następnie `uv tool run --python 3.12 fastfence@1.0.1 serve`. Inicjalizacja instaluje Laya i przygotowuje domyślny model Qwen3:4b. Ustaw `FASTFENCE_AGENT_TOKEN` na wygenerowany token agenta.

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 --with openai==2.21.0 python examples/openai_client.py 'Hi'
```

Skrypt wypisuje chronioną odpowiedź modelu. Ustaw `FASTFENCE_MODEL`, jeśli korzystasz z innego dozwolonego modelu. Ustaw `FASTFENCE_URL`, jeśli bramka nasłuchuje pod innym adresem; zawsze jest to adres bramki, nigdy adres upstream.

## Kompletny klient {#complete-client}

<!-- source: examples/docs/openai_client.py -->

## Sprawdź blokowanie {#verify-blocking}

W **Policies** dodaj regułę literalną dla wejścia modelu dopasowującą `forbidden`, przetestuj ją i aktywuj. Następnie wykonaj:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 --with openai==2.21.0 python examples/openai_client.py 'forbidden'
```

Oczekiwany wynik: niezerowy kod zakończenia i odmowa HTTP. **Activity** pokazuje regułę wejścia oraz `upstream_executed: false`. Klient wyłącza automatyczne ponawianie i nigdy nie przełącza się na bezpośrednie połączenie z dostawcą.

## Użyj innego backendu modelu {#use-a-different-model-backend}

Pozostaw klienta bez zmian i zastosuj na bramce [konfigurację upstream zgodnego z OpenAI](openai-upstream.md). Klucz dostawcy pozostaje po stronie serwera. Model semantyczny Laya jest konfigurowany osobno.

Obsługiwany zakres: czat tekstowy bez strumieniowania, z temperaturą zero. Ten adapter zgodności nie obsługuje strumieniowania, generowania wywołań narzędzi ani wiadomości multimodalnych. Użyj [REST](protected-request.md), jeśli odpowiedź ma zawierać pełną decyzję zabezpieczeń.
