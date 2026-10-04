/** Build the jury deck with the supplied @oai/artifact-tool runtime. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const skill = process.env.PRESENTATION_SKILL_DIR;
const modules = process.env.RUNTIME_NODE_MODULES;
const python = process.env.RUNTIME_PYTHON;
if (!skill || !modules || !python) {
  throw new Error('Set PRESENTATION_SKILL_DIR, RUNTIME_NODE_MODULES and RUNTIME_PYTHON');
}
const requireRuntime = createRequire(path.join(modules, '__deck__.cjs'));
const { Presentation, PresentationFile } = await import(pathToFileURL(requireRuntime.resolve('@oai/artifact-tool')));
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')));
const sharp = requireRuntime('sharp');
const build = path.join(root, 'state/private/presentation-build');
const output = path.join(root, 'presentation/output');
await fs.mkdir(build, { recursive: true });
await fs.mkdir(output, { recursive: true });
const font = resolvePresentationFont();
const colors = { bg: '#0C1218', text: '#F3F6F8', muted: '#A6B7C3', lime: '#C5F277', teal: '#04A495', line: '#536572' };
const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });

function text(slide, content, x, y, w, h, size = 28, color = colors.text, bold = false) {
  const box = slide.shapes.add({ geometry: 'textbox', position: { left: x, top: y, width: w, height: h }, fill: 'none', line: { fill: 'none', width: 0 } });
  box.text = content;
  box.text.style = { typeface: font, fontSize: size, color, bold, autoFit: 'none' };
  return box;
}
function slide(title, number, notes) {
  const s = deck.slides.add();
  s.background.fill = colors.bg;
  if (title) text(s, title, 64, 42, 1152, 76, 48, colors.text, true);
  text(s, `FastFence 1.0.7    /    ${number}`, 64, 675, 1100, 26, 17, colors.muted);
  s.speakerNotes.textFrame.setText(notes);
  return s;
}
async function screenshot(s, name, frame) {
  const file = path.join(root, 'presentation/assets', name);
  const bytes = await fs.readFile(file);
  s.images.add({ blob: bytes, contentType: 'image/png', alt: `Actual FastFence 1.0.7 ${name}`, fit: name === 'policy-rule.png' ? 'cover' : 'contain', ...(name === 'policy-rule.png' ? { crop: { left: 0, right: 0, top: 0, bottom: 0.47 } } : {}), position: frame });
}
function node(s, label, x, y, w, h, accent = false) {
  const n = s.shapes.add({ geometry: 'rect', position: { left: x, top: y, width: w, height: h }, fill: accent ? '#17332F' : '#15202A', line: { fill: accent ? colors.teal : colors.line, width: 1.5 } });
  n.text = label;
  n.text.style = { typeface: font, fontSize: 26, color: colors.text, bold: accent, alignment: 'center', verticalAlignment: 'middle', autoFit: 'none' };
  return n;
}
function connect(s, a, b, fromSide = 'right', toSide = 'left') {
  s.shapes.connect(a, b, { kind: 'straight', fromSide, toSide, line: { fill: colors.lime, width: 2 }, head: { type: fromSide === 'bottom' ? 'none' : 'triangle' }, tail: { type: 'triangle' } });
}
function table(s, values, y, widths, rowHeight = 78) {
  const t = s.tables.add({ rows: values.length, columns: widths.length, left: 64, top: y, width: 1152, height: values.length * rowHeight, columnWidths: widths, values });
  t.borders.assign({ fill: colors.line, width: 0.7 });
  for (let r = 0; r < values.length; r++) {
    for (let c = 0; c < widths.length; c++) {
      const cell = t.getCell(r, c);
      cell.fill = r === 0 ? '#17332F' : colors.bg;
      cell.text.style = { typeface: font, fontSize: r === 0 ? 23 : 24, bold: r === 0 || c === 0, color: c === 0 && r > 0 ? colors.lime : colors.text };
    }
  }
  return t;
}

// 1. Cover and the problem, 20 seconds.
{
  const s = slide('', '01', '0:00–0:20. FastFence kontroluje to, co agent wysyła do modeli i narzędzi, oraz to, co zwraca użytkownikowi. Samo uwierzytelnienie nie chroni przed wyciekiem danych ani niekontrolowanym użyciem narzędzi. Zbudowaliśmy centralne polityki, które można zmieniać podczas pracy systemu.\nSource: challenge criteria, sections 1–4; README.md. Team name: repository organization llama-lovers.');
  text(s, 'FastFence', 64, 138, 780, 106, 88, colors.text, true);
  text(s, 'Security policies for\nevery AI interaction', 68, 260, 740, 150, 46, colors.lime);
  text(s, 'Sensitive data. Tool permissions. Resource budgets.', 68, 438, 775, 84, 27, colors.muted);
  text(s, 'llama-lovers\nHackYeah 2026 / Goldman Sachs AI Control Layer', 68, 580, 850, 70, 23, colors.text);
  const logo = await sharp(path.join(root, 'docs/assets/fastfence-logo.svg')).resize(350).png().toBuffer();
  s.images.add({ blob: logo, contentType: 'image/png', fit: 'contain', alt: 'Original FastFence logo', position: { left: 870, top: 210, width: 310, height: 310 } });
}
// 2. Editable system diagram, 30 seconds.
{
  const s = slide('One control layer across AI interfaces', '02', '0:20–0:50. Ten sam silnik chroni REST, OpenAI-compatible, MCP i ACP. Najpierw wykonuje szybkie kontrole lokalne. Polityka określa, kiedy Laya ocenia znaczenie tekstu. Sprawdzamy wejście i wyjście. Konfigurację aktualizujemy bez restartu. Kolejka czeka na wolne zasoby, a przed wykonaniem ponownie sprawdzamy aktualną politykę.\nSources: src/fastfence/modules/control/application; specs/changes/146-bounded-fair-request-admission.yaml. Diagram is a logical view, not a promise of universal protocol compatibility.');
  const policy = node(s, 'policy.yaml + threat feed\nValidated hot reload', 390, 145, 500, 100, true);
  const client = node(s, 'Apps and agents', 64, 305, 245, 120);
  const core = node(s, 'FastFence\nInput and output controls', 390, 290, 500, 150, true);
  const target = node(s, 'Models and tools', 971, 305, 245, 120);
  connect(s, policy, core, 'bottom', 'top');
  connect(s, client, core);
  connect(s, core, target);
  text(s, 'REST   OpenAI-compatible   MCP   ACP', 64, 485, 1152, 50, 28, colors.lime);
  text(s, 'Local Python / regex checks first\nLaya semantic assessment when the policy requires it', 64, 550, 1152, 85, 27);
}
// 3. Real product screenshot, 30 seconds.
{
  const s = slide('A reviewed rule becomes a live policy', '03', '0:50–1:20. Regułę możemy opisać słowami albo zapisać jako precyzyjny wzorzec. Porównujemy wyniki przed zmianą i po niej. Operator przegląda zmianę i aktywuje politykę bez restartu. Dla reguł semantycznych zapisujemy przypadki do ponownego uruchomienia. Jeśli model nie spełnia oczekiwań na próbkach, przegląd nie daje zgody na aktywację.\nSources: specs/changes/138-private-semantic-suites-and-replay.yaml; evaluation/results/reviewed-semantic-workflow-1.0.6.json. Screenshot: actual installed 1.0.7 recording. Reviewed samples do not guarantee unseen-case accuracy.');
  text(s, 'Describe the rule', 64, 180, 310, 55, 31, colors.lime, true);
  text(s, 'Test both outcomes\nReview the change\nActivate without restart', 64, 267, 310, 190, 29);
  text(s, 'Natural-language rules use Laya. Exact patterns run locally.', 64, 512, 310, 105, 24, colors.muted);
  await screenshot(s, 'policy-rule.png', { left: 410, top: 145, width: 806, height: 490 });
}
// 4. Privacy feature, without implying fabricated token output.
{
  const s = slide('Privacy controls preserve useful context', '04', '1:20–1:45. Dane można nieodwracalnie maskować albo zastępować samowystarczalnymi zaszyfrowanymi tokenami. Przywrócenie oryginałów wymaga ustawienia i uprawnień. Obsługujemy też szyfrowanie z kluczem publicznym i prywatnym, bez bazy konwersacji. Obrazy i wielostronicowe PDF przetwarzamy lokalnie przez OCR, a model dostaje oczyszczony Markdown.\nSources: docs/examples/asymmetric-anonymization.md; src/fastfence/modules/anonymization; evaluation/results/asymmetric-crypto.json; evaluation/results/ocr-local.json. Reversible pseudonymization is not irreversible anonymization. The model must preserve complete tokens for restoration.');
  text(s, 'Irreversible masking', 64, 170, 520, 60, 36, colors.lime, true);
  text(s, 'Aliases replace sensitive values.\nNo recovery of the originals.', 64, 250, 520, 120, 29);
  text(s, 'Reversible pseudonymization', 655, 170, 560, 60, 36, colors.lime, true);
  text(s, 'Encrypted, self-contained tokens.\nAuthorized restoration with keys.\nNo conversation database.', 655, 250, 560, 150, 29);
  text(s, 'Images and multipage PDFs', 64, 470, 1152, 55, 34, colors.text, true);
  text(s, 'Local OCR produces Markdown. Text controls sanitize it before the model call.', 64, 550, 1120, 80, 28, colors.muted);
}
// 5. Native evidence table. Counts are distinct checks, not summed.
{
  const s = slide('Evidence from FastFence 1.0.7', '05', '1:45–2:15. Mamy 1484 testy źródłowe oraz 406 testów bezpieczeństwa i transportu na paczce zainstalowanej poza repozytorium. Kolejkę sprawdziliśmy na tysiącu żądań z kontrolowanym backendem. Osobno dwanaście równoległych żądań przeszło przez prawdziwe Laya i Ollamę, łącznie z dwudziestoma czterema ocenami wejścia i wyjścia. To różne zakresy testów, nie tysiąc jednoczesnych generacji modelu.\nSources: specs/changes/150-queued-runtime-release.yaml; evaluation/results/request-queue-1.0.7.json; state/private/queue-package-1.0.7-pypi.json (outcomes only, no private data embedded). Counts overlap and must not be summed.');
  table(s, [
    ['Result', 'What we verified'],
    ['1,484 tests passed', 'Source suite, 93.28% code coverage'],
    ['406 tests passed', 'Installed package: security, admission, transport'],
    ['12 / 12 real requests', 'Laya + Ollama, 24 input/output assessments'],
    ['1,000 / 1,000 requests', 'Controlled provider, 8 active and 992 waiting'],
  ], 150, [420, 732], 86);
  text(s, 'The queue absorbs bursts. Model capacity still limits throughput.', 64, 605, 1152, 45, 25, colors.muted);
}
// 6. Actual dashboard and operating limits.
{
  const s = slide('Every decision has an operational record', '06', '2:15–2:40. Dashboard pokazuje decyzje, powody blokad, budżety, opóźnienia i kolejkę. W szczegółach widać, czy wykonaliśmy upstream oraz jaka wersja polityki zadziałała. Eksport audytu nie zawiera surowych promptów ani kluczy. Budżety i audyt są lokalne dla procesu. Restart je zeruje, więc nie deklarujemy globalnego limitu dla wielu instancji.\nSources: src/fastfence/modules/control/persistence/ledger.py; docs/integration-reference.md. Screenshot: actual installed 1.0.7 recording. Dashboard refreshes periodically, not instant push telemetry.');
  await screenshot(s, 'dashboard.png', { left: 64, top: 135, width: 860, height: 485 });
  text(s, 'Decision + reason\nPolicy version\nBudget usage\nQueue wait\nJSONL export', 958, 172, 260, 300, 28, colors.lime);
  text(s, 'Process-local state.\nRestart resets budgets and retained audit.', 958, 510, 260, 115, 22, colors.muted);
}
// 7. Closing and installation, 20 seconds.
{
  const s = slide('Try FastFence from PyPI', '07', '2:40–3:00. Produkt uruchamiamy z PyPI jednym poleceniem. W nagraniu pokażemy rzeczywisty request do modelu, zmianę reguły bez restartu oraz blokadę tego samego requestu z zapisem audytu. Najważniejszą granicą pozostaje trafność modelu dla nowych reguł semantycznych. Dlatego łączymy go z kontrolami lokalnymi i obowiązkowym przeglądem próbek w tym workflow.\nSources: README.md; PyPI package1.0.7; docs/manual-testing.md. Automatic setup may download models and dependencies on first run. Required Python and uv prerequisites are documented.');
  text(s, 'uv tool run fastfence@1.0.7', 64, 190, 1152, 100, 55, colors.lime, true);
  text(s, 'fastfence.dev', 64, 360, 1000, 65, 46, colors.text, true);
  text(s, 'github.com/llama-lovers/FastFence', 64, 448, 1100, 55, 32, colors.muted);
  text(s, 'Recorded demo: a policy change takes effect on the next request', 64, 565, 1130, 72, 30);
}
// 8. Optional benchmark appendix, outside the three-minute pitch.
{
  const s = slide('Appendix: latency measurements and scope', '08', 'Opcjonalny slajd do pytań. Nie przedstawiaj tych pomiarów jako wyników 1.0.7 ani pełnego czasu odpowiedzi aplikacji.\nSource: docs/benchmarks.md; evaluation/results/installed-package-1.0.2-comparison.json; evaluation/results/installed-package-1.0.2-semantic.json. Apple M3 Pro, one process. Deterministic2000samples+100warmup. Semantic20samples+2warmup, fixed short prompt, warm Laya/qwen3:4b, two assessments. No ingress HTTP or business-model generation. These are descriptive observations, not SLOs.');
  text(s, 'Public package 1.0.2, Apple M3 Pro, concurrency 1', 64, 135, 1152, 55, 27, colors.muted);
  table(s, [
    ['Measured path', 'p50', 'p95', 'Samples'],
    ['Deterministic controls', '0.206 ms', '0.248 ms', '2,000'],
    ['Laya input + output', '1,117 ms', '1,200 ms', '20'],
  ], 225, [555, 200, 200, 197], 90);
  text(s, 'Both exclude ingress HTTP and business-model generation.\nThe semantic sample is small and uses a warm model.\nA full 1.0.7 latency benchmark remains open.', 64, 535, 1152, 112, 25, colors.muted);
}

const candidate = path.join(build, 'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidate);
for (let i = 0; i < deck.slides.items.length; i++) {
  const image = await deck.export({ slide: deck.slides.items[i], format: 'png', scale: 1 });
  await fs.writeFile(path.join(build, `slide-${i + 1}.png`), new Uint8Array(await image.arrayBuffer()));
}
const finalPath = path.join(output, process.env.DECK_OUTPUT_NAME || 'fastfence-pitch.pptx');
await finalizePresentation({
  workspaceDir: root, candidatePath: candidate, finalPath,
  pythonExecutable: python,
  integrityValidatorPath: path.join(skill, 'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(skill, 'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-heading-fit', '--require-native-table-slide', '5', '--require-native-table-slide', '8'],
  explicitTotalSlideCount: 8,
  requiredNativeTableOwnerSlides: [5, 8],
  requiredNativeChartOwnerSlides: [],
  fontPolicy: { basis: 'design', families: [font] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(build, path.basename(finalPath) + '.validation.json'),
});
console.log(JSON.stringify({ finalPath, font, slides: 8 }));
