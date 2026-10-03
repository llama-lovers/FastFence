let studioProposal = null;
let studioPreviewed = false;
let studioRevision = 0;
let studioBusy = false;

const studioErrors = {
  unsupported_or_ambiguous_instruction: 'This instruction is outside the supported rule catalog or is ambiguous. Describe a specific text, privacy or tool-access rule.',
  invalid_or_unsafe_model_proposal: 'The proposed change failed validation. Nothing was activated. Make the instruction more specific and draft again.',
  policy_base_version_conflict: 'The active policy changed. Draft again against the latest version.',
  policy_activation_conflict: 'The policy changed before activation. Draft and review it again.',
  proposal_expired_redraft: 'This proposal expired. Draft it again before activation.',
  proposal_feed_changed_preview_again: 'The threat feed changed after preview. Test the examples again before activation.',
  proposal_preview_required: 'Test examples before activating this proposal.',
  proposal_already_activated: 'This proposal was already activated. Inspect the current policy.',
  proposal_not_found: 'This proposal is no longer available for this management identity. Draft again.',
  laya_not_installed_run_setup: 'Laya is not installed for this gateway. Run integrations/laya/setup.sh in the configured project directory.',
  authoring_requires_local_model: 'Policy authoring requires a configured local Ollama server.',
  laya_authoring_timeout: 'The authoring model did not respond in time. The active policy is unchanged; try again.',
  laya_authoring_failed: 'Laya could not draft the policy. Check that Ollama is running with qwen3:4b installed.',
  authoring_busy_try_again: 'Another proposal is being drafted. Try again when it finishes.',
  policy_source_is_read_only: 'Publish changes at the configured remote policy source.',
  proposal_capacity_wait_for_expiry: 'The proposal queue is full. Wait for older proposals to expire.',
};
function studioMessage(text, failed = false) {
  text = studioErrors[text] || text;
  $('policyStudioMessage').textContent = text;
  $('policyStudioMessage').className = 'message ' + (failed ? 'red' : 'green');
}
function updateStudioActivation() {
  $('activatePolicyDraft').disabled = studioBusy || !studioProposal || !studioPreviewed || !$('policyReviewed').checked;
}
function invalidateStudioPreview() {
  studioRevision += 1;
  studioPreviewed = false;
  $('policyReviewed').checked = false;
  $('policySampleResults').replaceChildren();
  updateStudioActivation();
}
function invalidateStudioProposal() {
  invalidateStudioPreview();
  studioProposal = null;
  $('policyDraftSection').classList.add('hidden');
}
function studioLock(locked) {
  studioBusy = locked;
  $('policyStudioDialog').querySelectorAll('input, textarea, select, button').forEach((field) => {
    field.disabled = locked;
  });
  updateStudioActivation();
}
function showStudio() {
  if (!admin) { $('connectDialog').showModal(); return; }
  if (!studioBusy) { invalidateStudioProposal(); studioMessage(''); }
  $('policyStudioDialog').showModal();
}
$('policyStudioBtn').onclick = showStudio;
$('policyStudioHero').onclick = showStudio;
$('closePolicyStudio').onclick = () => $('policyStudioDialog').close();
$('policyStudioDialog').addEventListener('cancel', (event) => {
  if (studioBusy) event.preventDefault();
});
$('policyInstruction').addEventListener('input', invalidateStudioProposal);
['policySamples', 'policySampleDirection', 'policySampleTarget'].forEach((name) => {
  $(name).addEventListener('input', invalidateStudioPreview);
});
$('policyReviewed').onchange = updateStudioActivation;
const policyExamples = {
  letters: ['Blokuj każde słowo zawierające literę a w wejściu i wyjściu modeli, bez rozróżniania wielkości liter.', 'Hello\nCat', 'input', 'model'],
  emails: ['Redaguj adresy e-mail w danych wejściowych i wyjściowych.', 'Contact us\nanna@example.org', 'input', 'model'],
  secrets: ['Blokuj dane osobowe i sekrety w danych wejściowych i wyjściowych.', 'Public report\nanna@example.org', 'output', 'tool'],
  roles: ['Ogranicz narzędzie knowledge.search wyłącznie do istniejącej roli operator.', 'Quarterly report', 'input', 'tool'],
};
document.querySelectorAll('[data-policy-example]').forEach((button) => {
  button.onclick = () => {
    invalidateStudioProposal();
    const [instruction, samples, direction, target] = policyExamples[button.dataset.policyExample];
    $('policyInstruction').value = instruction;
    $('policySamples').value = samples;
    $('policySampleDirection').value = direction;
    $('policySampleTarget').value = target;
    studioMessage('Describe the intended change, then draft it with Laya.');
  };
});
function policyEffect(operation) {
  const directions = {input: 'inputs', output: 'outputs', both: 'inputs and outputs'};
  const targets = {model: 'model', tool: 'tool', all: 'model and tool'};
  if (operation.type === 'upsert_text_rule') {
    const rule = operation.rule;
    const predicate = {contains: 'the content contains', word_contains: 'a word contains', equals: 'the content equals'}[rule.operator];
    return 'Block ' + targets[rule.target] + ' ' + directions[rule.direction] + ' when ' + predicate +
      ' ' + JSON.stringify(rule.value) + ' (' + (rule.case_sensitive ? 'case sensitive' : 'case insensitive') + ').';
  }
  if (operation.type === 'set_privacy' || operation.type === 'set_privacy_detector') {
    const detector = {pii_email: 'email addresses', pii_polish_id: 'eleven-digit Polish ID matches'};
    const subject = operation.type === 'set_privacy' ? 'detected personal data and secrets' : detector[operation.detector];
    return (operation.action === 'block' ? 'Block content containing ' : 'Redact ') + subject +
      ' in all ' + directions[operation.direction] + '.' +
      (operation.type === 'set_privacy' ? ' Individual detector exceptions for these directions are reset.' : ' Other detectors keep their configured actions.');
  }
  if (operation.type === 'restrict_tool_roles') {
    return 'Allow ' + operation.tool + ' only for these roles: ' + operation.roles.join(', ') + '.';
  }
  return 'Inspect the exact operation below before activation.';
}

function showProposal(proposal) {
  studioProposal = proposal;
  $('policyDraftSection').classList.remove('hidden');
  $('policyDraftMeta').textContent = 'Based on policy v' + proposal.base_version + ' · ' + proposal.model +
    ' · drafted in ' + (proposal.inference_ms / 1000).toFixed(2) + ' s · expires ' +
    new Date(proposal.expires_at).toLocaleTimeString();
  $('policyOperations').textContent = JSON.stringify(proposal.operations, null, 2);
  $('policyEffects').replaceChildren(...proposal.operations.map((operation) => el('li', policyEffect(operation))));
  $('policyRolePreviewNote').classList.toggle('hidden', !proposal.operations.some((operation) => operation.type === 'restrict_tool_roles'));
  $('policyDiff').replaceChildren(...proposal.changes.map((change) => {
    const row = document.createElement('tr');
    [change.path, JSON.stringify(change.before), JSON.stringify(change.after)].forEach((value) => {
      const cell = el('td', value ?? '—');
      cell.style.whiteSpace = 'pre-wrap';
      cell.style.wordBreak = 'break-word';
      row.append(cell);
    });
    return row;
  }));
  $('policyDraftWarnings').textContent = proposal.warnings.map((warning) => warning === 'privacy_was_disabled_enabling_existing_detectors' ? 'Privacy checks were disabled. This proposal also enables the existing privacy detectors; inspect the full diff below.' : warning).join(' ');
  $('policyDraftWarnings').classList.toggle('hidden', !proposal.warnings.length);
}
$('draftPolicy').onclick = async () => {
  invalidateStudioProposal();
  const instruction = $('policyInstruction').value.trim();
  if (!instruction) { studioMessage('Describe a policy first.', true); return; }
  const token = admin;
  studioLock(true);
  studioMessage('Laya is drafting a proposal. This can take several seconds; your policy stays active.');
  try {
    const status = await api('/api/admin/status', token);
    if (!status.configuration.management_writable) throw Error('Update this policy at its configured remote source.');
    const result = await api('/api/admin/policies/draft', token, {instruction, base_version: status.policy.version});
    if (admin !== token) throw Error('Management identity changed. Draft again.');
    showProposal(result);
    studioMessage('Proposal ready. Inspect the changes and test examples before activation.');
  } catch (error) { studioMessage(error.message, true); }
  finally { studioLock(false); }
};
$('previewPolicy').onclick = async () => {
  if (!studioProposal) return;
  invalidateStudioPreview();
  const revision = studioRevision;
  const proposal = studioProposal;
  const token = admin;
  const samples = $('policySamples').value.split('\n').map((text) => ({
    text, target: $('policySampleTarget').value, direction: $('policySampleDirection').value,
  }));
  studioLock(true);
  studioMessage('Testing examples against the proposed local controls…');
  try {
    const result = await api('/api/admin/policies/preview', token, {proposal_id: proposal.proposal_id, samples});
    if (revision !== studioRevision || studioProposal !== proposal || admin !== token) throw Error('Proposal changed. Preview again.');
    $('policySampleResults').replaceChildren(...result.results.map((sample, index) => {
      const row = el('div', '', 'budgetrow');
      row.append(el('strong', 'Sample ' + (index + 1) + ': ' + sample.decision.toUpperCase(),
        sample.decision === 'blocked' ? 'red' : sample.decision === 'redacted' ? 'amber' : 'green'));
      row.append(el('p', sample.reason + (sample.findings.length ? ' · ' + sample.findings.join(', ') : ''), 'small'));
      if (sample.safe_text !== null && sample.safe_text !== undefined) row.append(el('pre', sample.safe_text));
      return row;
    }));
    studioPreviewed = true;
    studioMessage('Examples checked. Confirm you reviewed the changes to enable activation.');
  } catch (error) { studioMessage(error.message, true); }
  finally { studioLock(false); }
};
$('activatePolicyDraft').onclick = async () => {
  if (!studioProposal || !studioPreviewed || !$('policyReviewed').checked || studioBusy) return;
  const proposal = studioProposal;
  studioLock(true);
  studioMessage('Activating the exact reviewed proposal…');
  try {
    const result = await api('/api/admin/policies/activate', admin, {
      proposal_id: proposal.proposal_id, base_version: proposal.base_version,
    });
    invalidateStudioProposal();
    await refresh();
    studioMessage('Policy v' + result.policy_version + ' is active. Test it in the playground; no model was called during activation.');
  } catch (error) { invalidateStudioPreview(); studioMessage(error.message, true); }
  finally { studioLock(false); }
};
