# Integracje

FastFence chroni operacje skierowane przez jego bramkę. Istniejące połączenia agenta trzeba jawnie skierować do chronionych adapterów. Instalacja FastFence nie przechwytuje automatycznie pozostałego ruchu sieciowego agenta.

## Narzędzia i modele REST {#rest-tools-and-models}

Endpointy agenta wymagają wystawionego tokenu bearer agenta. Endpointy zarządzania wymagają osobnego tokenu administratora. Interaktywny schemat API jest dostępny lokalnie pod `http://127.0.0.1:8000/docs`.

Chronione operacje zapisu REST uwierzytelniają klienta przed odczytem i parsowaniem treści. Całe żądanie wywołania ma limit **512 KiB** rzeczywiście przesłanych bajtów, także przy przesyle fragmentami i znakach escapowanych w JSON. Żądania administracyjne używają większej wartości z 512 KiB i zaufanego ustawienia `FASTFENCE_MAX_CONFIG_SOURCE_BYTES` (maksymalnie 2 MiB). Zbyt duże żądania otrzymują bezpieczny błąd `413`, bez wywołania usługi docelowej i rezerwacji budżetu. Aktywna polityka niezależnie ogranicza logiczne dane wejściowe do 64 KiB. Adapter zgodny z OpenAI ma osobny limit całego żądania 64 KiB.

| Endpoint | Przeznaczenie |
| --- | --- |
| `POST /api/invoke` | Wywołanie dozwolonego narzędzia ze sprawdzonymi argumentami |
| `POST /api/models/complete` | Wywołanie dozwolonego modelu Ollama z promptem lub wiadomościami |
| `GET /v1/models` | Modele dozwolone dla zweryfikowanej roli |
| `POST /v1/chat/completions` | Ograniczony interfejs czatu zgodny z OpenAI |
| `GET /acp/agents` | Skonfigurowani agenci ACP dostępni dla klienta |
| `POST /acp/runs` | Synchroniczne wywołanie tekstowe agenta ACP z kontrolą wejścia i wyjścia |
| `GET /api/me` | Zaufane atrybuty tożsamości nadane przez serwer |
| `GET /api/admin/status` | Polityka, budżety, telemetria i audyt bez poufnych treści |
| `GET /api/admin/audit.jsonl` | Eksport zachowanych rekordów audytu |

Implementacje biznesowe rejestruje aplikacja. Uruchom [przykład serwera FastMCP](examples/fastmcp-server.md) na porcie 8010, a następnie wyślij tę treść do jego `/api/invoke` z tokenem agenta należącym do przykładu:

```json
{
  "tool": "text.uppercase",
  "arguments": {"text": "hello"}
}
```

Rzeczywiste odpowiedzi modelu wymagają uruchomionej usługi Ollama, zainstalowanego modelu i aktywnej polityki dopuszczającej ten model. Wiadomości `system`, `user` i `assistant` korzystają z Ollama `/api/chat`, a zwykłe prompty z `/api/generate`. Każda wiadomość i sekwencja stop przechodzą przez te same kontrole oraz rozliczanie zasobów.

Adapter zgodny z OpenAI obsługuje ograniczone wiadomości tekstowe, odpowiedzi bez strumieniowania, temperaturę zero i jeden wynik. Limit tokenów odpowiedzi jest ograniczany limitem bramki i polityką modelu. Strumieniowanie, wygenerowane wywołania narzędzi, treści multimodalne, opcje odpowiedzi strukturalnej i nieobsługiwane pola są jawnie odrzucane. `usage` ma wartość `null`, ponieważ zachowawcze jednostki budżetu bramki nie są dokładnym rozliczeniem dostawcy. Zachowane są informacje stop/length oraz metadane decyzji bramki.

## MCP

Endpoint Streamable HTTP MCP to `http://127.0.0.1:8000/mcp/`. Przyjmuje zweryfikowane tokeny agenta i udostępnia:

- Narzędzie `invoke` przyjmujące nazwę dozwolonego narzędzia biznesowego i argumenty.
- Narzędzie `complete` przyjmujące `model`, `prompt` i ograniczone `max_output_tokens`; korzysta z tej samej ścieżki kontroli modelu co HTTP.
- Zasób `memory://{tenant}/{key}`, wywołujący chronioną operację `memory.read`.

Przypięta implementacja transportu MCP uwierzytelnia przed parsowaniem JSON i ogranicza treść HTTP do 4 MiB. Ten limit protokołu jest oddzielny od mniejszego limitu danych wejściowych modelu lub narzędzia w polityce. Komunikaty protokołu, takie jak `ping`, nie uruchamiają operacji biznesowej.

Generowanie przez MCP wymaga zainstalowanego, dozwolonego modelu. Reguły wejścia i wyjścia, prywatność, ocena semantyczna, budżety i audyt działają tak samo jak dla HTTP. Serwer udostępnia zarejestrowane operacje, nie jest dowolnym proxy do wszystkich serwerów MCP.

W katalogu zainicjalizowanej instalacji zapisz i uruchom ten kompletny klient Python:

```python
import asyncio
import json
from pathlib import Path

from fastmcp import Client
from fastmcp.client.auth import BearerAuth


async def main():
    credentials = json.loads(Path("state/credentials.json").read_text())
    async with Client(
        "http://127.0.0.1:8000/mcp/",
        auth=BearerAuth(credentials["local-agent"]),
    ) as client:
        completion = await client.call_tool(
            "complete", {"model": "qwen3:4b", "prompt": "Cat", "max_output_tokens": 16}
        )
        print(completion.data)


asyncio.run(main())
```

Istniejące instalacje zachowują pierwotny plik danych dostępu i nazwy tożsamości. Jeśli inicjalizacja wskazuje starszy `state/demo-tokens.json`, użyj tokenu jego agenta. Nie rotuj ani nie nadpisuj tokenów tylko po to, aby zmienić nazwy.

Zasoby tenanta muszą odpowiadać zweryfikowanej tożsamości. Kontrola polityk działa przed utworzeniem tekstowej i strukturalnej reprezentacji wyniku przez FastMCP, więc obie zawierają przefiltrowaną odpowiedź.

## Agenci ACP

Endpoint zgodności z Agent Communication Protocol to `/acp`. Skonfiguruj zaufane adresy agentów w `FASTFENCE_ACP_AGENTS`, a następnie dopuść narzędzia `acp.<alias>` i odpowiednie role w polityce. [Kompletny przykład ACP](examples/acp.md) korzysta z oficjalnego SDK do wywołania osobnego agenta przez FastFence.

Adapter obsługuje synchroniczne, bezstanowe wiadomości ze zwykłym tekstem umieszczonym bezpośrednio w treści. Odrzuca sesje wybrane przez klienta, strumieniowanie i załączniki. Automatycznie wygenerowane identyfikatory sesji agenta docelowego są pomijane. Tekst przechodzi przez te same kontrole wejścia i wyjścia co inne narzędzia; token klienta nigdy nie staje się tokenem agenta docelowego. ACP przeniosło się do A2A. Ten adapter zachowuje opisany profil zgodności ACP i nie implementuje A2A.

## Rzeczywista integracja Laya

Pakiet korzysta z [silnika Laya w Pythonie](https://github.com/aayushch/laya) w przypiętej rewizji. Zwykłe `fastfence init` instaluje go w katalogu instalacji i sprawdza lub pobiera skonfigurowany model oceniający przez Ollama. `fastfence setup-laya` służy jedynie do osobnej instalacji lub naprawy silnika. Pobiera zewnętrzny silnik, zachowuje informacje licencyjne i instaluje zależności ze sprawdzanymi hashami w prywatnym stanie lokalnym. Potrzebuje Git, `sh` i `uv`, ale nie repozytorium FastFence.

Laya pełni dwie niezależne role:

- **Ocena w trakcie żądania:** nazwane reguły języka naturalnego i wytyczne bezpieczeństwa analizują wejście i wyjście za pomocą rzeczywistego modelu. [Klient polityk semantycznych](examples/semantic-policy.md) testuje próbki, pokazuje różnice i aktywuje zmianę tylko z jawnym `--activate`.
- **Tworzenie szybkich reguł:** **Describe a fast rule** przygotowuje ograniczoną propozycję deterministyczną z podglądem treści i testami regresyjnymi. Przejrzyj ją i aktywuj; późniejsze dopasowanie literalne nie wywołuje Laya.

Domyślny model oceniający to Qwen3:4b w lokalnej Ollama. Chroniony model generujący odpowiedzi jest konfigurowany niezależnie. Dokładny zakaz litery powinien używać reguły literalnej lub tekstowej; osąd modelu jest przybliżony. Zakresy i obsługę awarii opisują [polityki](policies.md).

Aby podłączyć zewnętrznego agenta, skieruj jego klienta modelu do [endpointu zgodnego z OpenAI](examples/openai-client.md), a zarejestrowane operacje przez [FastMCP](examples/fastmcp-server.md). Bramka nie przechwytuje połączeń nadal kierowanych bezpośrednio do dostawców.
