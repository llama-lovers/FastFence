# Polityki i kontrole bezpieczeństwa

## Źródła konfiguracji

FastFence odczytuje `config/policy.yaml` i `config/signatures.json` przy starcie. Proces w tle domyślnie sprawdza aktualizacje co dwie sekundy. Każde żądanie pobiera przez referencję jeden głęboko niezmienny snapshot polityki i sygnatur. Odczyt i walidacja konfiguracji odbywają się poza deterministyczną ścieżką żądania.

Zmiana treści polityki wymaga wyższego `policy.version`, a zmiana sygnatur — wyższego `feed.version`. Aktualizacja samych sygnatur może zachować wersję polityki. Błędne aktualizacje, konflikty wersji i awarie źródła pozostawiają ostatni poprawny snapshot. Start wymaga poprawnej konfiguracji.

Panel administracyjny umożliwia edycję i zapis lokalnej polityki z podniesieniem wersji. Uwierzytelniony administracyjnie `POST /api/admin/reload` żąda natychmiastowego przeładowania. Diagnostyka konfiguracji pokazuje rodzaj źródła, generację, liczniki odświeżeń i kody błędów bez poufnych danych.

Dla centralnego źródła ustaw `FASTFENCE_CONFIG_URL` na zaufany endpoint HTTPS. HTTP jest dozwolone tylko dla adresu pętli zwrotnej. Endpoint musi zwracać obiekt JSON z dokładnie dwoma polami:

```json
{
  "policy": {"...": "complete policy object"},
  "feed": {"...": "complete signature feed object"}
}
```

To ilustracja struktury pakietu, a nie poprawna polityka. Oba obiekty wewnętrzne muszą spełniać te same schematy co pliki lokalne. Przekierowania są wyłączone, a pobieranie ma limit czasu całej odpowiedzi i jej rozmiaru. Zdalną politykę zmienia się u źródła; zapis przez panel bramki nie może jej nadpisać.

Ustawienia odświeżania, czasu, rozmiaru, tożsamości i usług docelowych opisano w [konfiguracji](settings.md).

## Pola polityki

| Pole | Przeznaczenie |
| --- | --- |
| `tools` | Jawna lista dozwolonych narzędzi biznesowych, role, czas i szacowany koszt wywołania. |
| `models` | Jawna lista dozwolonych modeli odpowiedzi, role, limit tokenów, czas i szacowany koszt. |
| `budgets` | Limity ról: wywołania, jednostki tokenów, koszt w mikro-USD, czas w milisekundach i współbieżność. |
| `privacy` | Włączenie kontroli prywatności oraz wybór `block` lub `redact` dla wejścia i wyjścia. |
| `signatures_enabled` | Włączenie literalnych sygnatur ataków na wejściu i wyjściu. |
| `semantic` | Wybór `laya` (domyślnie), `disabled`, `ollama` lub `kev`; model oceniający, próg, czas, skanowanie wyjścia i opcjonalne instrukcje tylko dla Laya. |
| `max_input_bytes`, `max_output_bytes` | Limity rozmiaru serializowanych danych UTF-8, także po usunięciu danych poufnych. |

Zapis administracyjny sprawdza również dokładny rozmiar zserializowanego YAML względem limitu źródła przed podmianą pliku lub snapshotu. Zbyt duża propozycja zachowuje ostatnie poprawne źródło, które nadal można odczytać po odświeżeniu i restarcie.

Każda dozwolona rola potrzebuje budżetu. Role, tenanty i nagłówki podane przez klienta nie nadają dostępu: określają go zaufane rekordy tożsamości przy starcie. Nadanie roli nie uprawnia do celu nieobecnego na aktywnej liście dozwolonych operacji.

## Blokowanie i redakcja

Dostarczona polityka blokuje wykryte dane poufne na wejściu i redaguje je na wyjściu:

```yaml
privacy:
  enabled: true
  input: block
  output: redact
```

Zmień `input` na `redact`, aby przekazywać usłudze docelowej treść po usunięciu danych poufnych. Zmień `output` na `block`, aby wstrzymać poufną odpowiedź. Przy edycji pliku zwiększ wersję polityki.

Redakcja nie omija ograniczeń treści. Bramka sprawdza oryginał, a następnie ponownie stosuje lokalne reguły tekstowe i sygnatury do wyniku po redakcji przed przekazaniem lub dostarczeniem. Przykładowo zakaz `a` bez rozróżniania wielkości liter odrzuci także `A` w `[REDACTED:pii_polish_id]`. Takie wejście zostaje zablokowane przed wywołaniem, a wyjście — po wykonaniu operacji. Podgląd stosuje tę samą kolejność. Treść bez wykrytych danych poufnych nie wymaga dodatkowego skanowania.

Prywatność łączy heurystyki z **detect-secrets 1.5.0** poprzez 19 lokalnych detektorów formatów danych dostępu i słów kluczowych. Obejmuje reprezentatywne formaty GitHub, GitLab, Slack, AWS, Azure, JWT i kluczy prywatnych oraz adresy email i inne wzorce heurystyczne. Sprawdzane są zagnieżdżone klucze i wartości. Wyniki zawierają stałe nazwy detektorów, nigdy wartości sekretów.

Detektory powstają przy starcie. Analiza żądania nie weryfikuje danych dostępu przez sieć, nie skanuje plików i ignoruje bazę wyjątków repozytorium oraz komentarze klienta deklarujące wyjątki. Błąd detektora blokuje wynik z bezpiecznym opisem przyczyny. Wyłączenie `privacy.enabled` wyłącza oba składniki prywatności.

Stosowana jest normalizacja Unicode NFKC. Ograniczone odtwarzanie podziałów wiersza obejmuje pojedynczy tekst do 4096 znaków i ośmiu podziałów. Fragmenty między osobnymi wiadomościami lub polami nie są łączone. Wykrywanie pozostaje heurystyczne; nie rozpoznaje wszystkich możliwych sekretów i danych osobowych.

## Sygnatury znanych ataków

Źródła zagrożeń zawierają ograniczone wzorce tekstowe, a nie wykonywalne reguły lub dowolne wyrażenia regularne użytkownika. Dopasowanie stosuje NFKC i normalizację wielkości liter, usuwa typowe separatory zerowej szerokości i dopuszcza do ośmiu białych znaków między znakami literału. Granice identyfikatorów zapobiegają dopasowaniu niebezpiecznego identyfikatora wewnątrz dłuższej zwykłej nazwy.

Sprawdzana jest jedna warstwa dekodowania procentowego i tekstowego base64 w drukowalnym UTF-8. Sąsiadujące teksty na liście mogą być odtworzone; niepowiązane pola słownika nie są łączone. Przekroczenie limitów głębokości, liczby węzłów, łącznej treści, dekodowanych danych i wariantów blokuje żądanie. Kontrole nie wykonują, nie deserializują i nie dekodują rekurencyjnie danych.

Przykładowo dodaj wzorzec do kompletnego źródła sygnatur i zwiększ jego wersję:

```json
{
  "id": "restricted_project_name",
  "pattern": "Project Nightfall",
  "description": "Block the configured project-name pattern"
}
```

Wzorzec ma 4–256 znaków, a źródło obsługuje do 200 sygnatur. Opcjonalny `match_mode: "token_sequence"` dopasowuje bezpiecznie escapowane tokeny oddzielone białymi znakami, z `max_gap` do 256 znaków. Dostarczona sygnatura powłoki używa `curl | sh` w tym trybie, dopuszczając URL między poleceniem a potokiem bez przyjmowania dowolnego regexu.

Dopasowanie na wejściu blokuje przed wykonaniem operacji. Dopasowanie na wyjściu wstrzymuje odpowiedź po wykonaniu; audyt zachowuje ID sygnatur i `upstream_executed`. Ten sam znormalizowany matcher korzysta z wersjonowanego zewnętrznego źródła aktualizowanego poza ścieżką żądania.

Wzorce obejmują przykładowe ciągi związane z ładowaniem pickle/PyTorch, zdalną powłoką i nadpisywaniem instrukcji. Cytowane opisy zawierające dokładny niebezpieczny wzorzec także bywają blokowane zachowawczo. To ograniczone kontrole tekstowe, a nie analiza binarnych modeli lub pełna ochrona przed exploitami.

## Kontrole semantyczne

Polityka produktu używa **Laya z lokalnym Qwen3:4b**, 30-sekundowym limitem oceny, progiem `0.7` i włączoną kontrolą wyjścia. Najpierw wykonywane są kontrole lokalne. Treść docierająca do oceny semantycznej jest analizowana przed przekazaniem, a odpowiedź — przed dostarczeniem. Błędna odpowiedź, brak modelu, przekroczenie czasu lub awaria dostawcy blokuje żądanie. Model odpowiedzi i model oceniający konfiguruje się niezależnie.

W **Policies → Edit configuration → Semantic analysis** wybierz dostawcę i opcjonalnie wpisz politykę języka naturalnego w `semantic.instructions`. Pole przyjmuje do 4096 znaków i wymaga `laya`; niepuste instrukcje z innym dostawcą są odrzucane. Przejrzyj i aktywuj zmianę przed testowaniem reprezentatywnych treści dozwolonych i zabronionych.

Dokładne wymagania, takie jak zakaz słów z literą a, realizuj deterministycznymi regułami treści. Modele semantyczne mogą przeoczyć ograniczenia znakowe. Instrukcje semantyczne nadają się do zakazów opartych na znaczeniu, ale ich wyniki nadal wymagają oceny na własnych danych.

Kategorie mają kody: `benign` → `0`, `suspicious` → `0.6`, `malicious` → `1`. Są to uporządkowane kategorie polityki, a nie prawdopodobieństwa. Próg `0.5` blokuje podejrzane i złośliwe treści, a `0.7` lub `0.8` — kategorię złośliwą. Ocena semantyczna uzupełnia uwierzytelnianie, dostęp, prywatność, sygnatury i budżety.

## Nazwane reguły Laya {#named-laya-rules}

Użyj **Policies → Add Laya rule** do ograniczeń znaczeniowych opisanych własnymi słowami. Każda reguła ma ID, instrukcję, kierunek i cel. Proces w panelu to **Test with Laya → Review policy change → Review changes → Activate policy**, z jawnym potwierdzeniem przed publikacją.

Poniższy fragment `semantic` połącz z kompletną polityką, zachowując modele, narzędzia, budżety i pozostałe kontrole. Nie jest samodzielnym plikiem polityki:

```yaml
semantic:
  provider: laya
  model: qwen3:4b
  threshold: 0.7
  timeout_ms: 30000
  scan_output: true
  rules:
    - id: no-personal-investment-advice
      instruction: >-
        Block personalized recommendations to buy or sell a specific investment.
        Allow general explanations of financial concepts.
      direction: input
      target: model
```

`direction` to `input`, `output` lub `both`, a `target` to `model`, `tool` lub `all`. Do kontekstu oceny trafiają tylko reguły dotyczące bieżącego etapu. Wszystkie pasujące reguły i globalne `semantic.instructions` współdzielą jedną ocenę modelu na etap wraz z wbudowanymi kryteriami bezpieczeństwa. Wynik to jedna kategoria zagrożenia; FastFence nie wymyśla na jej podstawie ID dopasowanych reguł.

Limit wynosi osiem reguł z unikalnymi ID, 2048 znaków na niepustą instrukcję i 8192 bajty UTF-8 dla łącznego wyrenderowanego tekstu polityki. Nazwane reguły wymagają `laya`. Reguła obejmująca wyjście wymaga także `scan_output: true`; niezgodna konfiguracja jest odrzucana.

Edytor testuje propozycję na jednej próbce za pomocą rzeczywistej Laya, bez zapisywania polityki i wykonywania chronionego wywołania modelu lub narzędzia. Pokazany zakres to wejście, jeśli reguła obejmuje oba kierunki, oraz model, jeśli obejmuje wszystkie cele. Inne kombinacje sprawdzisz przez [administracyjne API podglądu](integration-reference.md#test-a-named-laya-rule). Propozycja jest oceniana razem z aktualnymi pasującymi regułami: blokady nie można przypisać wyłącznie jej, a brak blokady nie sprawdza całej bramki.

Po teście przejrzyj różnice i jawnie aktywuj zmianę. Edycja reguły lub próbki unieważnia test; nieaktualna wersja i awaria dostawcy wymagają ponownego przeglądu. Lista reguł pozwala je edytować i usuwać. Zdalne źródła konfiguracji pozostają tylko do odczytu przez lokalne zarządzanie.

### Wybierz właściwy edytor

| Edytor | Co zapisuje | Działanie podczas żądania |
| --- | --- | --- |
| **Add Laya rule** | Nazwaną instrukcję języka naturalnego z kierunkiem i celem | Rzeczywista ocena semantyczna we właściwych etapach |
| **Add content rule** | Literalny warunek `contains`, `word_contains` lub `equals` | Deterministyczne dopasowanie lokalne bez modelu |
| **Describe a fast rule** | Sprawdzoną, ograniczoną propozycję konfiguracji wygenerowaną przez Laya | Powstałe kontrole; wygenerowane predykaty literalne są dopasowywane lokalnie |

Używaj **Add content rule** do konkretnych słów i liter, a **Add Laya rule** do ograniczeń znaczeniowych. Model może przeoczyć dokładny warunek znakowy. Tworzenie reguł przez Laya nie zamienia dowolnego opisu w gwarantowany szybki predykat.

## Zakres budżetów

Budżet jest lokalny dla instancji, zaufanej tożsamości i dnia UTC. Atomowe rezerwacje zapobiegają wydaniu tej samej pozostałej puli przez równoległe wywołania. Wywołanie jest naliczane przy rezerwacji; rozliczenie zwalnia niewykorzystaną część, a błędy i anulowana praca zachowują zachowawcze obciążenie.

Jednostki tokenów są zachowawczym oszacowaniem, a nie dokładnym wynikiem tokenizera lub fakturą dostawcy. Rezerwacje modeli uwzględniają 1024 jednostki na narzut szablonu promptu poza bajtami wejścia i ograniczoną odpowiedzią. Niewykorzystana rezerwacja jest zwalniana. `cost_microusd` to skonfigurowany koszt wywołania; jeden mikro-USD to 0,000001 USD. Modele lokalne mogą mieć koszt finansowy równy zero, nadal podlegając limitom czasu i tokenów.

Liczniki i ograniczony audyt zerują się po restarcie. Instancje mają niezależne limity bez globalnej koordynacji. Blokada wyjścia nie cofa skutków operacji docelowej.

## Tworzone reguły tekstowe

Dodawaj ograniczone reguły lokalne do `policy.text_rules`. Używają operatorów literalnych, nigdy generowanego kodu Python ani dowolnych wyrażeń regularnych:

```yaml
text_rules:
  - id: no-letter-a
    operator: word_contains
    value: a
    direction: both
    target: model
    action: block
    case_sensitive: false
```

Reguła blokuje wejście lub odpowiedź modelu zawierającą słowo z `a`, również wielkim `A` i zgodnymi formami Unicode. Stosuje NFKC i opcjonalnie casefold; znaki diakrytyczne pozostają różne, więc `ą` nie pasuje do `a`. Słowa składają się z liter Unicode i znaków łączących. `contains` sprawdza literalny podciąg jednej wartości tekstowej, a `equals` całą wartość. Wartość `word_contains` może zawierać tylko litery i znaki łączące.

Wybierz `input`, `output` lub `both` oraz `model`, `tool` lub `all`. Wejście modelu obejmuje prompt, treści wiadomości i ciągi stop; wyjście obejmuje wygenerowany tekst. Role, identyfikatory modeli i strukturalne klucze JSON są wyłączone. Reguły narzędzi sprawdzają rekurencyjnie wartości tekstowe, bez kluczy słowników. Sygnatury i prywatność zachowują szerszy zakres kontroli.

Dozwolone są maksymalnie 64 reguły z unikalnymi ID i niepustą wartością do 128 znaków. Przygotowanie literału odbywa się podczas walidacji. Dopasowanie nie potrzebuje kompilatora, modelu, plików ani sieci. Blokady wejścia poprzedzają wykonanie; blokady wyjścia wstrzymują dostarczenie po wykonaniu. Wyniki zawierają ID reguł, nie dopasowaną treść.

W **Policies** wybierz **Add content rule**, ustaw zakres i próbki, a potem sprawdź podgląd, przejrzyj i aktywuj regułę. Podgląd ocenia tylko proponowany predykat: `NO MATCH` nie obiecuje zezwolenia pozostałych kontroli. Aktywacja dodaje regułę do bieżącej polityki z nową wersją. Duplikaty ID, błędne reguły i konflikty wersji są odrzucane. Zdalną konfigurację aktualizuje się u jej źródła.

Klient administracyjny może pobrać `GET /api/admin/rules/schema`, a następnie wywołać `POST /api/admin/rules/preview` z obiektem `rule` i maksymalnie 16 `samples`, po 4096 znaków. Podgląd nie zmienia polityki i nie wywołuje modelu. Poprawną propozycję publikuj przez wersjonowany `PUT /api/admin/policy`.

## Opisz politykę w panelu

Wykonaj zwykłe `fastfence init` lub odpowiednik przez uv, pozostaw Ollama uruchomioną z dostępnym modelem oceniającym i połącz panel tożsamością administracyjną. W **Policies** wybierz **Describe a fast rule**:

1. Napisz konkretną instrukcję po polsku lub angielsku i wybierz **Draft with Laya**.
2. Sprawdź stan przed i po zmianie oraz dokładne operacje. Utworzenie propozycji niczego nie aktywuje.
3. Podaj przykłady, wybierz kierunek i cel, a następnie **Test examples**.
4. Potwierdź przegląd zmian i wyników, po czym wybierz **Activate this proposal**.
5. W **Test requests** sprawdź politykę na rzeczywistym chronionym wywołaniu. Narzędzia biznesowe wymagają osobno zarejestrowanych implementacji; domyślny produkt nie ma symulowanych narzędzi. Wynik zawiera ID audytu i informację o wykonaniu operacji docelowej.

Obsługiwane instrukcje obejmują zakaz słów z `a`, redakcję emaili, blokowanie danych osobowych i sekretów oraz zawężenie istniejącego narzędzia do podzbioru już dozwolonych ról. Selektywne detektory obejmują obecnie email i heurystykę jedenastocyfrowego polskiego identyfikatora. Ogólne deklaracje zgodności prawnej, nowe narzędzia, rozszerzanie ról i dowolne wykonywalne reguły są odrzucane zamiast wymyślane.

Selektywna redakcja emaili zmienia na przykład `privacy.detector_actions.pii_email`, pozostawiając działania innych detektorów. Żądanie z emailem i sekretem nadal jest blokowane, jeśli detektor sekretu ma akcję blokowania. Ogólne instrukcje prywatności zmieniają wszystkie kontrole w wybranym kierunku i usuwają jego selektywne wyjątki. Włączenie wcześniej wyłączonych kontroli jest pokazane w propozycji zmian.

Propozycja jest związana z tożsamością administratora i wersją bazowej polityki, wygasa po dziesięciu minutach i może zostać aktywowana raz. Serwer wymaga podglądu przed aktywacją. Zmiana przykładów unieważnia potwierdzenie przeglądu w przeglądarce, a zmiana instrukcji usuwa szkic. Aktywacja publikuje dokładnie zapisaną propozycję bez kolejnego wywołania modelu. Podgląd sprawdza tylko lokalne kontrole treści; role, budżety, semantyka i zachowanie usługi docelowej są sprawdzane przy rzeczywistym wywołaniu.

Endpointy zarządzania to `POST /api/admin/policies/draft`, `/preview` i `/activate`. Tworzenie propozycji używa ograniczonego, izolowanego lokalnego procesu Laya poza deterministycznym matcherem. Ocena semantyczna żądania jest osobnym etapem i może wywołać model dla każdej sprawdzanej interakcji. Wdrożenie z osobnym katalogiem konfiguracji może wskazać zaufanym `FASTFENCE_AUTHORING_ROOT` katalog instalacji Laya. Użytkownik przeglądarki nie może podawać ścieżek ani adresów modeli.

## Utwórz regułę językiem naturalnym w Laya

Funkcja **Describe a fast rule** korzysta z przypiętego rzeczywistego silnika Laya i lokalnego modelu Qwen do utworzenia ograniczonej propozycji. Wykonaj kroki panelu opisane wyżej albo użyj endpointów szkicu, podglądu i aktywacji. Po aktywacji konkretna reguła tekstowa działa lokalnie; osobno włączona analiza semantyczna nadal korzysta z modelu oceniającego.

Dla dokładnego przykładu wpisz: `Block each word containing the letter a, case insensitive, on model input only.`. Sprawdź `word_contains`, wartość `a`, cel model i kierunek wejściowy. Przetestuj `Hello` (brak lokalnego dopasowania) i `Cat` (blokada), przejrzyj różnice i aktywuj. Powtórz test przez [klienta MCP](examples/mcp-client.md).

Dla reguły znaczeniowej ocenianej przy każdej interakcji użyj kompletnego [skryptu nazwanej polityki Laya](examples/semantic-policy.md). Testuje rzeczywiste próbki i pokazuje wersjonowane różnice przed opcjonalną aktywacją. To osobna ścieżka względem tworzenia dokładnej reguły literalnej.

Ogólne wytyczne prawne nie są kompilowane do deterministycznej zgodności z prawem. Oceny i propozycje modelu mogą błędnie zrozumieć intencję; przygotuj niezależne oczekiwane przykłady i analizuj błędy.

Aby zmienić lub usunąć regułę, wybierz **Edit rule** lub **Remove…** w **Policies**, przejrzyj propozycję i jawnie ją aktywuj. Zaawansowana edycja JSON znajduje się w **Edit configuration**. Możesz też podnieść wersję w centralnym źródle konfiguracji. Zmiany dotyczą kolejnych wywołań.
