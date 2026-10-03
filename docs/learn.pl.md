# Poznaj FastFence

Wykonaj te zadania kolejno na swojej lokalnej instalacji. Każde ma jeden widoczny wynik. [Instrukcja testów ręcznych](manual-testing.md) zawiera pełniejszą listę kontroli.

## Zacznij od działającego kodu

Zainstaluj [pakiet](getting-started.md), pobierz [komplet przykładów](downloads/fastfence-examples.zip) i rozpakuj do `examples/` w katalogu instalacji. Zacznij od [klienta REST](examples/protected-request.md), [nazwanej reguły Laya](examples/semantic-policy.md), [klienta MCP](examples/mcp-client.md) lub [serwera FastMCP](examples/fastmcp-server.md). Każda strona zawiera pełny kod.

## 1. Wyślij chronione żądanie do modelu {#1-send-a-protected-model-request}

Wykonaj [pierwsze kroki](getting-started.md). Zwykłe `init` instaluje Laya i przygotowuje skonfigurowany model oceniający; nowa instalacja używa go też do odpowiedzi. Otwórz panel, podłącz tożsamości agenta i administratora, a następnie wybierz **Test requests**. Wybierz model, wpisz krótki prompt i wyślij żądanie.

Wynik pokazuje wersję polityki, decyzję, przyczynę i informację, czy model docelowy został wywołany. Odnośnik do audytu otwiera to samo żądanie w **Activity**. Odrzucone wejście musi pokazywać brak wykonania operacji docelowej.

Odpowiednik w REST:

```sh
curl http://127.0.0.1:8000/api/models/complete \
  -H "Authorization: Bearer $FASTFENCE_AGENT_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3:4b","prompt":"Hi","max_output_tokens":256}'
```

Ustaw `FASTFENCE_AGENT_TOKEN` na token swojej tożsamości agenta. Nie zapisuj go w repozytorium i nie zastępuj tokenem administratora. Jeżeli aktywna polityka używa innego modelu, zmień identyfikator w przykładzie.

## 2. Napisz regułę Laya i sprawdź jej znaczenie

W **Policies** wybierz **Add Laya rule**. Nadaj ID `no-personal-investment-advice` i wpisz:

> Block personalized recommendations to buy or sell a specific investment. Allow general explanations of financial concepts.

Reguła zabrania spersonalizowanych rekomendacji kupna lub sprzedaży inwestycji, dopuszczając ogólne wyjaśnienia pojęć finansowych.

Wybierz **Input only** i **Models**. W **Sample content** wpisz `Tell me which stock I should buy with my retirement savings.` i wybierz **Test with Laya**. Test używa rzeczywistego skonfigurowanego modelu oceniającego; nie wywołuje chronionego modelu do odpowiedzi i nie aktywuje reguły.

Porównaj z dozwolonym przykładem `Explain what portfolio diversification means.`. Testuj realistyczne warianty i analizuj nieoczekiwane wyniki. Pokazana decyzja obejmuje całą ocenę semantyczną, w tym inne pasujące reguły; nie dowodzi dopasowania jednej nazwanej reguły.

Wybierz **Review policy change**, następnie **Review changes**. Sprawdź instrukcję, zakres wejście/model i ustawienia dostawcy w różnicach. Potwierdź przegląd i wybierz **Activate policy**. Nowa wersja i reguła pojawią się w **Policies**. W **Test requests** sprawdź pełną ścieżkę bramki z aktywną regułą.

Zmiana instrukcji, próbki lub zakresu unieważnia wcześniejszy test. Przekroczenie czasu lub niedostępność modelu niczego nie aktywuje. Przy **Input and output** okno testuje wejście, a przy **Models and tools** — treść dla modelu. Wynik podaje sprawdzony zakres. Inne kombinacje można testować przez API opisane w [konfiguracji reguł semantycznych](policies.md#named-laya-rules).

### Dokładne reguły tekstowe: przykład litery a

Ograniczenie znakowe utwórz przez **Add content rule**: wybierz `Word contains`, wartość `a`, kierunek wejściowy, cel model i wyłącz rozróżnianie wielkości liter. Przetestuj `Hi` oraz `Cat`, przejrzyj i aktywuj regułę. Lokalny matcher musi blokować `Cat` przed wykonaniem modelu; `Hi` może dotrzeć do modelu, jeśli pozwalają inne kontrole.

**Describe a fast rule** to osobny proces tworzenia reguł: Laya tłumaczy obsługiwaną instrukcję na ograniczoną propozycję konfiguracji. Przed aktywacją sprawdź różnice i wygenerowane przypadki regresyjne. Powstała reguła literalna różni się od oceny znaczenia przez **Add Laya rule**.

## 3. Zmień konfigurację

W **Policies** użyj edytora ustawień. Przejrzyj różnice względem aktywnej polityki i potwierdź przed publikacją. Po przyjęciu zmiany przez serwer panel pokaże nową aktywną wersję.

Jeśli źródłem polityki jest zdalny pakiet HTTP, zmień to źródło prawdy. Panel oznacza je jako tylko do odczytu. Błąd walidacji lub konflikt wersji zachowuje aktywną konfigurację: sprawdź błąd, odśwież stan i ponownie przejrzyj zmianę.

## 4. Chroń treść dokumentów

Wykonaj [instalację OCR](getting-started.md), podłącz tożsamość agenta i otwórz **Documents**. Prześlij PNG, JPEG lub wielostronicowy PDF. Sprawdź Markdown po kontroli polityk, zanim wyślesz go do dozwolonego modelu.

Anonimizacja korzysta z tych samych kontroli co inne wejścia i odpowiedzi. Odtwarzanie oryginałów jest domyślnie wyłączone; wymaga trybu odwracalnego oraz zezwolenia odpowiedniej reguły. OCR nie modyfikuje oryginalnego dokumentu.

## 5. Dodaj narzędzia biznesowe

Użyj [przykładu serwera FastMCP](examples/fastmcp-server.md), aby zarejestrować rzeczywiste narzędzie przez `ToolsPort` i chronić je za pomocą FastFence. Przykład działa oddzielnie, z własnymi danymi dostępu i polityką. Zastąp operację zmiany wielkości liter logiką swojej aplikacji.

Szczegóły adapterów opisuje [dokumentacja integracji](integration-reference.md), a przebieg kontroli i granice działania — [architektura](architecture.md).
