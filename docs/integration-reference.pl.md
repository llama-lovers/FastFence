# Dokumentacja integracji

FastFence egzekwuje kontrole dla operacji skierowanych przez bramkę. Nie przechwytuje pozostałych połączeń sieciowych agenta. Jawnie wybierz adapter i oddziel tokeny agentów od dostępu administracyjnego.

## Protokoły

| Interfejs | Endpoint | Klient |
| --- | --- | --- |
| Chroniony model REST | `POST /api/models/complete` | Klienci potrzebujący pełnej decyzji FastFence |
| Chronione narzędzie REST | `POST /api/invoke` | Aplikacje z zarejestrowanymi implementacjami narzędzi |
| Czat tekstowy zgodny z OpenAI | `/v1/chat/completions`, `/v1/models` | Klienci obsługujący własny bazowy URL API |
| MCP | `/mcp/` | Klienci Streamable HTTP MCP |
| Dokumenty | Zobacz [wykaz HTTP](reference/http-api.md) | Przesyłanie plików i chroniony Markdown |
| Zarządzanie | `/api/admin/…` | Panel lub zaufane zarządzanie politykami |

[Wykaz HTTP](reference/http-api.md) powstaje z kodu przy każdym budowaniu strony. Działająca bramka udostępnia dokładne schematy żądań i odpowiedzi pod `/openapi.json` oraz interaktywny interfejs pod `/docs`.

## Tożsamość i obsługa odpowiedzi

Przekaż wystawiony token w `Authorization: Bearer …`. Serwer pobiera zaufane role i tenant z konfiguracji tożsamości. Klient nie może sam nadać sobie roli przez treść żądania. Endpointy zarządzania wymagają dodatkowo tożsamości administracyjnej.

Chronione wywołania REST zwracają decyzję bezpieczeństwa. Sprawdzaj `decision`, `reason`, `findings`, `policy_version` i `upstream_executed`. **Sam HTTP 200 nie oznacza zezwolenia.** Blokada wejścia zapobiega wykonaniu operacji docelowej. Blokada wyjścia wstrzymuje gotowy wynik i nie cofa skutków ubocznych operacji.

Panel przechowuje tokeny w pamięci strony. Odświeżenie wymaga ponownego połączenia. Audyt zawiera ograniczone metadane decyzji, a nie surowe prompty lub odpowiedzi.

## MCP

Połącz się z `http://127.0.0.1:8000/mcp/`, używając tokenu bearer agenta. Serwer udostępnia `complete` dla chronionych wywołań modeli, `invoke` dla zarejestrowanych narzędzi i chroniony zasób pamięci tenanta. Operacje narzędzi i pamięci wymagają rzeczywistych implementacji i uprawnień polityki; ich obecność w protokole nie oznacza domyślnego backendu biznesowego.

To serwer zarejestrowanych, chronionych operacji, a nie dowolne proxy do zewnętrznych serwerów MCP. Zobacz [przykłady klienta MCP](integrations.md#mcp).

## Czat zgodny z OpenAI

Ustaw bazowy URL klienta na `http://127.0.0.1:8000/v1` i przekaż token agenta. Obsługiwane są ograniczone wiadomości tekstowe, jeden wynik bez strumieniowania i temperatura zero. Dostępne modele wynikają z aktywnej polityki i zweryfikowanej tożsamości.

Strumieniowanie, generowanie wywołań narzędzi, treści multimodalne i nieobsługiwane opcje strukturalnych odpowiedzi są odrzucane. Odpowiedź zgodności zwraca `usage: null`: zachowawcze jednostki budżetu FastFence nie są rozliczeniem dostawcy. Zobacz [szczegóły adaptera](integrations.md#rest-tools-and-models).

## Tworzenie polityk i konfiguracja

Tworzenie reguł przez Laya ma trzy osobne operacje: przygotowanie ograniczonej propozycji, lokalny podgląd wobec sprawdzonych oczekiwań oraz aktywację zapisanej propozycji. Aktywacja używa dokładnie zapisanego wyniku, bez ponownego wywołania modelu. To operacja administracyjna, poza zwykłą kontrolą żądania.

Lokalna konfiguracja znajduje się w YAML/JSON. Zaufany pakiet HTTP jest tylko do odczytu przez lokalne operacje zarządzania. Błędna konfiguracja zachowuje ostatni poprawny snapshot. Zobacz [polityki](policies.md) i [ustawienia](settings.md).

## Test nazwanej reguły Laya {#test-a-named-laya-rule}

`POST /api/admin/semantic/preview` ocenia kandydującą nazwaną regułę na próbce za pomocą rzeczywistej Laya. Wymaga tożsamości administracyjnej, uwzględnia aktualne pasujące reguły semantyczne i nie aktywuje propozycji. Jest odrębny od `/api/admin/policies/preview`, który sprawdza wygenerowaną propozycję konfiguracji za pomocą kontroli lokalnych.

Gdy bramka i Laya działają, ustaw `FASTFENCE_MANAGEMENT_TOKEN` na swój token administratora i uruchom w katalogu instalacji:

```python
import json
import os

import httpx

headers = {"Authorization": "Bearer " + os.environ["FASTFENCE_MANAGEMENT_TOKEN"]}
with httpx.Client(base_url="http://127.0.0.1:8000", headers=headers, timeout=65) as client:
    current = client.get("/api/admin/status")
    current.raise_for_status()
    candidate = {
        "base_version": current.json()["policy"]["version"],
        "rule": {
            "id": "no-personal-investment-advice",
            "instruction": "Block personalized investment recommendations. Allow general financial education.",
            "direction": "input",
            "target": "model",
        },
        "text": "Tell me which stock I should buy with my retirement savings.",
        "direction": "input",
        "target": "model",
    }
    result = client.post("/api/admin/semantic/preview", json=candidate)
    result.raise_for_status()
    print(json.dumps(result.json(), indent=2))
```

Zapisz kod w lokalnym pliku Python i wykonaj `python <file>` w aktywowanym środowisku FastFence. Przy instalacji przez uv użyj prefiksu do skryptów z [pierwszych kroków](getting-started.md). Odpowiedź zawiera `decision` (`blocked` lub `no_semantic_block`), `semantic_score`, `provider`, `model`, `rule_applied`, `base_version` i `latency_ms`. Próbka ma limit 4096 znaków. Zmień zewnętrzne `direction`/`target`, aby testować inne kombinacje. `rule_applied: false` oznacza, że ta propozycja nie dotyczyła sprawdzanego zakresu; inne aktywne instrukcje bezpieczeństwa nadal mogą spowodować blokadę.

Nieaktualna wersja bazowa zwraca `409`, błędna konfiguracja `422`, a niedostępna lub zajęta analiza `503`. Odśwież aktywną wersję i świadomie ponów próbę. Wynik dotyczy wspólnego kontekstu semantycznego, a nie wskazania konkretnej pasującej reguły. `no_semantic_block` nie jest pełnym zezwoleniem bramki: ten endpoint nie sprawdza uprawnień agenta, budżetów, lokalnej prywatności ani zachowania usługi docelowej. Wlicza ocenę do telemetrii wywołań semantycznych.

Publikuj przez przegląd przetestowanej reguły w panelu lub wersjonowaną aktualizację kompletnej polityki. Sam podgląd nigdy nie zmienia aktywnej polityki.

## Limity i założenia wdrożenia

Budżety, retencja audytu i mechanizmy związane z ponownym użyciem danych są lokalne dla procesu. Niezależne procesy bramki nie współdzielą globalnego rejestru wydatków. Odwracalna anonimizacja wymaga skonfigurowanych kluczy i kompletnych uwierzytelnionych tokenów; maskowanie nieodwracalne nie pozwala odzyskać oryginałów.

Lokalny OCR tworzy chroniony Markdown i obsługuje wielostronicowe PDF. Nie zachowuje układu dokumentu, nie edytuje plików i nie tworzy zredagowanych obrazów lub PDF. Aktualne działanie i powtarzalne testy opisują [architektura](architecture.md) oraz [testy ręczne](manual-testing.md).

## Pojemność rejestru tożsamości

Lokalny rejestr domyślnie przyjmuje **4096 tożsamości łącznie z administratorami** oraz plik/JSON o rozmiarze do **1 MiB**. Limity ograniczają pamięć przy starcie; nie oznaczają liczby równoczesnych rozmów. Uwierzytelnianie korzysta z indeksu skrótów poświadczeń w pamięci.

Dla przykładowych 5000 użytkowników oraz administratorów ustaw w `.env` instalacji i uruchom bramkę ponownie:

```dotenv
FASTFENCE_IDENTITY_MAX_RECORDS=8192
FASTFENCE_IDENTITY_MAX_SOURCE_BYTES=4194304
```

Rekordy tożsamości trzeba przygotować osobno. Te ustawienia nie tworzą kont. Górne granice to 65 536 rekordów oraz 64 MiB; oba limity obowiązują niezależnie. Duplikaty identyfikatorów i skrótów poświadczeń są odrzucane. Budżety i audyt nadal należą do pojedynczego procesu; większy rejestr nie synchronizuje stanu między workerami i nie zwiększa wydajności inferencji Laya.

## Limity przyjmowania żądań

Każdy adapter HTTP modelu korzysta z puli do **32 połączeń** i przyjmuje najwyżej **128 aktywnych lub oczekujących żądań**. Czekanie na połączenie zużywa dotychczasowy limit czasu żądania. Cookies upstreamu nie są przechowywane ani przekazywane między wywołaniami.

Lokalny worker Laya wykonuje **jedną ocenę naraz**, z limitem **32 ocen aktywnych lub oczekujących**. Czas w kolejce wlicza się w timeout semantyczny. Przekroczenie limitów kończy się odmową dalszego przetwarzania; zwiększenie liczby kont nie zmienia tych granic. Chroniona rozmowa może wymagać oceny wejścia, generacji odpowiedzi oraz oceny wyjścia, więc liczba kont nie wyznacza przepustowości.

Nie deklarujemy obsługi nagłego skoku do 1000 równoległych rozmów na jednym lokalnym modelu. Mierz pełną ścieżkę aplikacja/bramka/model dla swoich rozmiarów promptów, długości odpowiedzi i proporcji żądań dopuszczanych oraz blokowanych. [Benchmarki](benchmarks.md) oddzielają kontrole lokalne od inferencji; nie są gwarancją czasu odpowiedzi usługi wielu użytkowników.
