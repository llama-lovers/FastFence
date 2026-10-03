# Chroń komunikację agentów przez ACP {#protect-agent-to-agent-calls-with-acp}

FastFence przyjmuje żądania **Agent Communication Protocol** i przekazuje je do skonfigurowanego agenta przez istniejący silnik polityk narzędzi:

```text
ACP client → FastFence /acp/runs → input controls → trusted ACP peer
                                                     ↓
ACP response ← output controls ← completed peer response
```

Jest to protokół REST IBM/BeeAI, odrębny od Agent Client Protocol dla edytorów. Jego [oficjalne repozytorium](https://github.com/i-am-bee/acp) zostało zarchiwizowane, a [projekt przeszedł do A2A](https://agentcommunicationprotocol.dev/introduction/welcome). FastFence implementuje ograniczony profil zgodności: synchroniczne, bezstanowe wywołania z jawnym tekstem w wiadomości i uwierzytelnione wykrywanie agentów. Nie deklaruje pełnej zgodności z ACP ani A2A.

## Uruchom rzeczywistego agenta lokalnie {#run-a-real-peer-agent-locally}

Zainstaluj FastFence **1.0.0 lub nowszy** według [Pierwszych kroków](../getting-started.md), a następnie rozpakuj [kompletne archiwum przykładów](../downloads/fastfence-examples.zip) do `examples/`. Wszystkie polecenia wykonuj z katalogu instalacji. Bramkę uruchom we własnym środowisku FastFence przez `uv run`. Utwórz osobne środowisko dla agenta i klienta zarchiwizowanego SDK; przypięta wersja Uvicorn nie zmienia wtedy bramki. SDK importuje też `requests`, nie deklarując tej zależności, dlatego zainstaluj ją jawnie w tym osobnym środowisku:

```sh
uv venv --python 3.12 .acp-venv
uv pip install --python .acp-venv/bin/python 'acp-sdk==1.0.3' 'uvicorn==0.35.0' 'requests==2.34.2'
.acp-venv/bin/python examples/acp_server.py
```

Oficjalny ACP SDK udostępnia rzeczywistą operację zamiany na wielkie litery na lokalnym porcie 8020. Generuje osobny prywatny token backendu w `state/examples/acp-upstream-token.txt`. Każdy endpoint backendu wymaga tego tokenu. Zawartość pliku nigdy nie jest wypisywana.

W drugim terminalu uruchom bramkę z jej własnymi zależnościami FastFence:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/acp_gateway.py
```

To uruchamia odizolowaną instancję FastFence na porcie 8030 i rejestruje agenta `uppercase` jako narzędzie polityki `acp.uppercase`. Konfiguracja i tokeny bramki znajdują się pod `state/examples/acp-gateway/`. Ponowny start zachowuje istniejącą konfigurację i nie edytuje głównej instalacji. Jawna polityka przykładu używa kontroli deterministycznych, więc nie wymaga modelu; domyślna polityka produktu nadal wymaga Laya.

W trzecim terminalu użyj **oficjalnego klienta ACP SDK**:

```sh
.acp-venv/bin/python examples/acp_client.py --prompt 'hello'
.acp-venv/bin/python examples/acp_client.py --prompt 'forbidden'
.acp-venv/bin/python examples/acp_client.py --prompt 'email@example.org'
```

Oczekiwany wynik: `hello` kończy się wynikiem `HELLO`; `forbidden` zwraca nieudane wykonanie przed uruchomieniem agenta, a skrypt kończy się kodem 1; adres e-mail jest redagowany przed przekazaniem. HTTP 200 może zawierać nieudane wykonanie: sprawdź `status`, `error.data.reason` i `error.data.upstream_executed`. Poprawny wynik jest zwracany dopiero po przejściu kontroli wyjścia. Sprawdź decyzję w **Activity** pod <http://127.0.0.1:8030>. UUID wykonania ACP odpowiada identyfikatorowi żądania w audycie bez myślników UUID.

Serwer i bramka przyjmują `--port`; bramka dodatkowo `--upstream-url`. Klient przyjmuje `--url`, `--agent` i `--credentials`. Domyślnym tokenem jest `local-agent` odizolowanego przykładu; tokeny administracyjne nie mogą wywoływać ACP.

## Podłącz istniejącego agenta ACP {#connect-your-existing-acp-agent}

Skonfiguruj zaufane ustawienia startowe w środowisku bramki lub prywatnym `.env`:

```sh
export FASTFENCE_ACP_AGENTS='{"assistant":{"base_url":"https://peer.example.org","agent_name":"assistant"}}'
```

Zastąp przykładowy URL i nazwę agenta własnymi wartościami. Dodaj `api_key` do tej zaufanej konfiguracji, jeśli agent wymaga tokenu Bearer. Jest to token backendu, osobny od tokenów FastFence używanych przez klientów. Nie jest zwracany przez API wykrywania agentów ani polityk. Zdalni agenci wymagają HTTPS; HTTP jest dopuszczony tylko dla adresów loopback. Dane klienta nie mogą wybierać adresów upstream ani ich tokenów.

Dodaj odpowiednie narzędzie do `config/policy.yaml`, zachowując pozostałe ustawienia i zwiększając aktywną wersję polityki:

```yaml
tools:
  acp.assistant:
    roles: [analyst]
    timeout_ms: 30000
    cost_microusd: 1
```

Po zmianie ustawień startowych uruchom proces ponownie. Zmiany polityki nadal przeładowują się na żywo. Przy zwykłej bramce działającej na porcie 8000:

```sh
.acp-venv/bin/python examples/acp_client.py --url http://127.0.0.1:8000 \
  --credentials state/credentials.json --agent assistant --prompt 'Hello'
```

`GET /acp/agents` pokazuje wyłącznie agentów zarejestrowanych, skonfigurowanych i dozwolonych dla roli. `POST /acp/runs` przyjmuje tę samą tożsamość Bearer co REST/MCP; wszystkie te transporty współdzielą politykę i budżet w pamięci dla danego podmiotu. Koszty agenta to skonfigurowany koszt narzędzia i ograniczone rozliczanie zasobów tekstowych, a nie pomiary tokenów rozliczeniowych dostawcy. Bezpośredni dostęp do backendu musi pozostawać ograniczony do zaufanych tokenów bramki lub właściwych granic sieciowych.

Kontrole obejmują wiadomości przechodzące przez FastFence. Nie sprawdzają wewnętrznych wywołań modeli/narzędzi zdalnego agenta, chyba że one również przechodzą przez FastFence; ukryte wewnętrzne zużycie tokenów nie jest mierzone przez ten adapter.

## Obsługiwana treść i wykonanie {#supported-content-and-execution}

- Akceptowane są wyłącznie `mode: sync`, `text/plain` zawarty bezpośrednio w wiadomości i `content_encoding: plain`. Dane binarne/base64, zdalne adresy treści, metadane inne niż null, sesje wybrane przez klienta, zadania asynchroniczne, strumieniowanie, odpytywanie, wznawianie i zdalne anulowanie są jawnie odrzucane. Bramka nie pobiera załączników i nie zapisuje wykonań.
- Ciała żądań są ograniczone do 65 536 bajtów; liczby wiadomości i części oraz długości tekstu mają osobne limity. Nieobsługiwane pola są odrzucane przed wykonaniem.
- Etykiety ról i poprawne znaczniki czasu SDK są metadanymi transportu. Nazwane role, np. `agent/researcher`, są normalizowane do `agent`; znaczniki czasu są odrzucane. Do kontroli narzędzi trafia tylko tekst i liczbowe oznaczenia ról, więc zakazana litera w `text/plain` nie zablokuje przypadkowo niezwiązanej treści. Zadeklarowana rola nigdy nie uwierzytelnia klienta.
- Cała odpowiedź agenta jest buforowana w granicach limitu rozmiaru i sprawdzana przed dostarczeniem. Nieudana kontrola wyjścia nie cofa pracy już wykonanej przez agenta. Przekroczenie czasu blokuje wynik i zużywa konserwatywnie zarezerwowane zasoby; zakończenie lokalnego żądania nie gwarantuje zatrzymania pracy zdalnego agenta.
- Bezstanowy klient powinien jawnie przesyłać potrzebny tekst konwersacji w każdym wywołaniu. FastFence nie przechowuje konwersacji ACP ani wyników. Przykładowy backend SDK tworzy własną sesję nawet bez takiego żądania. FastFence sprawdza i odrzuca zwrócony UUID: nigdy nie zwraca, nie zachowuje ani nie używa ponownie identyfikatora sesji. Agent może niezależnie utrzymywać własny stan.

Surowa chroniona reprezentacja narzędzia, dostępna także przez REST/MCP, to `{"tool":"acp.assistant","arguments":{"input":[{"role":0,"parts":["Hello"]}]}}`. Rola `0` oznacza użytkownika, a `1` agenta. Ta wewnętrzna projekcja tekstu różni się od natywnego schematu ACP. Reguły literalne i semantyczne używają celu **Tools**.

[Oficjalny OpenAPI](https://github.com/i-am-bee/acp/blob/main/docs/spec/openapi.yaml) i [klient SDK](https://github.com/i-am-bee/acp/blob/main/python/src/acp_sdk/client/client.py) definiują wiadomości protokołu i zachowanie `run_sync` używane przez te przykłady.

## Kompletne źródła przykładu {#complete-example-sources}

### Agent z oficjalnego SDK {#official-sdk-peer}

<!-- source: examples/docs/acp_server.py -->

### Rejestracja bramki {#gateway-registration}

<!-- source: examples/docs/acp_gateway.py -->

### Oficjalny klient SDK {#official-sdk-client}

<!-- source: examples/docs/acp_client.py -->

### Odizolowana polityka {#isolated-policy}

<!-- source: examples/docs/acp_policy.yaml -->
