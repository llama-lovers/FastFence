![Logo FastFence](assets/fastfence-logo.svg){ .fastfence-landing-logo width="120" height="121" }

# FastFence

**Polityki bezpieczeństwa dla agentów. Lokalne egzekwowanie przy każdym wywołaniu.**

FastFence sprawdza żądania i odpowiedzi AI zgodnie z politykami dostępu, prywatności, treści i zasobów. Połącz aplikację przez REST, endpoint zgodny z OpenAI, MCP lub skonfigurowanego agenta ACP. Opisz regułę za pomocą Laya, przejrzyj zmiany i testy, a następnie aktywuj ją bez restartu bramki.

[Rozpocznij](getting-started.md){ .md-button .md-button--primary }
[Przejdź samouczek](learn.md){ .md-button }
[Dokumentacja HTTP API](reference/http-api.md){ .md-button }

## Uruchom lokalnie

Zainstaluj [uv](https://docs.astral.sh/uv/getting-started/installation/) i uruchom [Ollama](https://ollama.com/). W wybranym katalogu roboczym wykonaj:

```sh
uv tool run fastfence
```

FastFence **1.0.2 lub nowszy** przygotowuje wymagane środowisko i uruchamia bramkę jednym poleceniem. Tworzy prywatną konfigurację, instaluje Laya, pobiera brakujący model oceniający i w razie potrzeby przygotowuje OCR. Nowa instalacja używa Qwen3:4b do oceny i generowania odpowiedzi w osobnych wywołaniach; drugi model nie jest potrzebny.

Otwórz **http://127.0.0.1:8000** i połącz się danymi z `state/credentials.json`. Korzystaj dalej z tego samego katalogu: konfiguracja i klucze pozostają tutaj, a uv przechowuje pakiet osobno. Jeśli uv ma już starsze wydanie w pamięci podręcznej, użyj `uv tool run fastfence@latest`.

Nie potrzebujesz repozytorium ani ręcznie aktywowanego środowiska. [Instrukcja instalacji](getting-started.md) opisuje wymagania, polecenia z przypiętą wersją i aktualizacje.

## Wybierz zadanie

| Chcę… | Zacznij tutaj |
| --- | --- |
| Wysłać chronione żądanie do modelu | [Pierwsze żądanie](learn.md#1-send-a-protected-model-request) |
| Opisać regułę i sprawdzić jej działanie | [Polityki i przegląd zmian](policies.md) |
| Podłączyć istniejącego agenta lub klienta MCP | [Kontrakt integracji](integration-reference.md) |
| Podłączyć innego agenta przez ACP | [Przykład komunikacji agentów](examples/acp.md) |
| Skonfigurować prywatność, anonimizację i budżety | [Konfiguracja polityk](policies.md) |
| Znaleźć endpoint lub schemat żądania | [Dokumentacja HTTP z kodu źródłowego](reference/http-api.md) |
| Skonfigurować instalację lokalną | [Zmienne środowiskowe](settings.md) |
| Samodzielnie sprawdzić system | [Testy ręczne](manual-testing.md) |
| Uruchomić kod integracji | [Gotowe przykłady](examples/fastmcp-server.md) · [OpenAI SDK](examples/openai-client.md) |
| Przekazać dokumentację modelowi LLM | [llms.txt](llms.txt) · [llms-full.txt](llms-full.txt) |

## Jak to działa

Uwierzytelnione żądanie przechodzi przez kontrolę dostępu, treści wejściowej i rezerwację budżetu przed wykonaniem operacji docelowej. FastFence następnie sprawdza odpowiedź i zapisuje decyzję bez poufnych treści. Szybkie kontrole deterministyczne działają lokalnie. Domyślna konfiguracja korzysta również z Laya do semantycznej oceny wejścia i wyjścia, które docierają do tego etapu; niedostępność analizy blokuje żądanie.

Laya ma dwie osobne role. W panelu zarządzania przygotowuje propozycje ograniczonych reguł, które po przeglądzie stają się szybkimi kontrolami lokalnymi. W trakcie obsługi żądania ocenia treść według zasad bezpieczeństwa i Twojej polityki opisanej językiem naturalnym. Samo dopasowanie reguł tekstowych nie wywołuje modelu, ale włączona analiza semantyczna go używa.

Polityki mogą być odświeżane z lokalnych plików lub zaufanego źródła HTTP. Błędna aktualizacja pozostawia ostatnią poprawną konfigurację. Propozycja zmiany nie jest aktywną polityką: sprawdź różnice, zweryfikuj oczekiwania i jawnie ją opublikuj.

## Zakres działania

Produkt lokalny uruchamia się bez symulowanych narzędzi biznesowych. Działające przykłady narzędzi są oddzielone od domyślnego środowiska. Wywołanie modelu wymaga dozwolonego modelu w skonfigurowanej usłudze Ollama lub zgodnej z OpenAI. OCR przekształca dokumenty w Markdown sprawdzany przez polityki; nie edytuje obrazów ani PDF.

Budżety i ograniczony dziennik audytu są lokalne dla procesu i zerują się po restarcie. Odwracalna anonimizacja używa uwierzytelnionych tokenów i lokalnych kluczy oraz wymaga jawnego zezwolenia na odtworzenie danych. Blokada odpowiedzi nie cofa wykonanej operacji. Granice zaufania i wdrożenia opisuje [architektura](architecture.md).

FastFence jest dostępny na licencji Apache-2.0.
