$('documentMode').onchange = () => $('documentModelFields').classList.toggle('hidden', $('documentMode').value !== 'complete');
$('documentRun').onclick = async () => {
  if (!agent) { openConnection(); return; }
  const file = $('documentFile').files[0];
  if (!file) { $('documentResult').textContent = 'Choose a PNG, JPEG or PDF.'; return; }
  if (file.size > 10 * 1024 * 1024) { $('documentResult').textContent = 'Maximum upload size is 10 MiB.'; return; }
  const complete = $('documentMode').value === 'complete';
  if (complete && !$('documentModel').value.trim()) { $('documentResult').textContent = 'Enter an allowlisted model ID.'; return; }
  const identity = agent, revision = playgroundRevision;
  $('documentRun').disabled = true; $('documentDownload').disabled = true;
  $('documentMarkdown').textContent = ''; $('documentVerdict').replaceChildren();
  $('documentResult').textContent = 'Reading pages locally and checking the active policy…';
  const params = new URLSearchParams({mode: $('documentMode').value});
  if (complete) {
    params.set('model', $('documentModel').value.trim());
    params.set('max_output_tokens', $('documentTokens').value);
    params.set('restore_originals', String($('documentRestore').checked));
  }
  try {
    const response = await fetch('/api/documents/markdown?' + params, {method: 'POST', headers: {Authorization: 'Bearer ' + identity, 'Content-Type': file.type}, body: file});
    const result = await response.json();
    if (identity !== agent || revision !== playgroundRevision) return;
    if (result.verdict) renderVerdict(result.verdict, 'documentVerdict');
    if (!response.ok) throw Error(result.verdict?.reason || result.detail || 'Document could not be processed.');
    $('documentResult').textContent = result.pages + ' pages · ' + result.ocr_elapsed_ms + ' ms OCR · ' + result.verdict.decision;
    $('documentMarkdown').textContent = result.markdown || '';
    $('documentDownload').disabled = !result.markdown;
    await refresh().catch(() => {});
  } catch (error) {
    if (identity === agent && revision === playgroundRevision) $('documentResult').textContent = error.message;
  } finally { $('documentRun').disabled = false; }
};
$('documentDownload').onclick = () => {
  const markdown = $('documentMarkdown').textContent;
  if (!markdown) return;
  const url = URL.createObjectURL(new Blob([markdown], {type: 'text/markdown;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = 'document.md'; link.click(); URL.revokeObjectURL(url);
};
