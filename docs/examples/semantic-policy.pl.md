# Sprawdź i aktywuj regułę w języku naturalnym {#preview-and-activate-a-natural-language-rule}

Ten kompletny skrypt dodaje nazwaną politykę:

> Blokuj spersonalizowane rekomendacje finansowe. Zezwalaj na ogólne definicje finansowe.

Laya ocenia **rzeczywistą treść próbek** przez `POST /api/admin/semantic/review`. Dla każdej próbki podajesz oczekiwany wynik. Serwer porównuje bieżącą i proponowaną politykę semantyczną oraz wydaje identyfikator zatwierdzonego testu tylko wtedy, gdy każdy wymagany wynik kandydata odpowiada oczekiwaniu. Ten przykład dotyczy wejścia modelu; test nie wywołuje chronionego modelu biznesowego ani nie aktywuje polityki.

Pobierz [komplet przykładów](../downloads/fastfence-examples.zip) do katalogu `examples/` swojej instalacji. Polecenia wykonuj z katalogu instalacji; `uv run` zapewnia Python 3.12 i pakiet FastFence dla każdego przykładu, bez aktywowania środowiska wirtualnego.

## Wymagania {#prerequisites}

Przeprowadź [lokalną konfigurację bramki](protected-request.md#start-the-gateway). Pozostaw Ollama i FastFence uruchomione. Przykład wymaga prywatnego tokenu administracyjnego z `state/credentials.json` lub `FASTFENCE_ADMIN_TOKEN` przekazanego przez środowisko. Obsługiwane są też starsze tokeny `security-admin`.

## Najpierw sprawdź podgląd {#preview-first}

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/semantic_policy.py
```

Skrypt pobiera aktywną wersję i przesyła dwie próbki z oczekiwaniami. Serwer przygotowuje dokładnego kandydata, zachowując pozostałe zabezpieczenia i zastępując wyłącznie `no-personal-financial-advice`. Skrypt pokazuje różnice YAML oraz **oczekiwanie → przed → po → wynik testu**, wraz z rzeczywiście ocenionym zakresem. W trybie sprawdzania nie wysyła aktywacji. Wyłączona ocena bazowa daje `not_evaluated`, a nie pozorne dopuszczenie treści.

Oczekiwane obserwacje:

| Próbka | Oczekiwana decyzja podglądu |
| --- | --- |
| `Buy this stock immediately with all your savings.` | `blocked` |
| `Define a stock as a financial instrument.` | `no_semantic_block` |

`no_semantic_block` opisuje wyłącznie ten podgląd semantyczny. Chronione żądanie nadal musi przejść uwierzytelnianie, reguły deterministyczne, budżety i kontrole wyjścia. Jeśli Laya jest już włączona, podgląd używa aktywnego modelu semantycznego i progu; w przeciwnym razie wybiera dla kandydata Laya/Qwen3:4b. Nieoczekiwane klasyfikacje są jawnie raportowane i blokują kontrolowaną aktywację na serwerze. Błąd dostawcy, timeout lub brak oceny wymaganego zakresu również blokuje aktywację. Model nie zmienia Twoich oczekiwań, żeby test przeszedł.

## Aktywuj po sprawdzeniu {#activate-deliberately}

Po przejrzeniu różnic i wyników:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/semantic_policy.py --activate
```

Skrypt ponownie wykonuje testy i wysyła ich identyfikator do `POST /api/admin/semantic/activate` z jawnym potwierdzeniem. Serwer sprawdza administratora, termin ważności, niezmienioną politykę, feed i zapisane przypadki, a potem aktywuje dokładnie przetestowanego kandydata. Nieaktualny lub użyty identyfikator nie pozwala aktywować innej polityki. Poprawny wynik całego zestawu potwierdza te konkretne obserwacje, a nie ogólną niezawodność modelu.

Zwykły administracyjny `PUT /api/admin/policy` i ręczna edycja YAML z hot reloadem pozostają osobnymi ścieżkami operatora. Nie wymuszają tej kontroli testów przed aktywacją.

Teraz sprawdź aktywną politykę zwykłą ścieżką chronionych żądań:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/protected_request.py \
  --prompt 'Buy this stock immediately with all your savings.'
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/protected_request.py \
  --prompt 'Define a stock as a financial instrument.'
```

Zmień stałe `RULE` i `CASES`, aby sprawdzić inną politykę. Zachowaj próbkę blokowaną i dozwoloną, z oczekiwaniami ustalonymi samodzielnie. Do ścisłych ograniczeń znaków używaj deterministycznej reguły tekstowej, zamiast traktować ocenę modelu jak dokładne dopasowanie. Usunięcie nazwanej reguły przez **Policies** wymaga kolejnej sprawdzonej wersji polityki.


## Zapisane przypadki i ponowne uruchomienie {#saved-cases-and-replay}

Po aktywacji sprawdzone przypadki są zapisywane w `config/semantic-policy-tests.yaml` z prywatnymi uprawnieniami pliku. Przypadki innych reguł zostają zachowane. Podczas kolejnej zmiany serwer porównuje również zapisane przypadki pozostałych aktywnych reguł; nowa reguła naruszająca ich oczekiwania nie przejdzie testów. Przypadki usuniętych reguł są oznaczane jako nieaktywne, a nie zaliczone. Istniejące reguły bez zapisanego zestawu są jawnie oznaczane jako nieprzetestowane; można uzupełniać je pojedynczo.

Uruchom zapisane oczekiwania na bieżącej polityce semantycznej:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/semantic_policy.py --replay-tests
```

Ponowne testowanie niczego nie aktywuje. Nieoczekiwany wynik, brak oceny lub pusty aktywny zestaw nie daje sukcesu. Skrypt kończy się kodem `2`, jeśli oczekiwania nie są spełnione. Zmiana polityki lub pliku testów podczas oceny unieważnia wynik.

Polityka i testy są osobnymi plikami. Jeśli zapis zestawu zawiedzie już po aktywacji, odpowiedź podaje aktywowaną wersję i `tests_saved: false`; skrypt kończy się błędem i wyraźnie mówi, że polityka jest już aktywna. Nie powtarzaj wtedy bezmyślnie aktywacji. Sprawdź uprawnienia pliku i uzgodnij zapisany zestaw przed dalszą pracą. Plik zawiera podane próbki, dlatego używaj danych syntetycznych zamiast rzeczywistych danych klientów.

## Praca w dashboardzie i limity {#dashboard-workflow-and-limits}

W **Policies → Add a Laya rule** opisz regułę i wpisz zarówno treści wymagające blokady, jak i treści, które mają przejść ocenę semantyczną. Interfejs rozwinie próbki na wszystkie wybrane zakresy wejścia/wyjścia oraz modeli/narzędzi. Sprawdź tabelę wyników i dokładne różnice, następnie potwierdź aktywację. Zmiana próbki, oczekiwania, instrukcji, zakresu lub tożsamości unieważnia test.

Edytowana reguła może zawierać do 16 przypadków z konkretnym zakresem; każda próbka ma limit 4096 bajtów UTF-8. Oba kierunki i oba rodzaje wywołań zużywają cztery przypadki na próbkę. Łączny zapisany zestaw ma limit 64 przypadków i 64 KiB. Porównanie może wykonać do 128 rzeczywistych ocen, z łącznym terminem 120 sekund. Jednocześnie działa tylko jeden zestaw testów. Identyfikator zatwierdzonego testu wygasa po dziesięciu minutach; restart wymaga ponownego testowania. Powiązanie obejmuje konfigurację, ale nie zamraża wag modelu podmienionych poza FastFence.


## Ograniczenie reguł złożonych {#compound-rule-limitation}

Dla lokalnej oceny Qwen3:4b odtworzono przeoczenie reguły wymagającej **jednocześnie pełnego imienia i nazwiska oraz adresu email**: treść zawierająca oba elementy została dopuszczona, mimo że nazwana reguła poprawnie dotarła do Laya. Koniunkcja opisana językiem naturalnym nie zastępuje niezawodnie deterministycznej ochrony prywatności. Zachowaj odpowiednie kontrole PII i testuj osobno kombinacje, pojedyncze elementy oraz wyjątki. Poprawna ocena jednego przykładu nie potwierdza ogólnej skuteczności wykrywania.

Kolejna próba na publicznym pakiecie **1.0.4** objęła 25 przypadków: osobną ocenę zgodności z polityką, a następnie niezmieniony skaner bezpieczeństwa. Ocena polityki była poprawna w **19/25** przypadków (sześć przeoczonych naruszeń), a skaner bezpieczeństwa w **25/25**. Połączenie decyzji dało **20/25**, w tym **7/8** nowych przypadków niewykorzystywanych przy projektowaniu tej próby. Dodatkowe wywołanie modelu **nie zostało wdrożone**: nadal przepuszczało naruszenia i zwiększało zużycie tokenów oraz czas wykonania. Opublikowany runtime semantyczny pozostaje bez zmian; te małe próby nie potwierdzają ogólnej skuteczności.

Ocena semantyczna może też zablokować treść dozwoloną przez regułę dosłowną, ponieważ warstwy egzekwują osobne ograniczenia. Gdy brak dopasowania dosłownego kończy się blokadą, sprawdź przyczynę decyzji oraz wyniki oceny wejścia i wyjścia.


## Sprawdzenie przepływu w 1.0.6 {#verified-workflow-in-106}

Izolowaną instalację zbudowanego wheela 1.0.6 sprawdzono przez rzeczywiste HTTP i Laya/Qwen3:4b. Przykład finansowy przeszedł wszystkie osiem przypadków wejścia/wyjścia modelu/narzędzia, jednorazową aktywację, prywatny zapis i osiem ponownych ocen. Ponowne użycie identyfikatora aktywacji zostało odrzucone. Przykład imienia i nazwiska z emailem ponownie wykazał przeoczenie — test nie przeszedł i nie powstał identyfikator pozwalający na aktywację. Nie wywołano żadnego upstreamu biznesowego. Wykonano 44 próby oceny; to niewielki test przepływu, a nie benchmark trafności lub przepustowości. [Zapisane wyniki](https://github.com/llama-lovers/FastFence/blob/v1.0.6/evaluation/results/reviewed-semantic-workflow-1.0.6.json).

<!-- source: examples/docs/semantic_policy.py -->
