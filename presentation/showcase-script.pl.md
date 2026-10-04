# FastFence — pokaz wartości produktu

Film v4 trwa 3:00 i ma angielskie napisy oraz instrumentalną muzykę, bez lektora.
Pokazuje rzeczywiste nagranie publicznej paczki 1.0.7 oraz wyniki osobnych prób
OpenAI SDK, MCP, ACP i przywracania zaszyfrowanych danych. Sceny kodu i odpowiedzi
odtwarzają oczyszczone zapisy tych prób. Montaż skraca pokaz, dlatego długość scen
nie jest pomiarem czasu odpowiedzi.

## Samodzielne trzyminutowe demo

Film zajmuje pełne trzy minuty. Dodatkowe przemówienie wydłuża pokaz. Prezentacja
ma dokładnie dziesięć slajdów i może służyć jako osobna forma pitchu.

Opcjonalne otwarcie: „FastFence pozwala zmienić ochronę agenta bez
przepisywania jego kodu. Pokażemy integrację, zmianę polityki i jej rzeczywisty
skutek, a następnie ochronę dokumentu.”

Uruchom film `output/fastfence-demo-v4.mp4`, 3 minuty.

Opcjonalne zamknięcie: „Ten sam klient działa dalej, a nowa polityka zmienia
wynik wywołania. Reguły sprawdzamy przed aktywacją, a błędna konfiguracja nie
zastępuje poprawnej. Lokalna kontrola poprzedza ocenę modelu. FastFence uruchamiamy
z PyPI poleceniem uv tool run fastfence.”

Dłuższe notatki poniżej służą prezentacji bez filmu i odpowiedziom na pytania.

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

Uruchom `output/fastfence-demo-v4.mp4` na pełnym ekranie z dźwiękiem.
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
  Model biznesowy otrzymuje chroniony Markdown. Osobna próba pokazuje szyfrowane
  tokeny FFR2 i przywrócenie syntetycznego imienia oraz nazwiska po włączeniu
  opcji. Przywrócenie wymaga klucza prywatnego i zgody reguły. Lokalna operacja
  echo widzi wyłącznie chronione dane, niezależnie od ustawienia przywracania.
  Ten przykład nie używa modelu i nie zakłada, że model zawsze zachowa token.
- **Zakres:** ta sama ścieżka kontroli obsługuje REST, OpenAI-compatible, MCP
  i synchroniczny tekstowy ACP. Film pokazuje klienta OpenAI, rzeczywiste
  wywołanie MCP oraz ACP do lokalnego agenta. W obu integracjach narzędziowych
  powtórzenie po aktywacji reguły nie zwiększa licznika wykonań backendu.

Szczegółowe wyniki i źródła twierdzeń: [evidence.md](evidence.md).
