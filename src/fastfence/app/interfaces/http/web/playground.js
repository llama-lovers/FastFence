function selectPlayground() {
  const model = $('playgroundMode').value === 'model';
  $('toolPlayground').classList.toggle('hidden', model);
  $('toolPresets').classList.toggle('hidden', model);
  $('modelPlayground').classList.toggle('hidden', !model);
  $('modelPresets').classList.toggle('hidden', !model);
  if (active) {
    $('allowedModels').replaceChildren(...Object.keys(active.models).map((name) => {
      const option = document.createElement('option');
      option.value = name;
      return option;
    }));
  }
}
$('playgroundMode').onchange = selectPlayground;
document.querySelectorAll('[data-model-prompt]').forEach((button) => {
  button.onclick = () => { $('completionPrompt').value = button.dataset.modelPrompt; };
});

function renderVerdict(verdict) {
  const color = verdict.decision === 'allowed' ? 'green' : verdict.decision === 'redacted' ? 'amber' : 'red';
  $('result').replaceChildren(
    el('strong', verdict.decision.toUpperCase() + ' · ' + verdict.reason, color),
    el('p', 'Policy v' + verdict.policy_version + ' · feed v' + verdict.feed_version +
      ' · ' + verdict.latency_ms + ' ms · upstream ' +
      (verdict.upstream_executed ? 'executed' : 'not executed'), 'small'),
    el('p', 'Audit request ID: ' + verdict.request_id, 'small'),
    el('pre', JSON.stringify({output: verdict.output, findings: verdict.findings,
      semantic_score: verdict.semantic_score, tokens: verdict.tokens}, null, 2))
  );
}

$('invokeBtn').onclick = async () => {
  if (!agent) { $('connectDialog').showModal(); return; }
  $('invokeBtn').disabled = true;
  const isModel = $('playgroundMode').value === 'model';
  $('result').replaceChildren(el('span', isModel ? 'Checking policy and calling the local model…' : 'Inspecting through active controls…', 'small'));
  try {
    const payload = isModel ? {
      model: $('completionModel').value,
      prompt: $('completionPrompt').value,
      max_output_tokens: Number($('completionTokens').value),
    } : {tool: $('tool').value, arguments: JSON.parse($('arguments').value)};
    const verdict = await api(isModel ? '/api/models/complete' : '/api/invoke', agent, payload);
    renderVerdict(verdict);
    await refresh();
  } catch (error) {
    $('result').replaceChildren(el('span', error.message, 'red'));
  } finally { $('invokeBtn').disabled = false; }
};
