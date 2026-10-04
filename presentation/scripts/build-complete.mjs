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
const build = path.join(root, 'state/private/presentation-build/complete');
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
  const categories = {1:'SOLUTION 30%',2:'ARCHITECTURE 20%',3:'REPORTING 20%',4:'SOLUTION 30%',5:'IMPLEMENTATION 15%',6:'IMPLEMENTATION 15%',7:'SOLUTION 30%',8:'SOLUTION 30%',9:'TESTING 15%',10:'ARCHITECTURE 20%'};
  tx(s, categories[number], 680, 30, 450, 26, 18, dark ? C.muted : C.gray);
  s.speakerNotes.textFrame.setText(notes + '\nOrganizer criteria: Solution 30% (slides1,4,7,8); Architecture 20% (slides2,10); Reporting 20% (slide3 and recorded Activity); Testing 15% (slide9 plus policy/protocol examples); Implementation 15% (slides5,6 and installation on slide10). These are organizer weights, not self-assigned scores.');
  return s;
}
async function crop(name, rect, dest) {
  const data = await sharp(path.join(assets,name)).extract(rect).png().toBuffer();
  await fs.writeFile(path.join(assets,dest),data); return data;
}
function pic(s, blob, x, y, w, h, alt) {
  s.images.add({ blob, contentType:'image/png', fit:'contain', position:{left:x,top:y,width:w,height:h}, alt });
}
const evidence = async name => JSON.parse(await fs.readFile(path.join(root,'presentation/output',name),'utf8'));
const mcp = await evidence('mcp-demo-evidence.json');
const acp = await evidence('acp-demo-evidence.json');
const live = await evidence('demo-evidence.json');
const integration = await evidence('integration-demo-evidence.json');
const anon = await evidence('anonymization-demo-evidence.json');
function title(s,value,dark=false) { tx(s,value,60,96,1160,112,49,dark?C.light:C.ink,true); }
function table(s,values,top,widths,dark=false,rowHeight=78) {
  const t=s.tables.add({rows:values.length,columns:widths.length,left:60,top,width:1160,height:values.length*rowHeight,columnWidths:widths,values});
  t.borders.assign({fill:dark?'#52706A':'#B4C9C0',width:0.7});
  for(let r=0;r<values.length;r++) for(let c=0;c<widths.length;c++) {
    const cell=t.getCell(r,c); cell.fill=r===0?(dark?'#153F38':'#DDEBE3'):(dark?C.dark:C.light);
    cell.text.style={typeface:font,fontSize:25,bold:r===0||c===0,color:dark?C.light:C.ink};
  }
}
function node(s,label,x,y,w,h){const n=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:'#153F38',line:{fill:C.teal,width:1}});n.text=label;n.text.style={typeface:font,fontSize:25,color:C.light,alignment:'center',verticalAlignment:'middle'};return n;}
function edge(s,a,b,fromSide='right',toSide='left'){s.shapes.connect(a,b,{kind:'straight',fromSide,toSide,line:{fill:C.lime,width:2},tail:{type:'triangle'}});}
{
 const s=page(true,1,'0:00–0:18. FastFence pozwala zmieniać zasady ochrony bez przebudowy agenta. Chronimy dane i operacje na granicy wywołania. Pokażemy działającą paczkę: integrację SDK, MCP, ACP, reguły Laya i dokumenty.\nSources: README.md; presentation/output/demo-evidence.json; protocol evidence JSON files.');
 const logo=await sharp(path.join(root,'docs/assets/fastfence-logo.svg')).resize(200).png().toBuffer();pic(s,logo,1030,115,180,180,'Original FastFence logo');
 tx(s,'FastFence',60,128,900,130,100,C.light,true);
 tx(s,'AI policies that change\nwithout changing agent code',63,294,1120,170,60,C.lime);
 tx(s,'Protected data and controlled operations at the point of execution.',63,514,1100,86,30,C.muted);
 tx(s,'llama-lovers   /   HackYeah 2026   /   Public release 1.0.7',63,646,1110,35,23,C.light);
}
{
 const s=page(true,2,'0:18–0:38. Jeden silnik obsługuje REST, SDK OpenAI, MCP i komunikację agentów ACP. Diagram jest edytowalny. Lokalnie sprawdzamy dostęp, detektory danych i sekretów, sygnatury zagrożeń oraz budżety. Laya ocenia znaczenie treści zgodnie z polityką. Kontrolujemy wejście oraz wyjście. Prawdziwa integracja SDK potwierdziła zmianę decyzji przez ten sam endpoint.\nSources: src/fastfence/app/factory.py; presentation/output/integration-demo-evidence.json; docs/integration-reference.md. ACP means Agent Communication Protocol, synchronous text-only compatibility.');
 title(s,'One policy pipeline across existing interfaces',true);
 const source=node(s,'Agents and apps\nREST / OpenAI SDK\nMCP / ACP',60,295,280,150);
 const core=node(s,'FastFence\nInput and output controls',440,295,410,150);
 const target=node(s,'Models and tools',950,295,270,150);
 const policy=node(s,'Validated policy + threat feed',440,195,410,65);
 edge(s,source,core);edge(s,core,target);edge(s,policy,core,'bottom','top');
 tx(s,'Local checks: identity, permissions, PII, secrets, signatures and budgets',60,491,1160,58,28,C.light);
 tx(s,'Laya adds semantic assessment when the policy requires it.',60,564,1160,45,28,C.muted);
 tx(s,'OpenAI SDK: configure base_url="http://localhost:8000/v1" and an agent token',60,645,1160,35,22,C.lime);
}
{
 const s=page(false,3,'0:38–0:56. W nagraniu ten sam tekst Hello przechodzi przy polityce v4. Po zmianie lokalnej reguły v5 zatrzymuje go przed modelem. Nie restartujemy bramki. Audyt łączy decyzję z powodem, wersją i faktem wykonania upstream. To pojedyncze obserwacje, nie benchmark.\nSources: presentation/output/demo-evidence.json; actual demo-allowed.png/demo-blocked.png screenshots.');
 title(s,'A rule change affects the next request');
 tx(s,'Same “Hello”. Same running gateway.',60,210,1160,58,36,C.ink,true);
 tx(s,'v4  ALLOW',60,305,550,62,41,C.teal,true);tx(s,'v5  BLOCK',675,305,545,62,41,C.red,true);
 pic(s,await fs.readFile(path.join(assets,'showcase-allow.png')),60,379,550,254,'Recorded ALLOW result');
 pic(s,await fs.readFile(path.join(assets,'showcase-block.png')),675,379,545,268,'Recorded BLOCK before upstream');
 tx(s,'Policy version and execution boundary remain visible in the audit.',60,662,1160,32,22,C.gray);
}
{
 const s=page(false,4,'0:56–1:17. Regułę semantyczną opisujemy zwykłym językiem i dodajemy oczekiwane przykłady. Laya porównuje aktywną oraz proponowaną politykę. Operator widzi wyniki i diff przed aktywacją. Zapisane przypadki stają się regresjami. Osiem przypadków przeszło prawdziwy przegląd. Nie twierdzimy, że przykład finansowy zaczął być blokowany dopiero po zmianie: bazowa ochrona już go blokowała. Natural-language assessment is not arbitrary Python or regex generation.\nSources: presentation/output/demo-evidence.json; semantic review source and specs136/138.');
 title(s,'Natural-language rules with reviewed examples');
 tx(s,'“Block personalized\nfinancial recommendations.”',60,240,535,133,37,C.teal,true);
 tx(s,'Define allowed and blocked examples.\nCompare active and proposed behavior.\nReview the diff before activation.',60,417,530,150,28,C.ink);
 pic(s,await fs.readFile(path.join(assets,'showcase-rule.png')),650,205,560,468,'Actual Laya rule and expected cases');
 tx(s,`${live.semantic_review.cases}/8 scoped cases passed and saved`,60,605,555,44,30,C.teal,true);
 tx(s,'Passing samples establish those cases, not universal semantic accuracy.',60,670,1160,28,20,C.gray);
}
{
 const s=page(true,5,'1:17–1:33. To rzeczywisty klient FastMCP po HTTP, nie zapytanie REST podpisane nazwą MCP. Wywołujemy prywatne narzędzie zamiany tekstu na wielkie litery przez FastFence. Po aktywacji reguły to samo wywołanie zostaje zablokowane. Licznik wykonania narzędzia pozostaje równy jeden. Ten pokaz nie wymaga modelu.\nSource: presentation/output/mcp-demo-evidence.json; presentation/scripts/record_mcp_demo.py; examples/docs/fastmcp_server.py. Client authenticated using BearerAuth; unauthenticated request returned401.');
 title(s,'MCP protection through a standard client',true);
 tx(s,'FastMCP client connects to /mcp/ with an agent credential',60,211,1160,54,30,C.muted);
 tx(s,'await client.call_tool("invoke", {\n    "tool": "text.uppercase",\n    "arguments": {"text": "hello"}\n})',60,296,1140,164,29,C.lime);
 table(s,[['Policy','Actual MCP result','Backend calls'],[`v${mcp.allowed.policy_version}`,'ALLOW  /  HELLO','1'],[`v${mcp.blocked.policy_version}`,'BLOCK  /  input_text_rule','Still 1'] ],485,[190,670,300],true,56);
 tx(s,'Real HTTP protocol and real local tool. No model inference in this test.',60,667,1160,30,21,C.muted);
}
{
 const s=page(false,6,'1:33–1:49. Agent Communication Protocol umożliwia przekazanie zadania innemu agentowi. Tutaj oficjalny klient i lokalny agent ACP działają po obu stronach FastFence. Po zmianie polityki ponowne hello kończy się niepowodzeniem przed wywołaniem agenta. Licznik agenta pozostaje jeden. Obsługujemy bezstanowy synchroniczny tekst. To nie Agent Client Protocol ani A2A.\nSource: presentation/output/acp-demo-evidence.json; presentation/scripts/record_acp_demo.py. Interoperability scope is deliberately bounded.');
 title(s,'ACP agent calls share the same controls');
 tx(s,'Official ACP SDK client and an actual local agent',60,211,1160,52,30,C.gray);
 tx(s,'await client.run_sync(\n    agent="uppercase",\n    input=[Message(role="user", parts=[MessagePart(content="hello")])]\n)',60,295,1150,172,25,C.teal);
 table(s,[['Policy','Actual ACP run','Peer calls'],[`v${acp.allowed.policy_version}`,'COMPLETED  /  HELLO','1'],[`v${acp.blocked.policy_version}`,'FAILED  /  input_text_rule','Still 1']],485,[190,670,300],false,56);
 tx(s,'Agent Communication Protocol. Stateless, synchronous text. No model inference.',60,667,1160,30,21,C.gray);
}
{
 const s=page(true,7,'1:49–2:09. Maskowanie może być nieodwracalne. Tryb odwracalny używa zaszyfrowanych tokenów zawierających wartość. Klucz publiczny służy do szyfrowania, prywatny do autoryzowanego przywrócenia. Przełącznik kontroluje, czy odpowiedź pozostanie chroniona, czy wróci do oryginału. Model musi zachować kompletny token. Nie potrzeba bazy konwersacji.\nSources: docs/examples/asymmetric-anonymization.md; cryptographic envelope tests; presentation/output/anonymization-demo-evidence.json. Actual public1.0.7 HTTP test with deterministic echo, no LLM. Gateway holds both keys. Upstream receives only the encrypted token; denied restore permission blocks before upstream. Reversible pseudonymization is not irreversible anonymization. Restoration rechecks recovered data and requires matching active policy/key permissions.');
 title(s,'Privacy with optional, authorized restoration',true);
 tx(s,'Irreversible masking',60,226,550,53,34,C.lime,true);
 tx(s,'Matched data becomes a safe alias.\nNo original value to restore.',60,302,550,100,29,C.light);
 tx(s,'Reversible pseudonymization',660,226,560,53,34,C.lime,true);
 tx(s,'Self-contained encrypted tokens.\nPublic-key encryption, private-key recovery.\nNo conversation database.',660,302,560,153,27,C.light);
 table(s,[['Return mode','Actual response','Upstream receives'],['Restore OFF','Encrypted FFR2 token','Encrypted token'],['Restore ON','Anna Kowalska','Encrypted token']],478,[330,415,415],true,56);
 tx(s,'Actual local echo test, no LLM. Gateway holds both keys. Restore needs permission.',60,661,1160,39,21,C.muted);
}
{
 const s=page(false,8,'2:09–2:27. Dwustronicowy dokument zawiera dwa syntetyczne adresy e-mail. Lokalny OCR wyciąga tekst, a polityka usuwa oba adresy przed użyciem przez model. Pobieramy dokładnie chroniony Markdown. Qwen naprawdę odpowiada i przechodzi obie kontrole Laya. Pokazujemy redakcję tekstu, nie edycję pikseli PDF.\nSources: presentation/output/ocr-demo-evidence.json; presentation/output/demo-document-approved.md; src/fastfence/workflows/document_markdown.py. No provider packet capture was performed; code path forwards prepared Markdown.');
 title(s,'Useful documents with protected contact data');
 tx(s,'Original two-page PDF',60,225,550,50,30,C.gray,true);tx(s,'Protected Markdown',675,225,550,50,30,C.teal,true);
 pic(s,await fs.readFile(path.join(assets,'showcase-document.png')),60,305,535,270,'Actual synthetic source PDF');
 pic(s,await fs.readFile(path.join(assets,'showcase-markdown.png')),675,287,545,335,'Approved Markdown with email redaction');
 tx(s,'2 pages. 2 email redactions. Real Qwen response.',60,627,1160,49,35,C.ink,true);
 tx(s,'Local OCR extracts text. Policies protect it before model use.',60,677,1160,28,20,C.gray);
}
{
 const s=page(false,9,'2:27–2:45. Tu wyraźnie oddzielamy zakresy dowodów. Historyczny pomiar paczki 1.0.2 obejmuje sam silnik bez HTTP i generowania modelu biznesowego. Próbki semantyczne są małe i rozgrzane. Aktualna wersja 1.0.7 ma 1484 testy źródłowe, 406 kontroli zainstalowanej paczki i osobny test 12 prawdziwych żądań. Liczb nie sumujemy i nie utożsamiamy testów z trafnością klasyfikatora.\nSources: evaluation/results/installed-package-1.0.2-comparison.json; installed-package-1.0.2-semantic.json; request-queue-1.0.7.json; presentation/evidence.md. Native table is editable.');
 title(s,'Measured latency with explicit scope');
 tx(s,'Historical package 1.0.2, Apple M3 Pro, concurrency 1',60,209,1160,42,28,C.gray);
 table(s,[['Measured path','p50','p95','p99','Samples'],['Controls OFF','0.000125 ms','0.000167 ms','0.000208 ms','2,000'],['Deterministic ON','0.206 ms','0.248 ms','0.644 ms','2,000'],['Laya input + output','1,117 ms','1,200 ms','1,222 ms','20']],285,[400,205,205,205,145],false,66);
 tx(s,'OFF calls the fixture directly. ON includes the gateway engine.\nAll paths exclude HTTP and business-model generation.\nLaya uses warm Qwen3:4b and a repeated prompt.',60,567,1160,84,22,C.gray);
 tx(s,'1.0.7 source: 1,484 tests, 93.28% coverage. Installed package: 406 checks.',60,658,1160,37,25,C.teal,true);
}
{
 const s=page(true,10,'2:45–3:10. Poprawne zasady wchodzą bez restartu, a błędne konfiguracje pozostawiają ostatni poprawny stan. Inicjalizacja jest idempotentna: zachowuje polityki, klucze i dane dostępowe. To nie deduplikacja operacji biznesowych. Kolejka ma limity liczby, bajtów, tożsamości i czasu. Sprawdziliśmy 1000 żądań z kontrolowanym backendem oraz 12 prawdziwych żądań modeli. Budżety i audyt są lokalne dla procesu, restart je zeruje. Kod i dokumentacja są publiczne, instalacja wymaga uv, zgodnego Pythona i działającej Ollamy.\nSources: tests/unit/test_runtime_bootstrap.py; tests/unit/test_config_providers.py; evaluation/results/request-queue-1.0.7.json; README.md. No business operation idempotency key or exactly-once guarantee.');
 title(s,'Local operation with controlled failure',true);
 tx(s,'Live valid updates. Last valid policy on configuration errors.',60,231,1160,64,31,C.light);
 tx(s,'Idempotent setup preserves configuration, credentials and keys.',60,322,1160,60,29,C.muted);
 tx(s,'Bounded queue: 1,000 controlled requests and 12 real model calls verified.',60,407,1160,62,28,C.muted);
 tx(s,'uv tool run fastfence@1.0.7',60,515,1160,82,51,C.lime,true);
 tx(s,'fastfence.dev   /   github.com/llama-lovers/FastFence',60,622,1160,46,29,C.light);
 tx(s,'Budgets and audit are process-local. First start needs Ollama and may download models.',60,677,1160,27,20,C.muted);
}
if(deck.slides.items.length!==10) throw new Error('Exactly ten slides required');
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(deck)).save(candidate);
for(let i=0;i<10;i++){const png=await deck.export({slide:deck.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));}
const finalPath=path.join(root,'presentation/output',process.env.DECK_OUTPUT_NAME||'fastfence-pitch-v3.pptx');
await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--require-native-table-slide','5','--require-native-table-slide','6','--require-native-table-slide','7','--require-native-table-slide','9'],explicitTotalSlideCount:10,requiredNativeTableOwnerSlides:[5,6,7,9],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(build,path.basename(finalPath)+'.'+Date.now()+'.validation.json')});
console.log(JSON.stringify({finalPath,font,slides:10}));
