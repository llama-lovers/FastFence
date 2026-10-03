# Chroń serwer FastMCP wewnątrz aplikacji FastAPI {#protect-a-fastmcp-server-inside-a-fastapi-application}

Ta kompletna aplikacja łączy rzeczywiste narzędzie FastMCP `uppercase` z FastFence przez `ToolsPort`. Aplikacja FastAPI w FastFence udostępnia uwierzytelnione wejścia REST i MCP. Kontrole wejścia wykonują się **przed** narzędziem, a kontrole wyjścia przed dostarczeniem wyniku.

Prywatny backend FastMCP działa w tym samym procesie i nie nasłuchuje na niezabezpieczonym porcie. Nie powstaje dzięki temu druga trasa omijająca bramkę. Dla zdalnego backendu MCP zastąp `Client(backend)` klientem o stałym zaufanym adresie, przekaż osobny token po stronie serwera i ogranicz bezpośredni dostęp do backendu.

## Uruchom {#run}

Po [zainstalowaniu pakietu](../getting-started.md) rozpakuj [archiwum przykładów](../downloads/fastfence-examples.zip) do `examples/` w katalogu instalacji. Zachowaj `policy.yaml` i `signatures.json` obok `fastmcp_server.py`. Następnie uruchom:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/fastmcp_server.py
```

Aplikacja nasłuchuje pod `http://127.0.0.1:8010`. Inicjalizuje osobną politykę i tokeny w `state/examples/fastmcp-integration/`; nie zmienia głównej instalacji. Otwórz tę konsolę i połącz tokeny `local-agent` oraz `local-admin` z pliku `state/credentials.json` w tym katalogu.

Ten samodzielny przykład celowo korzysta z kontroli deterministycznych, aby działał bez modelu. Główna polityka produktu domyślnie włącza Laya. Aby włączyć te same kontrole semantyczne wejścia i wyjścia w odizolowanym przykładzie, wykonaj poniższe kroki [Włącz Laya](#enable-laya-in-this-example).

## Kompletny serwer i integracja z FastAPI {#complete-server-and-fastapi-integration}

<!-- source: examples/docs/fastmcp_server.py -->

Punktem integracji jest `create_app(..., tools=ProtectedMCPTools())`. Rejestruj operacje biznesowe przez ten port; zwykła trasa FastAPI nie jest automatycznie chroniona przez FastFence. Publiczna trasa `/integration-info` zwraca wyłącznie statyczne metadane. Zweryfikowana tożsamość przekazana adapterowi może też służyć do sprawdzania własności zasobów tenanta przed wykonaniem operacji.

## Polityka {#policy}

<!-- source: examples/docs/policy.yaml -->

## Włącz Laya w tym przykładzie {#enable-laya-in-this-example}

Zatrzymaj serwer przykładu. W głównym katalogu instalacji, przy działającym Ollama przygotuj środowisko wykonawcze:

```sh
uv tool run --python 3.12 fastfence@1.0.1 init --anonymization
export FASTFENCE_AUTHORING_ROOT="$PWD"
```

Zmienna środowiskowa pozwala odizolowanemu przykładowi korzystać z silnika Laya głównej instalacji. Jeśli zmieniłeś endpoint Ollama, wyeksportuj w tej powłoce również takie samo `FASTFENCE_OLLAMA_URL`; przykład czyta zmienne środowiskowe, a nie plik `.env` głównej instalacji.

Edytuj `state/examples/fastmcp-integration/config/policy.yaml`, utworzony przy pierwszym starcie przykładu. Zachowaj narzędzia, budżety i pozostałe kontrole, zwiększ bieżącą wersję `version` na najwyższym poziomie i zastąp sekcję `semantic` następującą:

```yaml
semantic:
  provider: laya
  model: qwen3:4b
  threshold: 0.7
  timeout_ms: 30000
  scan_output: true
```

Jeśli zmieniłeś model oceniający z Qwen3:4b, użyj modelu przygotowanego w głównej instalacji. Sama instalacja Laya nie włącza oceniania: polityka tego przykładu musi zawierać `provider: laya`.

Uruchom ponownie z tej samej powłoki:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/fastmcp_server.py
```

Wyślij ponownie `hello`. Przy dozwolonej odpowiedzi zarówno `semantic_input_status`, jak i `semantic_output_status` powinny mieć wartość `passed`. Brak oceny lub błąd jej wykonania blokuje żądanie. Wejście odrzucone przez wcześniejszą regułę lokalną nigdy nie dociera do modelu oceniającego ani do narzędzia.

## Wywołaj przez REST {#invoke-through-rest}

Ustaw w powłoce `FASTFENCE_AGENT_TOKEN` na wygenerowany token agenta tego przykładu, a następnie:

```sh
curl http://127.0.0.1:8010/api/invoke \
  -H "Authorization: Bearer $FASTFENCE_AGENT_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"tool":"text.uppercase","arguments":{"text":"hello"}}'
```

Oczekiwany wynik: `decision: allowed`, `upstream_executed: true` i `output.text: HELLO`.

Powtórz z `{"text":"forbidden"}`. Oczekuj `decision: blocked` i `upstream_executed: false`. FastFence blokuje dokładne przykładowe słowo przed wywołaniem FastMCP. Te same kontrole obowiązują przez [klienta FastMCP](mcp-client.md), z portem tego serwera i identyfikatorem narzędzia.

Aby sprawdzić samo wyjście, dodaj regułę dopasowującą `HELLO`, kierunek `output`, cel `tool`, z rozróżnianiem wielkości liter. Narzędzie wykona się, ale odpowiedź zostanie zatrzymana. W **Activity** rozróżnisz blokadę wejścia od blokady wyjścia. Sam HTTP 200 nigdy nie oznacza zezwolenia na operację.
