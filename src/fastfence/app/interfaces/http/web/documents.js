$('documentRun').onclick = async () => {
  if (!agent) { $('connectDialog').showModal(); return; }
  const file = $('documentFile').files[0];
  if (!file) { $('documentResult').textContent = 'Choose a PNG, JPEG or PDF.'; return; }
  if (file.size > 10 * 1024 * 1024) { $('documentResult').textContent = 'Maximum upload size is 10 MiB.'; return; }
  const identity = agent;
  const revision = playgroundRevision;
  $('documentRun').disabled = true;
  $('documentDownload').disabled = true;
  $('documentMarkdown').textContent = '';
  $('documentResult').textContent = 'Reading pages locally and checking the active policy…';
  const params = new URLSearchParams({mode: $('documentMode').value});
  if ($('completionModel').value) params.set('model', $('completionModel').value);
  if ($('documentMode').value === 'complete') {
    params.set('max_output_tokens', $('completionTokens').value);
    params.set('restore_originals', String($('restoreOriginals').checked));
  }
  try {
    const response = await fetch('/api/documents/markdown?' + params, {
      method: 'POST', headers: {Authorization: 'Bearer ' + identity, 'Content-Type': file.type}, body: file,
    });
    const result = await response.json();
    if (identity !== agent || revision !== playgroundRevision) return;
    if (!response.ok) throw Error(result.verdict?.reason || result.detail || 'Document could not be processed.');
    $('documentResult').textContent = result.pages + ' pages · ' + result.provider + ' · ' + result.ocr_elapsed_ms + ' ms OCR · ' + result.verdict.decision;
    $('documentMarkdown').textContent = result.markdown || '';
    $('documentDownload').disabled = !result.markdown;
    renderVerdict(result.verdict);
    await refresh();
  } catch (error) {
    if (identity === agent && revision === playgroundRevision) $('documentResult').textContent = error.message;
  } finally { $('documentRun').disabled = false; }
};

$('documentDownload').onclick = () => {
  const markdown = $('documentMarkdown').textContent;
  if (!markdown) return;
  const url = URL.createObjectURL(new Blob([markdown], {type: 'text/markdown;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'document.md';
  link.click();
  URL.revokeObjectURL(url);
};
