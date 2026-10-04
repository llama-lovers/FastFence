# Sprawdź i aktywuj regułę w języku naturalnym {#preview-and-activate-a-natural-language-rule}

Ten kompletny skrypt dodaje nazwaną politykę:

> Blokuj spersonalizowane rekomendacje finansowe. Zezwalaj na ogólne definicje finansowe.

Laya ocenia **rzeczywistą treść próbek** przez `POST /api/admin/semantic/preview`. Reguła dotyczy wyłącznie wejścia modelu. Podgląd nie aktywuje reguły ani nie wysyła zadania do chronionego modelu.

Pobierz [komplet przykładów](../downloads/fastfence-examples.zip) do katalogu `examples/` swojej instalacji. Polecenia wykonuj z katalogu instalacji; `uv run` zapewnia Python 3.12 i pakiet FastFence dla każdego przykładu, bez aktywowania środowiska wirtualnego.

## Wymagania {#prerequisites}

Przeprowadź [lokalną konfigurację bramki](protected-request.md#start-the-gateway). Pozostaw Ollama i FastFence uruchomione. Przykład wymaga prywatnego tokenu administracyjnego z `state/credentials.json` lub `FASTFENCE_ADMIN_TOKEN` przekazanego przez środowisko. Obsługiwane są też starsze tokeny `security-admin`.

## Najpierw sprawdź podgląd {#preview-first}

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/semantic_policy.py
```

Skrypt pobiera aktywną politykę, zachowuje pozostałe zabezpieczenia, dodaje lub zastępuje wyłącznie `no-personal-financial-advice` i zwiększa wersję kandydata. Wysyła dwie próbki do rzeczywistego endpointu podglądu, następnie wypisuje rzeczywiste wyniki i różnice w YAML. W trybie podglądu nie wysyła `PUT`.

Oczekiwane obserwacje:

| Próbka | Oczekiwana decyzja podglądu |
| --- | --- |
| `Buy this stock immediately with all your savings.` | `blocked` |
| `Define a stock as a financial instrument.` | `no_semantic_block` |

`no_semantic_block` opisuje wyłącznie ten podgląd semantyczny. Chronione żądanie nadal musi przejść uwierzytelnianie, reguły deterministyczne, budżety i kontrole wyjścia. Jeśli Laya jest już włączona, podgląd używa aktywnego modelu semantycznego i progu; w przeciwnym razie wybiera dla kandydata Laya/Qwen3:4b. Nieoczekiwane klasyfikacje są jawnie raportowane i uniemożliwiają aktywację przez ten skrypt.

## Aktywuj po sprawdzeniu {#activate-deliberately}

Po przejrzeniu różnic i wyników:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/semantic_policy.py --activate
```

Skrypt ponownie wykonuje podglądy, sprawdza oczekiwane wyniki, ponownie pobiera aktywną politykę, aby wykryć równoległe zmiany, a następnie przesyła kandydata do rzeczywistego endpointu `PUT /api/admin/policy`. Serwer sprawdza wersję i skonfigurowane źródło. Nieudany podgląd lub konflikt zatrzymuje przykład bez aktywacji.

Teraz sprawdź aktywną politykę zwykłą ścieżką chronionych żądań:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/protected_request.py \
  --prompt 'Buy this stock immediately with all your savings.'
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/protected_request.py \
  --prompt 'Define a stock as a financial instrument.'
```

Zmień stałe `RULE` i `CASES`, aby sprawdzić inną politykę. Zachowaj próbkę blokowaną i dozwoloną, z oczekiwaniami ustalonymi samodzielnie. Do ścisłych ograniczeń znaków używaj deterministycznej reguły tekstowej, zamiast traktować ocenę modelu jak dokładne dopasowanie. Usunięcie nazwanej reguły przez **Policies** wymaga kolejnej sprawdzonej wersji polityki.


## Ograniczenie reguł złożonych {#compound-rule-limitation}

Dla lokalnej oceny Qwen3:4b odtworzono przeoczenie reguły wymagającej **jednocześnie pełnego imienia i nazwiska oraz adresu email**: treść zawierająca oba elementy została dopuszczona, mimo że nazwana reguła poprawnie dotarła do Laya. Koniunkcja opisana językiem naturalnym nie zastępuje niezawodnie deterministycznej ochrony prywatności. Zachowaj odpowiednie kontrole PII i testuj osobno kombinacje, pojedyncze elementy oraz wyjątki. Poprawna ocena jednego przykładu nie potwierdza ogólnej skuteczności wykrywania.

Kolejna próba na publicznym pakiecie **1.0.4** objęła 25 przypadków: osobną ocenę zgodności z polityką, a następnie niezmieniony skaner bezpieczeństwa. Ocena polityki była poprawna w **19/25** przypadków (sześć przeoczonych naruszeń), a skaner bezpieczeństwa w **25/25**. Połączenie decyzji dało **20/25**, w tym **7/8** nowych przypadków niewykorzystywanych przy projektowaniu tej próby. Dodatkowe wywołanie modelu **nie zostało wdrożone**: nadal przepuszczało naruszenia i zwiększało zużycie tokenów oraz czas wykonania. Opublikowany runtime semantyczny pozostaje bez zmian; te małe próby nie potwierdzają ogólnej skuteczności.

Ocena semantyczna może też zablokować treść dozwoloną przez regułę dosłowną, ponieważ warstwy egzekwują osobne ograniczenia. Gdy brak dopasowania dosłownego kończy się blokadą, sprawdź przyczynę decyzji oraz wyniki oceny wejścia i wyjścia.

<!-- source: examples/docs/semantic_policy.py -->
