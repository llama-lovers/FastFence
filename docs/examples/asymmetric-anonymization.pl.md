# Anonimizacja z kluczem publicznym i prywatnym {#publicprivate-key-anonymization}

Ten przykład dodaje **szyfrowanie kluczem publicznym RSA i odtwarzanie kluczem prywatnym** do bezstanowej anonimizacji odwracalnej. RSA-3072 OAEP-SHA256 szyfruje nowy klucz AES-256-GCM dla każdego tokenu. Osobny klucz uwierzytelniania wystawcy, wyprowadzony z istniejącego lokalnego zbioru kluczy, uwierzytelnia całą kopertę przed odszyfrowaniem RSA. Implementacja korzysta z mechanizmów [RSA](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/) i [AEAD](https://cryptography.io/en/latest/hazmat/primitives/aead/) biblioteki cryptography.

Nie powstaje baza konwersacji ani mapowanie jawnymi wartościami. Weryfikacja tokenu pozostaje związana z zaufanym tenantem, tożsamością, odciskiem aktywnej reguły i terminem ważności. Stabilne identyfikatory w danym zakresie rozpoznają jednakowe wartości oryginalne; zaszyfrowane tokeny nadal są losowane.

## 1. Wygeneruj klucze raz {#1-generate-keys-once}

Po [zainstalowaniu FastFence](../getting-started.md) i rozpakowaniu [archiwum przykładów](../downloads/fastfence-examples.zip) do `examples/` wykonaj w katalogu instalacji:

```sh
uv tool run --python 3.12 fastfence@1.0.1 init --anonymization
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/asymmetric_keys.py
```

Pierwsze polecenie tworzy prywatny zbiór kluczy wystawcy, jeśli go brakuje. Drugie tworzy `state/private/anonymization-rsa/public.pem` i `private.pem` z uprawnieniami `0600`. Odmawia nadpisania któregokolwiek pliku. Ponowne wykonanie nie jest poleceniem rotacji kluczy.

Kompletny wykonywalny generator kluczy jest osadzony bezpośrednio ze źródła:

<!-- source: examples/docs/asymmetric_keys.py -->

## 2. Skonfiguruj bramkę {#2-configure-the-gateway}

Ustaw obie ścieżki w powłoce uruchamiającej FastFence lub dodaj te ustawienia do własnego `.env`:

```sh
export FASTFENCE_ANONYMIZATION_PUBLIC_KEY_FILE=state/private/anonymization-rsa/public.pem
export FASTFENCE_ANONYMIZATION_PRIVATE_KEY_FILE=state/private/anonymization-rsa/private.pem
uv tool run --python 3.12 fastfence@1.0.1 doctor
uv tool run --python 3.12 fastfence@1.0.1 serve
```

Względne ścieżki RSA są rozwiązywane względem `FASTFENCE_ROOT` (domyślnie katalog roboczy). Oba pliki PEM muszą opisywać tę samą parę RSA-3072 z wykładnikiem publicznym 65537. Istniejący zbiór kluczy wystawcy `state/anonymization-keys.json` nadal jest wymagany: samo szyfrowanie kluczem publicznym nie uwierzytelnia wystawcy tokenu i nie tworzy stabilnych aliasów opartych na kluczu.

Klucze są ładowane raz podczas startu. Po zmianie ustawień kluczy uruchom bramkę ponownie. Pełna bramka wymaga klucza prywatnego nawet przy wyłączonym przywracaniu odpowiedzi, ponieważ wewnętrznie odszyfrowuje otrzymane tokeny do kontroli zgodnie z aktualnymi zasadami. Nie zaimplementowano bramki przekazującej tylko z kluczem publicznym ani trybu odzyskiwania z kluczem wyłącznie po stronie klienta.

Przechowuj `private.pem` i zbiór kluczy wystawcy prywatnie, poza Git. Publiczny PEM można udostępniać jako publiczny klucz szyfrowania; samo jego posiadanie nie pozwala stworzyć podrobionego tokenu akceptowanego przez FastFence.

## 3. Włącz regułę odwracalną {#3-enable-a-reversible-rule}

W **Policies → Add anonymization rule** ustaw dopasowanie literalne, np. `Anna Kowalska`, etykietę zamiennika `PERSON` i właściwy zakres wejścia/wyjścia oraz modelu/narzędzia. Zezwól na jawne przywracanie, jeśli chcesz udostępnić tę opcję. Przejrzyj konfigurację kandydata i przed aktywacją ustaw tryb odzyskiwania **Reversible** w formularzu ustawień.

Poniżej znajduje się odpowiednia sekcja polityki. Dołącz ją do pełnej polityki zamiast zastępować cały plik:

```yaml
anonymization:
  enabled: true
  mode: reversible
  rules:
    - id: person
      operator: literal
      value: Anna Kowalska
      replacement: PERSON
      direction: both
      target: all
      allow_restore: true
```

Po skonfigurowaniu pary RSA nowe tokeny odwracalne zaczynają się od `[FFR2.`. Dotychczasowe symetryczne tokeny `[FFR1.` pozostają weryfikowalne, dopóki dostępny jest ich klucz wystawcy i pasująca reguła oraz nie upłynęła ważność. Zachowanie nieodwracalnych `[FFI1.` pozostaje bez zmian.

## 4. Sprawdź wejście i wyjście {#4-verify-input-and-output-behavior}

Użyj [przykładu chronionego żądania](protected-request.md) lub **Test requests**, aby wysłać tekst objęty regułą. Przy wyłączonym przywracaniu model otrzymuje token, a odpowiedź zachowuje chronioną postać wartości. Przy `restore_originals: true` w żądaniu i `allow_restore: true` w regule bramka może odtworzyć kompletne poprawne tokeny w dostarczanej odpowiedzi.

Model może pominąć lub zmienić tokeny. FastFence nie odtwarza niepełnego szyfrogramu i nie zgaduje brakującej wartości oryginalnej. Po przywróceniu nadal obowiązują kontrole prywatności i blokowania wyjścia; uprawnienie do przywracania ich nie zastępuje.

## Czas życia kluczy i wydajność {#key-lifetime-and-performance}

Ta implementacja ładuje **jedną parę RSA odbiorcy**. Jej wymiana uniemożliwia odczyt wcześniejszych tokenów FFR2, nawet jeśli zbiór kluczy wystawcy zachowuje stare klucze wystawcy. Zachowaj pierwotną parę przez wymagany okres odzyskiwania albo poczekaj na wygaśnięcie tokenów przed zmianą; automatyczna rotacja wielu odbiorców nie jest zaimplementowana. Usunięcie klucza wystawcy unieważnia także tokeny nim uwierzytelnione.

Koperty RSA dodają bajty i operacje asymetryczne względem tokenów symetrycznych. Konfiguracja jest odczytywana tylko przy starcie, ale ten tryb nie ma deklarowanej latencji równej lokalnemu dopasowaniu literalnemu. Nadal obowiązują ograniczenia długości tokenu i wartości, rozmiaru żądania oraz liczby zamian; zbyt duże wartości są odrzucane.
