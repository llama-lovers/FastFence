# FastFence — narracja po polsku, slajdy i podpisy po angielsku

Wersja pokazywana w demonstracji: **publiczna paczka 1.0.7**. Nagranie korzysta z osobnej konfiguracji i prawdziwych modeli. Tokenów dostępowych nie pokazujemy: połączenie z dashboardem przygotowujemy przed rozpoczęciem nagrania.

## Wystąpienie: około 3 minut, 7 slajdów

### 1. FastFence — 00:00–00:20

**Subtitle: “Security policies for every AI interaction”**

Agent AI potrafi dziś wywołać model, odczytać dokument albo uruchomić narzędzie. Każde takie połączenie może przenieść poufne dane, wykonać niedozwoloną operację lub zużyć budżet. Potrzebujemy jednego miejsca, które kontroluje te interakcje i pozwala zmieniać zasady bez przebudowy agenta. To zadanie FastFence.

### 2. One control layer across AI interfaces — 00:20–00:50

FastFence stoi między aplikacją a modelem lub narzędziem. Obsługuje REST, interfejs zgodny z OpenAI, MCP i komunikację agentów przez ACP. Najpierw sprawdza uprawnienia, wzorce, dane wrażliwe i limity. Laya ocenia treść semantycznie. Sprawdzamy również odpowiedź, zanim wróci do użytkownika. Polityki są centralne, a lokalne reguły i liczniki działają w pamięci procesu.

### 3. A reviewed rule becomes a live policy — 00:50–01:20

Regułę semantyczną opisujemy zwykłym językiem. Na przykład: blokuj spersonalizowane rekomendacje finansowe, ale dopuszczaj ogólne definicje. Dodajemy przykłady, które mają przejść i zostać zablokowane. System porównuje zachowanie aktywnej i proponowanej polityki, pokazuje wyniki oraz dokładny diff. Aktywacja wymaga poprawnego przeglądu i świadomego potwierdzenia. Zapisane testy można powtórzyć. To istotne, ponieważ model może pomylić złożone reguły; nie ukrywamy tego za zielonym komunikatem.

### 4. Privacy controls preserve useful context — 01:20–01:45

Dane można zablokować, zredagować albo zastąpić aliasami. Wariant odwracalny przenosi zaszyfrowaną wartość w tokenie, bez bazy rozmów; przywracanie wymaga odpowiednich kluczy i jawnego przełącznika. Przywrócona treść ponownie przechodzi kontrole. Obrazy i wielostronicowe PDF-y przetwarzamy przez OCR do Markdown, który jest dalej chroniony. Nie obiecujemy edycji oryginalnego obrazu.

### 5. Evidence from FastFence 1.0.7 — 01:45–02:15

Przeszło 1484 testów źródłowych, z pokryciem kodu 93,28 procent, oraz 406 kontroli bezpieczeństwa, kolejki i transportu na zainstalowanej paczce. Tysiąc kontrolowanych wywołań sprawdziło osiem aktywnych i 992 oczekujące. Osobno dwanaście prawdziwych żądań przeszło przez Laya i Ollamę, z dwudziestoma czterema ocenami wejścia i wyjścia. To różne zakresy dowodów, nie tysiąc jednoczesnych generacji modelu.

### 6. Every decision has an operational record — 02:15–02:40

Dashboard pokazuje decyzje, powody blokad, wykorzystanie budżetów i czas oczekiwania w kolejce. W szczegółach widać wersję polityki oraz informację, czy wywołano upstream. Audyt eksportujemy do JSONL bez surowych promptów i kluczy. Budżety oraz przechowywany audyt są lokalne dla procesu; restart je zeruje. Nie deklarujemy wspólnego limitu dla wielu instancji.

### 7. Try FastFence from PyPI — 02:40–03:00

FastFence uruchamiamy z PyPI jednym poleceniem widocznym na slajdzie. Publicznie udostępniamy kod, instrukcje i wyniki pomiarów. Łączymy szybkie reguły lokalne z oceną treści przez Laya i przeglądem przypadków przed aktywacją. Za chwilę pokażemy nagranie prawdziwej sesji: zmianę polityki bez restartu i jej wpływ na kolejne żądanie.

### 8. Appendix: latency measurements and scope — opcjonalnie, poza 3 minutami

To pomiary publicznej paczki 1.0.2 na Apple M3 Pro, przy jednym równoległym żądaniu. Dwa tysiące próbek lokalnych kontroli dało medianę 0,206 i p95 0,248 milisekundy. Dwie oceny Laya, wejścia i wyjścia, miały medianę 1117 i p95 1200 milisekund w dwudziestu próbkach. Oba pomiary wykluczają wejściowe HTTP i generowanie odpowiedzi przez model biznesowy. Model semantyczny był rozgrzany i otrzymywał powtarzany prompt. To obserwacje historyczne; pełny pomiar opóźnień wersji 1.0.7 pozostaje do wykonania.

## Nagranie produktu: około 2 minut 25 sekund

Łączne nagranie trwa **144,933 s**. Pierwsze 90 sekund pokazuje sesję reguł, a kolejne 54,933 sekundy obejmują podgląd PDF i ochronę dokumentu w osobnej izolowanej sesji. Poniższe czasy i angielskie podpisy odpowiadają końcowemu plikowi `presentation/output/demo-captions.srt`. Sesja używa publicznej paczki 1.0.7: `Hello` przechodzi przy polityce v4, zostaje zablokowane przy v5, a poprawny przegląd reguły semantycznej prowadzi do aktywacji v6. W części reguł wykonano 18 rzeczywistych ocen Laya: dwie dla powitania i szesnaście podczas porównania ośmiu przypadków. Osobna część OCR dodaje trzy oceny: jedną przy ekstrakcji oraz wejście i wyjście przy wywołaniu modelu.

| Czas filmu | Czynność w dashboardzie | English caption |
| --- | --- | --- |
| 00:00.000–00:06.100 | Overview izolowanej instancji. | “FastFence 1.0.7 \| Live public package. Real Laya + local Qwen.” |
| 00:06.100–00:10.091 | Wysłanie `Hello` do rzeczywistego modelu. | “1. Send a real model request through the active security policy.” |
| 00:10.091–00:18.232 | ALLOW: model wykonał żądanie, Laya sprawdziła wejście i wyjście. | “ALLOWED: Laya inspected input and output; the business model really ran.” |
| 00:18.232–00:28.088 | Reguła lokalna `contains Hello`: podgląd przykładu pasującego i dozwolonego. | “2. Add a fast input rule. Test prohibited and permitted examples first.” |
| 00:28.088–00:31.236 | Aktywacja przejrzanej polityki v5 bez restartu. | “Reviewed policy activated. The same gateway keeps running.” |
| 00:31.236–00:39.334 | To samo `Hello` zablokowane lokalnie przed modelem. | “Same 'Hello', now BLOCKED locally before model execution. No restart.” |
| 00:39.334–00:45.450 | Activity: decyzja, wersja polityki i granica wykonania upstream. | “The audit explains the decision, policy version and execution boundary.” |
| 00:45.450–00:51.675 | Reguła finansowa opisana językiem naturalnym z oczekiwaniami. | “3. Describe a semantic rule in plain language, with explicit expected outcomes.” |
| 00:51.675–01:05.629 | Rzeczywisty przegląd Laya: osiem przypadków, przed zmianą i po zmianie; oczekiwanie pokazane w całości. | “Real Laya review: 8 scoped cases, active versus proposed policy. Waiting live.” |
| 01:05.629–01:13.838 | Wyniki 8/8: wejście i wyjście, modele i narzędzia. | “All 8 reviewed cases pass. Input + output, models + tools. No business call during review.” |
| 01:13.838–01:23.012 | Jawne potwierdzenie aktywuje v6 i zapisuje przypadki regresyjne. | “Explicit confirmation activates the tested policy and saves regression cases.” |
| 01:23.012–01:30.000 | Powrót do Overview; podsumowanie działania produktu. | “Fast local enforcement. Reviewed semantic policies. Visible, exportable decisions.” |
| 01:30.000–01:36.000 | Podgląd oryginalnego, syntetycznego PDF z adresami kontaktowymi. | “Source PDF preview: two pages of synthetic contact data. Original emails are visible here.” |
| 01:36.000–01:40.250 | Osobna sesja: ustawienia prywatności Redact i ocena Laya. | “4. Documents: local OCR, protected Markdown, then a real model response.” |
| 01:40.250–01:53.927 | Wysłanie dwustronicowego PDF do lokalnego OCR. | “Upload the actual two-page PDF. Local OCR extracts text; input privacy redacts matches.” |
| 01:53.927–02:00.979 | Chroniony Markdown z dwoma znacznikami redakcji; pobranie pliku. | “Two pages become approved Markdown. Synthetic email values are removed before model use.” |
| 02:00.979–02:14.847 | Przetworzenie dokumentu w trybie wywołania Qwen; widoczne oczekiwanie. | “Send protected Markdown to Qwen. The original PDF is not sent to the business model.” |
| 02:14.847–02:24.933 | Odpowiedź modelu, decyzja REDACTED, znalezione pii_email oraz poprawne kontrole wejścia i wyjścia. | “Real model output, with Laya input and output checks. No edited PDF is produced.” |

Zmianę zachowania `ALLOW → BLOCK` pokazuje reguła lokalna `Hello`. Sekwencja finansowa pokazuje ocenę próbek, aktywację oraz zapis testów: zabroniony przykład był już blokowany przez bazową ocenę bezpieczeństwa. Film nie dowodzi, że dopiero nowa reguła spowodowała tę blokadę, ani nie pokazuje osobnego finansowego wywołania po aktywacji.

### Sprawdzone przykłady reguły semantycznej

Instruction:

```text
Block personalized financial recommendations. General financial definitions are allowed.
```

Must block:

```text
Buy this stock immediately with all your savings.
```

Must pass:

```text
Define a stock as a financial instrument.
```

Zakres `both` / `all` daje osiem przypadków: dwa oczekiwania razy dwa kierunki razy dwa typy celu. Rzeczywisty przegląd w końcowym nagraniu przeszedł 8/8. Oczekiwanie na szesnaście ocen Laya pokazano bez skrótu. Przy samodzielnym powtórzeniu wynik nowej sesji nadal musi zostać sprawdzony przed aktywacją; wcześniejszy sukces nie zastępuje bieżącego przeglądu.

## Plan awaryjny i ręczne powtórzenie

1. Jeśli semantyczny przegląd nie przejdzie, pokaż niedopasowanie i niedostępną aktywację. To poprawne zachowanie produktu. Nie osłabiaj oczekiwań, aby uzyskać zielony wynik.
2. Następnie pokaż niezależną regułę deterministyczną: operator `contains`, wartość `Hello`, kierunek `input`, cel `model`. Sprawdź `Hello` jako pasujące i `Good morning` jako niepasujące. Przejrzyj zmianę i aktywuj; ponowne `Hello` powinno zostać zablokowane bez wywołania upstream.
3. Jeśli zabraknie modelu lub czasu, odtwórz dostarczone nagranie rzeczywistej sesji. Nazwij je nagraniem; nie przedstawiaj go jako działającego na żywo.
4. Aby odtworzyć produkt od zera, użyj osobnego katalogu i dostępnego Ollama. Pierwsze uruchomienie może pobierać wymagane składniki; wykonaj je przed prezentacją:

```bash
mkdir fastfence-presentation
cd fastfence-presentation
uv tool run --python 3.12 fastfence@1.0.7 --port 8020
```

Otwórz `http://127.0.0.1:8020`. Podłącz lokalną tożsamość agenta i administratora przed udostępnieniem ekranu. Wybierz model dostępny w aktywnej allowliście. Nowa domyślna instalacja może używać innego modelu biznesowego niż izolowane nagranie; treść reguły i kroki przeglądu pozostają takie same.

## Ręczne powtórzenie ochrony dokumentu

Użyj [dwustronicowego pliku demo-document.pdf](assets/demo-document.pdf).
Zawiera wyłącznie dane syntetyczne; widoczne w oryginale adresy `example.com`
służą do pokazania redakcji. Pracuj w osobnej instancji demonstracyjnej.

1. Ustaw akcję prywatności wejścia na **Redact**, pozostawiając rzeczywistą
   ocenę Laya wejścia i wyjścia. Nie wyłączaj kontroli, aby wymusić sukces.
2. W **Documents** wybierz `demo-document.pdf`, tryb **Download protected
   Markdown** i **Process document**. Sprawdź dwie strony, decyzję redakcji,
   znacznik `[REDACTED:pii_email]` oraz brak oryginalnych adresów.
3. W tym trybie model biznesowy nie jest wywoływany. **Download .md** pobiera
   zatwierdzony tekst, nie przerobiony PDF.
4. Wybierz **Send protected Markdown to a model** i model z aktywnej allowlisty.
   Po wykonaniu pokaż osobno chroniony Markdown, odpowiedź modelu i statusy
   kontroli wejścia oraz wyjścia. W przypadku błędu lub blokady pokaż rzeczywisty
   wynik; nie przedstawiaj go jako poprawnego wywołania.

Komentarz mówcy: „Plik trafia do lokalnego OCR. Adresy kontaktowe zastępujemy
znacznikami przed wywołaniem modelu. Model dostaje sprawdzony Markdown, a nie
oryginalny załącznik. To redakcja danych — nie pokaz odwracalnego szyfrowania.”

## Granice stwierdzeń na scenie

- Wynik 1000/1000 dotyczy silnika z kontrolowanym upstream; rzeczywisty test kolejki obejmuje 12 wywołań.
- Pomiar około 0,2 ms dotyczy deterministycznego silnika paczki 1.0.2, bez HTTP i generowania przez model. Nie przedstawiamy go jako opóźnienia całego produktu 1.0.7.
- Semantyczne reguły mogą mieć błędy. Nie deklarujemy pełnej zgodności z RODO ani uniwersalnego wykrywania ataków.
- Blokada odpowiedzi nie cofa skutków narzędzia, które już zostało wykonane.

Dowody: `evaluation/results/request-queue-1.0.7.json`, `evaluation/results/reviewed-semantic-workflow-1.0.6.json`, `docs/benchmarks.md`, `docs/integration-reference.md`.
