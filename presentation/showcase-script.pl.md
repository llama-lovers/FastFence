# FastFence — pokaz wartości produktu

Film v2 ma angielskie napisy i instrumentalną muzykę, bez lektora. Materiał
wykorzystuje rzeczywiste nagranie publicznej paczki 1.0.7. Montaż skraca pokaz,
dlatego długość scen nie jest pomiarem czasu odpowiedzi.

## Główna myśl

**Zmieniasz zasady ochrony podczas pracy agenta, bez przebudowy jego kodu.**

Regułę możesz opisać słowami, sprawdzić na przykładach i świadomie aktywować.
Ten sam system kontroluje wejście i wyjście. Precyzyjne reguły lokalne działają
przed oceną modelu. Dokumenty przechodzą przez OCR i kontrolę danych, zanim ich
tekst trafi do modelu biznesowego.

## Otwarcie — około 20 sekund

„Agent może mieć prawidłowy token dostępu i nadal wysłać poufne dane do modelu.
A kiedy zmienia się polityka firmy, nie chcemy poprawiać każdej integracji.
FastFence pozwala zmienić zasady w jednym miejscu i zastosować je podczas pracy
agenta. Za chwilę zobaczycie tę zmianę na rzeczywistym żądaniu.”

## Pokaz filmu

Uruchom `output/fastfence-demo-v2.mp4` na pełnym ekranie z dźwiękiem.
Film sam objaśnia kolejne sceny po angielsku. Nie trzeba czytać podpisów na głos.

W pokazie są dwa odrębne mechanizmy reguł. Lokalna reguła dotycząca `Hello`
rzeczywiście zmienia wynik z ALLOW na BLOCK. Reguła semantyczna pokazuje opis
słowny, przegląd ośmiu przykładów i aktywację. Nie przypisujemy jej zmiany decyzji,
która nastąpiła dzięki regule lokalnej.

## Zamknięcie — około 35 sekund

„Wartość FastFence polega na tym, że polityka staje się działającą kontrolą,
którą można zmienić bez wdrażania agenta od nowa. Widzieliście zablokowane
wywołanie przed uruchomieniem modelu i dokument, którego treść pozostała użyteczna
po usunięciu adresów kontaktowych.

Dbamy też o zachowanie podczas zmian i awarii. Błędna konfiguracja pozostawia
ostatnią poprawną politykę. Żądanie wychodzące z kolejki ponownie przechodzi
kontrolę aktualnych reguł. Ponowne przygotowanie instalacji zachowuje konfigurację,
poświadczenia i klucze. Produkt jest dostępny na PyPI: uv tool run fastfence.”

## Odpowiedzi na pytania techniczne

- **Dynamiczność:** walidowany snapshot polityki zmienia się bez restartu.
  W filmie ten sam request przechodzi przy v4 i zostaje zablokowany przy v5.
- **Niezawodność:** konkretnymi gwarancjami są zachowanie ostatniej poprawnej
  konfiguracji, ograniczona kolejka i blokowanie żądania przy awarii wymaganej
  oceny semantycznej. Nie oznacza to bezbłędności samego modelu.
- **Idempotencja:** dotyczy przygotowania instalacji. Ponowienie zachowuje
  istniejące pliki i klucze. Nie deklarujemy deduplikacji żądań biznesowych.
- **Szybkość:** lokalne dopasowania poprzedzają inference. Blokada lokalna w filmie
  nie wykonuje modelu. Historyczny benchmark ma osobno opisaną wersję i zakres.
- **Prywatność:** w filmie dwa adresy e-mail zastępują znaczniki redakcji.
  Model biznesowy otrzymuje chroniony Markdown. Film nie pokazuje przywracania
  danych za pomocą klucza prywatnego.
- **Zakres:** ta sama ścieżka kontroli obsługuje REST, OpenAI-compatible, MCP
  i synchroniczny tekstowy ACP. Materiał przedstawia integrację modelową i OCR.

Szczegółowe wyniki i źródła twierdzeń: [evidence.md](evidence.md).
