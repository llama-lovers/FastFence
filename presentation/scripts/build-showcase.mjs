/** Product showcase. Native text and actual recorded product evidence. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const skill = process.env.PRESENTATION_SKILL_DIR;
const modules = process.env.RUNTIME_NODE_MODULES;
const python = process.env.RUNTIME_PYTHON;
if (!skill || !modules || !python) throw new Error('Set PRESENTATION_SKILL_DIR, RUNTIME_NODE_MODULES and RUNTIME_PYTHON');
const rr = createRequire(path.join(modules, '__showcase__.cjs'));
const { Presentation, PresentationFile } = await import(pathToFileURL(rr.resolve('@oai/artifact-tool')));
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')));
const sharp = rr('sharp');
const build = path.join(root, 'state/private/presentation-build/showcase');
const assets = path.join(root, 'presentation/assets');
await fs.mkdir(build, { recursive: true });
const font = resolvePresentationFont({ fontFamily: 'Helvetica Neue' });
const C = { dark: '#092524', light: '#F6F7F2', ink: '#102C2A', teal: '#007F72', lime: '#CCF578', muted: '#B9CBC7', gray: '#52635E', red: '#C53642' };
const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
function tx(s, value, x, y, w, h, size, color, bold = false) {
  const b = s.shapes.add({ geometry: 'textbox', position: { left:x, top:y, width:w, height:h }, fill:'none', line:{fill:'none',width:0} });
  b.text = value;
  b.text.style = { typeface:font, fontSize:size, color, bold, autoFit:'none' };
  return b;
}
function page(dark, number, notes) {
  const s = deck.slides.add(); s.background.fill = dark ? C.dark : C.light;
  tx(s, 'FASTFENCE', 60, 30, 300, 26, 18, dark ? C.lime : C.teal, true);
  tx(s, String(number).padStart(2,'0'), 1170, 30, 50, 26, 18, dark ? C.muted : C.gray);
  s.speakerNotes.textFrame.setText(notes);
  return s;
}
async function crop(name, rect, dest) {
  const data = await sharp(path.join(assets,name)).extract(rect).png().toBuffer();
  await fs.writeFile(path.join(assets,dest),data); return data;
}
function pic(s, blob, x, y, w, h, alt) {
  s.images.add({ blob, contentType:'image/png', fit:'contain', position:{left:x,top:y,width:w,height:h}, alt });
}
const rule = await crop('demo-semantic-rule.png',{left:20,top:184,width:660,height:551},'showcase-rule.png');
const allow = await crop('demo-allowed.png',{left:935,top:278,width:600,height:277},'showcase-allow.png');
const block = await crop('demo-blocked.png',{left:935,top:278,width:600,height:295},'showcase-block.png');
const markdown = await crop('demo-ocr-markdown.png',{left:938,top:301,width:590,height:362},'showcase-markdown.png');
const source = await crop('demo-document-preview.png',{left:125,top:300,width:535,height:270},'showcase-document.png');

{
  const s = page(true,1,'0:00–0:25. Agent potrafi wysłać poufne dane albo wykonać kosztowne wywołanie. Nie chcemy przy każdej zmianie zasad przebudowywać agenta. FastFence to bramka między aplikacją a modelem lub narzędziem. Zasady opisujemy i zmieniamy centralnie, a kolejne wywołanie korzysta z aktywnej polityki. W tej prezentacji pokażemy konkretne zachowanie działającej paczki 1.0.7.\nŹródła: README.md; presentation/output/demo-evidence.json.');
  const logo = await sharp(path.join(root,'docs/assets/fastfence-logo.svg')).resize(160).png().toBuffer();
  pic(s,logo,1090,115,115,115,'Original FastFence logo');
  tx(s,'FastFence',60,119,1040,120,100,C.light,true);
  tx(s,'AI policies that change\nwithout changing agent code',63,273,1100,176,62,C.lime);
  tx(s,'One gateway between your agents and their models or tools.',63,510,1110,65,29,C.muted);
  tx(s,'llama-lovers',63,630,500,35,23,C.light);
}
{
  const s = page(false,2,'0:25–1:00. Najbardziej użyteczne jest to, że regułę opisujemy zwykłym językiem. Tutaj: blokuj spersonalizowane rekomendacje finansowe, dopuszczaj definicje. Dodajemy oczekiwane przykłady. Laya ocenia aktywną i proponowaną politykę, a my widzimy wyniki i dokładny diff przed aktywacją. Zapisane przykłady wracają jako regresje przy kolejnych zmianach. Ten rzeczywisty przegląd zaliczył osiem zakresowych przypadków. Nie twierdzimy, że dopiero nowa reguła zablokowała przykład finansowy: bazowa ochrona też go blokowała.\nŹródła: presentation/assets/demo-semantic-rule.png; presentation/output/demo-evidence.json; specs/changes/136-reviewed-semantic-rule-activation.yaml.');
  tx(s,'A policy written in words',60,95,1160,80,55,C.ink,true);
  tx(s,'“Block personalized\nfinancial recommendations.”',60,225,535,125,37,C.teal,true);
  tx(s,'You define allowed and blocked examples.\nLaya compares the proposed behavior.',60,393,510,95,27,C.ink);
  tx(s,'Review the diff.\nActivate the tested policy.',60,514,510,90,31,C.ink,true);
  pic(s,rule,640,190,580,484,'Actual natural-language rule and expected examples');
  tx(s,'Recorded review: 8 of 8 scoped cases passed',60,653,560,32,20,C.gray);
}
{
  const s = page(false,3,'1:00–1:30. To dowód zmiany bez restartu: dokładnie ten sam tekst Hello i ten sam działający gateway. Najpierw polityka v4 pozwoliła wykonać rzeczywisty model. Po zatwierdzeniu lokalnej reguły tekstowej polityka v5 zatrzymała kolejne Hello, zanim uruchomił się upstream. Panel pokazuje wersję i granicę wykonania. Reguła tej demonstracji jest lokalna, a nie semantyczna.\nŹródła: presentation/output/demo-evidence.json; presentation/assets/demo-allowed.png; presentation/assets/demo-blocked.png. Czas 1 ms na oryginalnym zrzucie to pojedyncze zarejestrowane żądanie, nie benchmark ani gwarancja wydajności.');
  tx(s,'Same request. New policy',60,95,1160,80,58,C.ink,true);
  tx(s,'“Hello”',60,207,450,70,49,C.ink,true);
  tx(s,'v4  ALLOW',60,307,540,60,40,C.teal,true);
  tx(s,'v5  BLOCK',672,307,548,60,40,C.red,true);
  pic(s,allow,60,390,550,254,'Actual v4 allowed verdict with upstream executed');
  pic(s,block,672,390,550,270,'Actual v5 blocked verdict with upstream not executed');
  tx(s,'One running gateway. Local text rule activated without restart.',425,220,790,58,28,C.gray);
}
{
  const s = page(true,4,'1:30–2:00. Ta sama polityka działa niezależnie od tego, czy aplikacja korzysta z REST, interfejsu zgodnego z OpenAI, MCP czy ACP. Kontrole lokalne wykonują się najpierw: uprawnienia, limity, detektory Python i wzorce. Zatrzymana tutaj treść nie wymaga inferencji. Dla pozostałych żądań Laya ocenia znaczenie zgodnie z konfiguracją polityki. Wyjście też przechodzi kontrole, zanim wróci do aplikacji. Blokada odpowiedzi nie cofa wcześniej wykonanego narzędzia.\nŹródła: src/fastfence/modules/control/application/services/inspection.py; src/fastfence/modules/control/application/services/execution.py; docs/integration-reference.md.');
  tx(s,'One policy on both sides\nof the model call',60,98,1150,145,57,C.light,true);
  tx(s,'01',60,315,110,75,52,C.lime,true);
  tx(s,'Local checks first',190,308,970,55,36,C.light,true);
  tx(s,'Python detectors, regex, permissions and budgets',190,373,990,50,29,C.muted);
  tx(s,'02',60,476,110,75,52,C.lime,true);
  tx(s,'Meaning where the policy requires it',190,468,1000,56,36,C.light,true);
  tx(s,'Laya assesses input and output',190,533,990,45,29,C.muted);
  tx(s,'REST     OpenAI-compatible     MCP     ACP',60,646,1150,35,24,C.lime);
}
{
  const s = page(false,5,'2:00–2:35. Ochrona nie kończy się na wpisanym prompcie. W prawdziwym nagraniu wysłaliśmy dwustronicowy PDF z dwoma syntetycznymi adresami e-mail. Lokalny OCR wyciągnął tekst, a polityka zastąpiła oba adresy znacznikami. Pobieramy dokładnie chroniony Markdown lub przekazujemy go do modelu. Model rzeczywiście odpowiedział, a Laya sprawdziła wejście i wyjście. Załącznik pozostaje po stronie lokalnego OCR. Ten pokaz używa nieodwracalnej redakcji. Oddzielnie produkt obsługuje samowystarczalne szyfrowane tokeny i dozwolone przywracanie bez bazy konwersacji.\nŹródła: presentation/output/ocr-demo-evidence.json; presentation/output/demo-document-approved.md; src/fastfence/workflows/document_markdown.py; docs/examples/asymmetric-anonymization.md. OCR może pomijać znaki. Nie zmieniamy pikseli oryginalnego PDF.');
  tx(s,'Useful documents. Protected content',60,95,1170,80,52,C.ink,true);
  tx(s,'Original PDF',60,206,520,44,28,C.gray,true);
  tx(s,'Markdown for the model',674,206,545,44,28,C.teal,true);
  pic(s,source,60,282,520,263,'Synthetic source document showing example.com contact');
  pic(s,markdown,674,270,545,335,'Actual approved Markdown with redacted email marker');
  tx(s,'2 pages. 2 email addresses redacted.',60,610,1145,51,36,C.ink,true);
  tx(s,'Local OCR supplies protected text to the model. No conversation database required.',60,665,1150,32,22,C.gray);
}
{
  const s = page(true,6,'2:35–3:00. Te zasady mają dać się zmieniać w działającym systemie. Poprawna polityka aktywuje się bez restartu, a błędna konfiguracja pozostawia ostatni prawidłowy stan. Powtórna inicjalizacja zachowuje istniejące klucze i dane dostępowe. To idempotencja konfiguracji, nie obietnica deduplikacji wywołań biznesowych. Produkt można uruchomić z publicznej paczki jednym poleceniem. Pierwszy start wymaga dostępnego Ollama i może pobrać modele oraz zależności.\nŹródła: README.md; tests/integration/test_policy_validation.py; tests/unit/test_one_command_startup.py; confirmed initialization and reload regressions.');
  tx(s,'Rules evolve.\nThe agent keeps running',60,105,1150,145,62,C.light,true);
  tx(s,'Valid changes activate live. Invalid changes keep the last valid policy.',60,308,1115,82,29,C.muted);
  tx(s,'Idempotent setup preserves configuration, credentials and keys.',60,411,1115,55,29,C.muted);
  tx(s,'uv tool run fastfence@1.0.7',60,520,1150,76,49,C.lime,true);
  tx(s,'fastfence.dev',60,632,1100,51,38,C.light,true);
}
{
  const s = page(false,7,'Opcjonalny załącznik poza trzema minutami. Wyniki dotyczą różnych zakresów i nie sumujemy ich. 1484 testy źródłowe, 406 testów paczki zainstalowanej poza repozytorium. Dwanaście rzeczywistych żądań obejmowało 24 oceny wejścia i wyjścia. Tysiąc kontrolowanych żądań sprawdzało kolejkę, nie wydajność tysiąca generacji modelu. Semantyka wciąż ma wyniki fałszywie dodatnie i ujemne, więc osiem przykładów nie dowodzi uniwersalnej trafności. Liczniki budżetu i audyt są lokalne dla procesu. Historycznych pomiarów 1.0.2 nie przedstawiamy jako opóźnień 1.0.7.\nŹródła: evaluation/results/request-queue-1.0.7.json; presentation/evidence.md; evaluation/results/reviewed-predicate-plan-diagnostic.json.');
  tx(s,'Release 1.0.7 verification',60,96,1160,80,55,C.ink,true);
  const rows = [
    ['1,484','source tests passed, 93.28% coverage'],
    ['406','installed-package security and transport checks'],
    ['12 / 12','real requests with 24 Laya assessments'],
    ['1,000','controlled requests: 8 active, 992 waiting'],
  ];
  rows.forEach(([n,label],i)=>{tx(s,n,60,212+i*86,265,65,44,C.teal,true);tx(s,label,365,223+i*86,850,58,27,C.ink);});
  tx(s,'FastFence 1.0.7. These counts measure control and integration tests.',60,573,1150,43,23,C.gray);
  tx(s,'Semantic judgments can be wrong. Reviewed examples cover those examples.\nBudget counters and retained audit belong to one process.',60,632,1150,65,22,C.gray);
}
const candidate = path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidate);
for (let i=0;i<deck.slides.items.length;i++) {
  const png = await deck.export({slide:deck.slides.items[i],format:'png',scale:1});
  await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
const finalPath = path.join(root,'presentation/output',process.env.DECK_OUTPUT_NAME || 'fastfence-pitch-v2.pptx');
await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,pythonExecutable:python,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
  explicitTotalSlideCount:7,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
  fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
  receiptPath:path.join(build,path.basename(finalPath)+'.validation.json')});
console.log(JSON.stringify({finalPath,font,slides:7}));
