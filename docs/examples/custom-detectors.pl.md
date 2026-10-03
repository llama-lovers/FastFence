# Napisz własne detektory tekstu w Pythonie {#write-custom-python-text-detectors}

Dodaj własne frazy literalne i wyrażenia regularne w plikach Pythona rozszerzających detect-secrets. Detektory działają razem z wbudowanymi detektorami tokenów i kluczy FastFence na zagnieżdżonych wartościach wejściowych i wyjściowych, w tym kluczach słowników. Dopasowanie uruchamia działanie prywatności z aktywnej polityki: blokowanie lub redakcję.

## Zainstaluj i skonfiguruj {#install-and-configure}

Po [zainstalowaniu FastFence](../getting-started.md) pobierz [archiwum przykładów](../downloads/fastfence-examples.zip) i rozpakuj pliki do `examples/` w katalogu instalacji. Kompletny przykład używa wartości syntetycznych i nie wymaga repozytorium źródłowego:

```sh
uv tool run --python 3.12 fastfence@1.0.1 init --anonymization
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/custom_detector.py
export FASTFENCE_SECRET_PLUGIN_FILES='["examples/custom_detector.py"]'
uv tool run --python 3.12 fastfence@1.0.1 doctor
uv tool run --python 3.12 fastfence@1.0.1 serve
```

Zachowaj tę zmienną środowiskową w terminalu lub konfiguracji usługi uruchamiającej FastFence. Ścieżki są rozwiązywane względem `FASTFENCE_ROOT` (domyślnie katalog roboczy). Po edycji pluginu uruchom proces ponownie: już załadowany kod pozostaje w pamięci. Żądania przechodzące kontrolę wejścia i docierające do modelu nadal wymagają standardowej konfiguracji Laya/Ollama z instrukcji instalacji.

Ustawienie przyjmuje maksymalnie osiem lokalnych plików `.py`, łącznie do 32 klas detektorów. Domyślnie plik może mieć do 65 536 bajtów; operator może ustawić `FASTFENCE_SECRET_PLUGIN_MAX_FILE_BYTES` między 1 024 a 1 048 576. Nazwy klas muszą być unikalne wśród wszystkich detektorów własnych i wbudowanych. Niepoprawny lub brakujący plugin zatrzymuje start; nie jest pomijany bez informacji.

## Zdefiniuj reguły literalne i regex {#define-literal-and-regex-rules}

`CompanyCodeDetector` dopasowuje `ACME-DEMO-1234` i literalną frazę `PROJECT ORCHID INTERNAL`. Używaj `re.escape(...)`, gdy ciąg ma być traktowany literalnie, łącznie z interpunkcją. `InternalPhraseDetector` pokazuje bazowy interfejs własnego dopasowywania w Pythonie. Zwracaj przez `yield` dokładny, niepusty fragment do usunięcia, zachowując oryginalną wielkość liter.

<!-- source: examples/docs/custom_detector.py -->

Detektory regex dostarczają od jednego do 32 skompilowanych wzorców Python `re`, każdy o długości maksymalnie 8 192 znaków. Wzorce dopasowujące pusty ciąg są odrzucane. FastFence maskuje całe dopasowanie regex, również przy użyciu grup przechwytujących. Detektory bazowe zwracają dokładne dopasowane fragmenty. Detektor może zwrócić maksymalnie 4 096 kandydatów dla jednej analizowanej postaci tekstu; niepoprawne wyniki lub wyjątki odrzucają żądanie ze stałym powodem niedostępności detektora.

Rozszerzenie korzysta z interfejsów [BasePlugin i RegexBasedDetector](https://github.com/Yelp/detect-secrets/blob/v1.5.0/detect_secrets/plugins/base.py) projektu źródłowego. FastFence wywołuje `analyze_string` bezpośrednio i nie wywołuje `verify` ani globalnego mechanizmu skanowania plików biblioteki.

## Wybierz zachowanie wejścia i wyjścia {#choose-input-and-output-behavior}

W `config/policy.yaml` swojej instalacji zachowaj pozostałe pola i ustaw:

```yaml
privacy:
  enabled: true
  input: block
  output: redact
```

Aktualizując działającą bramkę, zwiększ istniejącą wersję `version` na najwyższym poziomie. Możesz też zmienić politykę przez konsolę. Te ustawienia odrzucają wejście z własnym dopasowaniem przed wywołaniem modelu, a własne dopasowania w wyjściu modelu/narzędzia zastępują `[REDACTED:detect_secrets]`. Zmień odpowiednią akcję na `redact` lub `block` zgodnie z potrzebami. Akcje obejmują wszystkie detektory sekretów; osobne nadpisywanie akcji dla konkretnego detektora nie jest obecnie obsługiwane.

Przy działającej bramce uruchom pobrany klient w drugim terminalu:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/protected_request.py --prompt 'Please summarize ACME-DEMO-1234'
```

Przy blokowaniu wejścia oczekuj `decision: blocked`, `reason: input_sensitive_data`, `upstream_executed: false` i stałego oznaczenia `detect_secrets_CompanyCodeDetector`. Redakcja wejścia usuwa dopasowanie przed kolejnymi kontrolami i wykonaniem zadania. Wyłączenie `privacy.enabled` wyłącza również ten skan prywatności.

## Granica zaufania operatora {#operator-trust-boundary}

Pliki pluginów to zaufany wykonywalny Python z uprawnieniami procesu serwera. Sprawdzaj je jak kod aplikacji. Funkcje dopasowujące powinny być bezstanowe, szybkie, bez dostępu do plików i sieci, logowania ani efektów ubocznych. Unikaj wyrażeń regularnych z nadmiernym nawrotem. Ograniczenia plików i kandydatów nie izolują kodu Pythona i nie narzucają twardego limitu czasu dowolnego pluginu.

Pliki wybierają wyłącznie zaufane ustawienia startowe. Żądania HTTP, aktualizacje polityk i konfiguracja zdalna nie mogą przesyłać ani wybierać wykonywalnych pluginów. FastFence ładuje kod przy starcie i nie odczytuje plików ponownie podczas żądań; sam nigdy nie loguje dopasowanego tekstu. Autorzy pluginów odpowiadają za operacje wejścia/wyjścia i logowanie wykonywane przez ich kod.
