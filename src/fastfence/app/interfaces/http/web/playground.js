let playgroundRevision = 0;
function resetPlaygroundConversation() {
  playgroundRevision += 1;
  $('documentMarkdown').textContent = ''; $('documentDownload').disabled = true;
  $('documentResult').textContent = '';
  $('documentVerdict').replaceChildren(el('p', 'No document processed for this identity.', 'small'));
  $('documentRestore').checked = false; $('restoreOriginals').checked = false;
  $('result').replaceChildren(el('p', 'No request sent for this identity.', 'small'));
}
function syncPlaygroundModels(preserveEditing = true) {
  if (!active) return;
  const names = Object.keys(active?.models || {});
  $('allowedModels').replaceChildren(...names.map(name => { const option = document.createElement('option'); option.value = name; return option; }));
  for (const id of ['completionModel', 'documentModel']) {
    const input = $(id);
    if (!names.includes(input.value) && (!preserveEditing || document.activeElement !== input)) input.value = names[0] || '';
  }
  const connected = latestStatus?.tools?.connected || [];
  const current = $('tool').value;
  $('tool').replaceChildren(...connected.map(name => { const option = el('option', name); option.value = name; return option; }));
  if (connected.includes(current)) $('tool').value = current;
  $('tool').disabled = !connected.length;
  $('toolAvailability').textContent = connected.length ? 'Only tools with a connected adapter and active policy entry are listed.' : 'No tool adapter is connected. Connect a tool backend in your application before testing tool calls. Model requests are available separately.';
}
function selectPlayground() {
  const model = $('playgroundMode').value === 'model';
  $('toolPlayground').classList.toggle('hidden', model);
  $('modelPlayground').classList.toggle('hidden', !model);
  syncPlaygroundModels(false);
}
$('playgroundMode').onchange = selectPlayground;
$('completionModel').onblur = () => syncPlaygroundModels(false);
function renderVerdict(verdict, destination = 'result') {
  const container = $(destination);
  const color = verdict.decision === 'allowed' ? 'green' : verdict.decision === 'redacted' ? 'amber' : 'red';
  const reasons = {controls_passed: 'Passed the active controls', input_text_rule: 'Blocked by an input content rule', output_text_rule: 'Output withheld by a content rule', input_signature: 'Blocked by a known threat signature', privacy_redacted: 'Sensitive content was transformed', semantic_input_risk: 'Blocked by semantic input analysis', semantic_output_risk: 'Output withheld by semantic analysis', model_unavailable_fail_closed: 'Model unavailable; request failed closed', model_capacity_exceeded: 'Model queue full; request could not complete', request_queue_full: 'Request queue full; request was not admitted', request_queue_timeout: 'Request queue wait expired; request was not admitted', request_queue_closed: 'Request queue closed; request was not admitted', tool_capacity_exceeded: 'Tool connection pool full; tool was not executed', tool_not_supported: 'No handler is connected for this tool'};
  container.replaceChildren(el('strong', verdict.decision.toUpperCase(), color),
    el('p', reasons[verdict.reason] || verdict.reason),
    el('p', 'Policy v' + verdict.policy_version + ' · feed v' + verdict.feed_version + ' · ' + verdict.latency_ms + ' ms total', 'small'),
    el('p', verdict.upstream_executed ? 'The upstream was executed.' : 'The upstream was not executed.', 'small'));
  if (Number.isSafeInteger(verdict.queue_wait_ms) && verdict.queue_wait_ms >= 0) container.append(el('p', 'Queue wait: ' + verdict.queue_wait_ms + ' ms · included in total latency', 'small'));
  const semantic = verdict.semantic_score == null ?
    verdict.semantic_provider === 'disabled' ? 'Semantic analysis was disabled. This decision is based on local controls, not an assessment of the text’s meaning.' : 'No semantic score was produced for this request. It may have stopped before analysis; inspect the decision reason.' :
    'Semantic analysis: ' + verdict.semantic_provider + ' · severity ' + verdict.semantic_score + ' (ordinal score, not a probability).';
  container.append(el('p', semantic, verdict.semantic_provider === 'disabled' ? 'notice warning' : 'small'));
  const stages = {not_run: 'not run', passed: 'passed', blocked: 'blocked', error: 'failed closed'};
  if (verdict.semantic_input_status) container.append(el('p', 'Text analysis · input: ' + stages[verdict.semantic_input_status] + ' · output: ' + stages[verdict.semantic_output_status], 'small'));
  container.append(el('p', 'Matched controls: ' + ((verdict.findings || []).join(', ') || 'None'), 'small'));
  if (verdict.anonymized || verdict.restored) container.append(el('p', 'Anonymized: ' + (verdict.anonymized ? 'yes' : 'no') + ' · originals restored: ' + (verdict.restored ? 'yes' : 'no'), 'small'));
  if (verdict.output !== null && verdict.output !== undefined) {
    container.append(el('h3', 'Response'));
    container.append(el('pre', typeof verdict.output === 'string' ? verdict.output : JSON.stringify(verdict.output, null, 2)));
  }
  const details = document.createElement('details'); details.append(el('summary', 'Request details'));
  details.append(el('p', 'Request ID: ' + verdict.request_id, 'small'), el('pre', JSON.stringify({reason: verdict.reason, semantic_provider: verdict.semantic_provider, semantic_score: verdict.semantic_score, tokens: verdict.tokens}, null, 2)));
  container.append(details);
  const inspect = el('button', 'Inspect in Activity →', 'btn'); inspect.onclick = () => focusAudit(verdict.request_id); container.append(inspect);
}
$('invokeBtn').onclick = async () => {
  if (!agent) { openConnection(); return; }
  const isModel = $('playgroundMode').value === 'model';
  if (!isModel && !$('tool').value) { $('result').replaceChildren(el('p', 'Connect a tool backend before sending tool requests.', 'red')); return; }
  if (isModel && (!$('completionModel').value.trim() || !$('completionPrompt').value.trim())) { $('result').replaceChildren(el('p', 'Enter a model ID and input text.', 'red')); return; }
  $('invokeBtn').disabled = true;
  const revision = playgroundRevision, identity = agent;
  const context = {restore_originals: $('restoreOriginals').checked};
  $('result').replaceChildren(el('p', 'Checking the active policy and processing your request…', 'small'));
  try {
    const payload = isModel ? {...context, model: $('completionModel').value.trim(), prompt: $('completionPrompt').value, max_output_tokens: Number($('completionTokens').value)} : {...context, tool: $('tool').value, arguments: JSON.parse($('arguments').value)};
    const verdict = await api(isModel ? '/api/models/complete' : '/api/invoke', identity, payload);
    if (revision !== playgroundRevision || identity !== agent) return;
    renderVerdict(verdict);
    await refresh().catch(() => {});
  } catch (error) {
    if (revision === playgroundRevision && identity === agent) $('result').replaceChildren(el('p', error.message, 'red'));
  } finally { $('invokeBtn').disabled = false; }
};
