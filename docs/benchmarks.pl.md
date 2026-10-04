# Benchmarki

Mierz FastFence na sprzęcie i z polityką, których zamierzasz używać. Lokalne sprawdzenie reguły tekstowej, pełne wywołanie bramki i żądanie oceniane przez Layę wykonują różną pracę. Wyniki poniżej wskazują, którą ścieżkę zmierzono.

## OFF / deterministyczne / semantyczne — paczka 1.0.2

Rzeczywiste pomiary z publicznej paczki PyPI 1.0.2, wykonane 4 października 2026 na Apple M3 Pro. Wszystkie wiersze używają tej samej krótkiej syntetycznej treści i odpowiedzi narzędzia, współbieżność 1. OFF i kontrole deterministyczne zmierzono razem; Layę w osobnym przebiegu na tej samej maszynie.

| Tryb | Próbek + rozgrzewka | p50 (ms) | p95 (ms) | p99 (ms) |
| --- | ---: | ---: | ---: | ---: |
| OFF — odpowiedź syntetyczna | 2000 + 100 | 0.000125 | 0.000167 | 0.000208 |
| Kontrole deterministyczne ON | 2000 + 100 | 0.206125 | 0.247500 | 0.643750 |
| Laya semantyczne ON — wejście i wyjście | 20 + 2 | 1117.160333 | 1199.532000 | 1222.141500 |

**OFF** omija wszystkie kontrole, walidację tożsamości, budżety i audyt. Mierzy jedynie stałą odpowiedź funkcji bez I/O; wartości bliskie rozdzielczości timera nie reprezentują opóźnienia rzeczywistego modelu ani API. Nie ekstrapoluj z nich produkcyjnej przepustowości. Pomiary ON obejmują wykonane kontrole; semantyczny dodatkowo dwie rzeczywiste oceny Qwen. Wszystkie trzy warianty pomijają wejściowy transport bramki HTTP/MCP oraz generowanie modelu biznesowego. Pomiar Laya obejmuje komunikację z lokalną Ollamą podczas oceny.

[Raport OFF i deterministic ON](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-package-1.0.2-comparison.json) zachowuje także pomiar współbieżności 8 i rzeczywisty wolniejszy ogon p99. [Raport semantic ON](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-package-1.0.2-semantic.json) ma tylko 20 próbek: p99 jest tu największą obserwacją, nie stabilnym oszacowaniem ogona rozkładu. Szczegóły środowiska i zakresu podano poniżej.

## Wyniki paczki 1.0.2 — 4 października 2026

Pomiar uruchomiono z wyeksportowanego ZIP na **publicznej paczce PyPI 1.0.2**, zainstalowanej w nowym środowisku poza checkoutem. Sprawdzono pochodzenie importów, wszystkie oczekiwane decyzje i rozliczenie budżetu.

Apple M3 Pro, 11 logicznych CPU, 18 GiB RAM, macOS 27.0.1 arm64, Python 3.12.12, Pydantic 2.13.5 i detect-secrets 1.5.0. Jeden proces, 2 000 próbek i 100 wywołań rozgrzewki na wiersz: łącznie 12 000 pomiarów i 600 wywołań rozgrzewki. Pomiar wykonano o 00:12 UTC.

**Zakres:** pełne wywołanie silnika przez API Pythona, detect-secrets, budżety w pamięci i audyt. Kontrola semantyczna wyłączona; syntetyczna odpowiedź narzędzia bez opóźnienia. Bez HTTP/MCP i generowania modelu biznesowego. Wejścia mają 31, 45 i 38 bajtów odpowiednio dla dozwolonego żądania, sygnatury i uprawnień.

| Ścieżka | Współbieżność | p50 (ms) | p95 (ms) | Żądań/s |
| --- | ---: | ---: | ---: | ---: |
| Dozwolone żądanie | 1 | 0.204625 | 0.227500 | 4757.87 |
| Blokada sygnatury | 1 | 0.031125 | 0.038167 | 29740.33 |
| Blokada uprawnień | 1 | 0.012000 | 0.015167 | 76225.32 |
| Dozwolone żądanie | 8 | 0.203834 | 0.228625 | 4681.31 |
| Blokada sygnatury | 8 | 0.031625 | 0.037333 | 27566.10 |
| Blokada uprawnień | 8 | 0.012042 | 0.014542 | 63487.61 |

[Pełny raport JSON](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-package-1.0.2-deterministic.json) zawiera także p99, zużycie pamięci procesu i sumy kontrolne obciążeń. Większa współbieżność nie poprawiła tutaj przepustowości; to jeden proces z lokalną pracą CPU. Tych wyników nie należy utożsamiać z czasem domyślnego żądania ocenianego przez Layę.

### Rzeczywista ocena Laya: wejście i wyjście

Osobny pomiar na tej samej maszynie i publicznej paczce 1.0.2 użył **Laya + qwen3:4b (Q4_K_M)**. Próg 0.7, limit czasu 60 s, ocena wyjścia włączona. Każdy wiersz obejmuje 20 mierzonych żądań i 2 wywołania rozgrzewki, współbieżność 1. Raport zapisano o 00:13 UTC.

| Ścieżka | p50 (ms) | p95 (ms) | Żądań/s | Wywołań oceny z rozgrzewką |
| --- | ---: | ---: | ---: | ---: |
| Dozwolone żądanie, ocena wejścia i wyjścia | 1117.160333 | 1199.532000 | 0.88 | 44 |
| Wczesna blokada sygnatury | 0.034042 | 0.042167 | 24451.13 | 0 |
| Wczesna blokada uprawnień | 0.013000 | 0.017166 | 51847.05 | 0 |

Dozwolone żądanie wykonuje dwie rzeczywiste oceny modelu. `median_ms` wyniósł 1119.5705 ms; p50 w tabeli używa metody najbliższej rangi, a nie średniej dwóch środkowych obserwacji. Wczesne blokady nie wywołują modelu.

To krótka próba z powtarzanym, stałym promptem i rozgrzanym modelem; cache prefiksów/KV Ollamy może pomagać. Wynik nie opisuje zimnego startu, zmiennych długich rozmów ani jakości wykrywania ataków. Odpowiedź narzędzia nadal jest syntetyczna. [Pełny raport Laya](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-package-1.0.2-semantic.json) zawiera pełny digest modelu, konfigurację i dowody rozliczenia.

## Uruchom pomiar z zainstalowanej paczki

Zainstaluj [uv](https://docs.astral.sh/uv/getting-started/installation/), a następnie pobierz pakiet benchmarków. Pomiar deterministyczny nie wymaga checkoutu FastFence ani działającej bramki.

```bash
curl -L https://fastfence.dev/downloads/fastfence-benchmarks.zip -o fastfence-benchmarks.zip
uv run --no-project --python 3.12 python -m zipfile -e fastfence-benchmarks.zip benchmarks
uv run --no-project --python 3.12 python benchmarks/scripts/benchmark_package.py \
  --pypi-version 1.0.2 --samples 2000 --warmup 100 --concurrency 1 8 \
  --output results.json
```

Skrypt instaluje dokładnie wskazaną publiczną paczkę PyPI w nowym środowisku tymczasowym, sprawdza, że `fastfence` importuje się z zainstalowanej paczki, i uruchamia dołączone obciążenie poza Twoim projektem. Tworzy osobne syntetyczne polityki i tożsamości; nie korzysta z konfiguracji Twojej bramki i jej nie zmienia. Obok czasów zapisuje rzeczywiste wersje zależności, sprzęt, oczekiwane decyzje i kontrole rozliczania budżetu. Pierwsze uruchomienie może pobierać zależności Pythona; instalacja paczki nie wchodzi do mierzonego czasu.

Domyślny pomiar używa ścieżki deterministycznej i syntetycznej odpowiedzi narzędzia bez oczekiwania. Mierzy lokalną pracę kontroli; nie reprezentuje domyślnej ścieżki produktu z włączoną Layą. Współbieżność 1 i 8 to osobne pomiary, nie test skalowania poziomego.

Aby dodatkowo zmierzyć rzeczywistą Layę, uruchom Ollamę i wykonaj polecenie, gdy model nie obsługuje innych zadań:

```bash
uv run --no-project --python 3.12 python benchmarks/scripts/benchmark_package.py \
  --pypi-version 1.0.2 --semantic --samples 20 --warmup 2 --concurrency 1 \
  --output semantic-results.json
```

Ten pomiar przygotowuje skonfigurowane środowisko oceny i model w osobnym katalogu roboczym. Wywołania modelu, rozgrzewka i mierzone żądania mogą zużyć dużo czasu i pamięci. Odpowiedź docelowego narzędzia pozostaje syntetyczna, więc mierzymy kontrolę semantyczną z lokalnym wywołaniem, nie generowanie przez model biznesowy. Dwadzieścia próbek daje jedynie wstępny obraz opóźnień; zachowaj metadane modelu i środowiska oraz zwiększ liczbę próbek do rzetelnego porównania wolniejszych odpowiedzi.

## Jak czytać pomiary

- **p50** to 50. percentyl opóźnienia (w raportach: metoda najbliższej rangi): połowa zmierzonych żądań zakończyła się w tym czasie lub szybciej.
- **p95** to czas, w którym zakończyło się 95% zmierzonych żądań. Opisuje wolniejsze żądania lepiej niż średnia.
- **p99** to 99. percentyl; małe próbki nie pozwalają wiarygodnie opisać tak rzadkich opóźnień.
- **Przepustowość** to liczba zakończonych żądań podzielona przez rzeczywisty czas pomiaru, wyrażona w żądaniach na sekundę. Większa współbieżność może zwiększyć przepustowość i jednocześnie wydłużyć pojedyncze żądanie.
- **Rozgrzewka** przygotowuje środowisko, ale jej wywołania nie wchodzą do próbki opóźnień. Nadal wpływają na cache, audyt i budżety.

Benchmark silnika mierzy pełne wywołania wewnątrz procesu, w tym skonfigurowane kontrole, rezerwację i rozliczanie budżetu w pamięci oraz ograniczony bufor audytu. Pomija transport HTTP/MCP, start procesu i odczyt konfiguracji. Wariant bez oczekiwania zwraca stałą syntetyczną odpowiedź; wariant z opóźnieniem celowo czeka 15 ms. Żaden z nich nie mierzy modelu biznesowego.

Ocena Laya wymaga osobnych pomiarów z rzeczywistym skonfigurowanym modelem. Włączenie kontroli semantycznych dodaje czas inferencji i może zmienić ścieżkę decyzji. Żądanie odrzucone przez regułę deterministyczną może całkowicie ominąć model. Raportuj te ścieżki osobno; szybka blokada wejścia nie określa czasu dozwolonego wywołania modelu.

## Weryfikacja zachowania poza pomiarem szybkości

Publiczna paczka 1.0.2 przeszła **143/143 istniejących parametryzowanych regresji bezpieczeństwa**, bez pominiętych przypadków. Testy uruchomiono w nowym środowisku poza checkoutem; połączenia sieciowe blokowano, a granice usług i oceny semantycznej były kontrolowane przez testy. To weryfikacja uprawnień, blokad, redakcji, budżetów, sygnatur i kompozycji kontroli — nie 143 nowych ataków ani pomiar skuteczności modelu. [Raport testów paczki](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-security-1.0.2.json).

Osobne uruchomienie rzeczywistej paczki przez jedną komendę sprawdziło Layę, OCR i zmianę aktywnej polityki bez restartu: **ALLOW v1 → BLOCK v2 → ALLOW v3 → blokada budżetu v4 → ALLOW v5** w tej samej instancji. Powtórny start zachował prywatny stan. [Raport rzeczywistego przebiegu](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-one-command-1.0.2.json) zawiera wyłącznie wyniki; bez promptów, odpowiedzi modelu i poświadczeń.

## Zapisane pomiary z 3 października 2026

To historyczne pomiary rozwojowe, **nie wyniki aktualnego wydania paczki**. Raport transportu wskazuje FastFence 0.1.0. Raporty mikrobenchmarków nie określają wydania paczki; poniżej są linki do surowych raportów i kodu.

Raporty silnika i transportu zapisują Apple M3 Pro, 11 logicznych CPU, 18 GiB RAM, macOS 27.0.1 arm64 i Python 3.12.12. Użyto jednego procesu; wybrane wiersze poniżej mają współbieżność 1. Nie kontrolowano aplikacji w tle ani stanu energetycznego CPU.

| Zmierzona ścieżka | Próbek | p50 (ms) | p95 (ms) | Żądań/s |
| --- | ---: | ---: | ---: | ---: |
| Silnik, dozwolone żądanie, detect-secrets włączone, odpowiedź bez oczekiwania | 2,000 | 0.131875 | 0.141625 | 7,530.61 |
| Bramka HTTP, dozwolone żądanie, symulowany backend 15 ms | 100 | 25.022 | 29.191 | 39.041 |
| Jedna reguła dosłowna, wejście 128 bajtów, brak dopasowania | 2,000 | 0.001083 | 0.001250 | Nie mierzono |
| 64 reguły dosłowne, wejście 65,536 bajtów, brak dopasowania | 2,000 | 0.276750 | 0.317000 | Nie mierzono |
| Odwracalny token AES-GCM, syntetyczny email, zamiana i przywrócenie | 1,000 | 0.035250 | 0.035875 | Nie mierzono |

Wiersz silnika obejmuje 100 wyłączonych z pomiaru wywołań rozgrzewki; HTTP ma ich 20, reguły 100, a token 100. Pomiary reguł pomijają kontrole prywatności, budżety, audyt i transport. Pomiar tokenu pomija inicjalizację kluczy, dopasowywanie w większych danych, transport i modele; dotyczy symetrycznych tokenów FFR1, nie kopert RSA.

Pełne surowe raporty: [silnik z detect-secrets](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/detect-secrets-runtime-benchmark.json), [transport HTTP/MCP](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/transport-benchmark.json), [dosłowne reguły tekstowe](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/authored-text-rules-benchmark.json), [bezstanowe tokeny](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/stateless-token-benchmark.json). Zawierają zakres pomiaru i dodatkowe przypadki; wybór tych wierszy nie czyni obciążeń równoważnymi.

## Powtarzalne porównania

Zachowaj surowy raport JSON z wersją paczki, Pythona i zależności, CPU/systemem/RAM, liczbą próbek, rozgrzewką, współbieżnością, rozmiarem danych i aktywnymi regułami. Dla pomiarów z modelem zapisz też model, czy był już załadowany oraz które etapy oceny wejścia i wyjścia wykonano. Porównuj takie samo obciążenie i współbieżność na tej samej maszynie.

Użyj odpowiedniej liczby próbek, aby zaobserwować wolniejsze żądania. p95 z dziesięciu próbek dostarcza bardzo mało informacji o najwolniejszych odpowiedziach. Powtarzaj pomiary i zachowuj błędy oraz nieoczekiwane decyzje; poprawna odpowiedź HTTP może nadal oznaczać blokadę żądania. Przerwij porównanie, jeżeli oczekiwane decyzje lub rozliczenie budżetu nie przechodzą walidacji.

Te liczby są obserwacjami na jednej maszynie deweloperskiej, nie SLA ani gwarancją wydajności. Nie odejmuj czasu endpointu health od chronionego żądania, aby wyznaczyć czysty narzut bezpieczeństwa: te endpointy wykonują różną pracę. Pomiar przepustowości nie mierzy również jakości wykrywania zagrożeń.
