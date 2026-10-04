let policyStatus = null;
let policyBase = null;
let policyWorking = null;
let policyCandidate = null;
let policyOwner = '';
let policyManagerBusy = false;
let anonOwner = '';
function policyManagerLock(locked) {
  policyManagerBusy = locked;
  $('policyDialog').querySelectorAll('input,select,textarea,button').forEach(field => { field.disabled = locked; });
  $('policyReview').disabled = locked || !policyStatus?.configuration.management_writable;
  $('savePolicy').disabled = locked || !policyCandidate || !$('policyConfirm').checked;
  if (!locked) updateSemanticFields();
}
const clonePolicy = (value) => JSON.parse(JSON.stringify(value));
function policyMessage(message, failed = false) {
  $('policyMessage').textContent = message;
  $('policyMessage').className = 'message ' + (failed ? 'red' : 'green');
}
function invalidatePolicyReview() {
  policyCandidate = null;
  $('policyConfirm').checked = false;
  $('savePolicy').disabled = true;
  $('policyReviewSection').classList.add('hidden');
}
function policyChanges(before, after, path = '') {
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  if (before && after && typeof before === 'object' && typeof after === 'object' && !Array.isArray(before) && !Array.isArray(after)) {
    return [...new Set([...Object.keys(before), ...Object.keys(after)])].flatMap(key => policyChanges(before[key], after[key], path ? path + '.' + key : key));
  }
  return [{path, before, after}];
}
function renderPolicyDiff(before, after) {
  const changes = policyChanges(before, after);
  $('policyReviewDiff').replaceChildren(...changes.map(change => {
    const row = el('tr', '');
    [change.path, JSON.stringify(change.before) ?? 'Not set', JSON.stringify(change.after) ?? 'Removed'].forEach(text => row.append(el('td', text)));
    return row;
  }));
  return changes;
}
function populatePolicyFields(policy) {
  $('policyDescription').value = policy.description;
  $('policyPrivacyEnabled').checked = policy.privacy.enabled;
  $('policyPrivacyInput').value = policy.privacy.input;
  $('policyPrivacyOutput').value = policy.privacy.output;
  $('policySignatures').checked = policy.signatures_enabled;
  $('policySemanticProvider').value = policy.semantic.provider;
  $('policySemanticModel').value = policy.semantic.model;
  $('policySemanticThreshold').value = policy.semantic.threshold;
  $('policySemanticTimeout').value = policy.semantic.timeout_ms;
  $('policySemanticOutput').checked = policy.semantic.scan_output;
  $('policySemanticInstructions').value = policy.semantic.instructions || '';
  updateSemanticFields();
  $('policyAnonEnabled').checked = policy.anonymization.enabled;
  $('policyAnonMode').value = policy.anonymization.mode;
  $('policyJson').value = JSON.stringify({...policy, version: policy.version + 1}, null, 2);
  $('policyVersionPath').textContent = 'Active v' + policy.version + ' → proposed v' + (policy.version + 1);
  $('policyOverrideNote').textContent = Object.keys(policy.privacy.detector_actions || {}).length ? 'Individual detector overrides remain active. Inspect them in Advanced configuration before changing the default actions.' : 'Actions apply to detected personal data and secrets.';
}
async function openPolicyManager(candidate = null) {
  if (!admin) { openConnection(); return; }
  try {
    const token = admin;
    const status = await api('/api/admin/status', token);
    if (admin !== token) throw Error('Management identity changed. Open the policy again.');
    if (candidate && candidate.version !== status.policy.version) throw Error('Policy changed. Refresh the rule list before editing.');
    policyStatus = status;
    policyBase = clonePolicy(status.policy);
    policyOwner = token;
    invalidatePolicyReview();
    policyWorking = clonePolicy(candidate || policyBase);
    populatePolicyFields(policyWorking);
    $('policyVersionPath').textContent = 'Active v' + policyBase.version + ' → proposed v' + (policyBase.version + 1);
    $('policyStructured').classList.remove('hidden');
    $('policyJsonMode').checked = false;
    $('policyAdvanced').open = false;
    $('policyReview').disabled = !status.configuration.management_writable;
    policyMessage(status.configuration.management_writable ? 'Edit settings, review the exact changes, then activate. The current policy remains active until you confirm.' : 'Read-only: this instance receives policy from a remote source. Publish there, then refresh the source.');
    $('policyDialog').showModal();
  } catch (error) { policyMessage(error.message, true); $('policyDialog').showModal(); }
}
function structuredPolicyCandidate() {
  const candidate = clonePolicy(policyWorking || policyBase);
  candidate.description = $('policyDescription').value;
  candidate.privacy.enabled = $('policyPrivacyEnabled').checked;
  candidate.privacy.input = $('policyPrivacyInput').value;
  candidate.privacy.output = $('policyPrivacyOutput').value;
  candidate.signatures_enabled = $('policySignatures').checked;
  candidate.semantic = {...candidate.semantic,
    provider: $('policySemanticProvider').value, model: $('policySemanticModel').value,
    threshold: Number($('policySemanticThreshold').value), timeout_ms: Number($('policySemanticTimeout').value),
    scan_output: $('policySemanticOutput').checked,
    instructions: $('policySemanticProvider').value === 'laya' ? $('policySemanticInstructions').value : '',
  };
  candidate.anonymization.enabled = $('policyAnonEnabled').checked;
  candidate.anonymization.mode = $('policyAnonMode').value;
  return candidate;
}
function renderPolicyInventory(status) {
  policyStatus = status;
  const summary = $('policySummary');
  if (summary) summary.textContent = 'Version ' + status.policy.version + ' · ' + (status.configuration.management_writable ? 'Editable on this gateway' : 'Managed by remote source');
  const container = $('policyInventory');
  if (!container) return;
  const controls = status.policy;
  const overview = el('div', '', 'rule-card');
  overview.append(el('strong', 'Current protection'));
  overview.append(el('p', 'Privacy: ' + (controls.privacy.enabled ? 'input ' + controls.privacy.input + ' · output ' + controls.privacy.output : 'disabled')));
  overview.append(el('p', 'Semantic analysis: ' + (controls.semantic.provider === 'disabled' ? 'disabled' : controls.semantic.provider + ' · ' + controls.semantic.model + ' · ' + (controls.semantic.scan_output ? 'input and output' : 'input only'))));
  if (controls.semantic.instructions) overview.append(el('p', 'Semantic policy: ' + controls.semantic.instructions));
  overview.append(el('p', 'Anonymization: ' + (controls.anonymization.enabled ? controls.anonymization.mode : 'disabled')));
  const rows = [overview];
  for (const [kind, rules] of [['Laya', status.policy.semantic.rules || []], ['Text', status.policy.text_rules || []], ['Anonymization', status.policy.anonymization.rules || []]]) {
    for (const rule of rules) {
      const row = el('div', '', 'rule-card');
      row.append(el('strong', rule.id), el('p', kind + ' · ' + rule.direction + ' · ' + rule.target, 'small'));
      row.append(el('p', kind === 'Laya' ? rule.instruction : rule.operator + ' “' + rule.value + '”' + (kind === 'Anonymization' ? ' → ' + rule.replacement : ' → block')));
      const controls = el('div', '', 'actions');
      const edit = el('button', 'Edit rule', 'btn');
      edit.disabled = !status.configuration.management_writable;
      edit.onclick = () => kind === 'Laya' ? openLayaRule(rule) : kind === 'Text' ? openTextRule(rule) : openAnonymizationRule(rule);
      const remove = el('button', 'Remove…', 'btn');
      remove.disabled = edit.disabled;
      remove.onclick = async () => {
        const next = clonePolicy(status.policy);
        if (kind === 'Laya') next.semantic.rules = next.semantic.rules.filter(item => item.id !== rule.id);
        else if (kind === 'Text') next.text_rules = next.text_rules.filter(item => item.id !== rule.id);
        else next.anonymization.rules = next.anonymization.rules.filter(item => item.id !== rule.id);
        await openPolicyManager(next);
      };
      controls.append(edit, remove); row.append(controls); rows.push(row);
    }
  }
  if (rows.length === 1) rows.push(el('p', 'No custom rules yet. Add a text rule, an anonymization rule, or describe a policy in natural language.', 'empty-state'));
  container.replaceChildren(...rows);
}
$('policyBtn').onclick = () => openPolicyManager();
$('closePolicy').onclick = () => { if (!policyManagerBusy) $('policyDialog').close(); };
$('policyDialog').querySelectorAll('input,select,textarea').forEach(field => {
  if (field.id !== 'policyConfirm') field.addEventListener('input', invalidatePolicyReview);
});
$('policyConfirm').onchange = () => { $('savePolicy').disabled = policyManagerBusy || !policyCandidate || !$('policyConfirm').checked; };
$('policyReview').onclick = () => {
  invalidatePolicyReview();
  if (!policyStatus?.configuration.management_writable) return;
  try {
    if (!policyBase || admin !== policyOwner) throw Error('Management identity changed. Reopen the policy.');
    const candidate = $('policyJsonMode').checked ? JSON.parse($('policyJson').value) : structuredPolicyCandidate();
    candidate.version = policyBase.version + 1;
    const changes = renderPolicyDiff(policyBase, candidate);
    if (changes.every(change => change.path === 'version')) throw Error('There are no settings changes to activate.');
    policyCandidate = candidate;
    $('policyReviewSection').classList.remove('hidden');
    policyMessage('Review these changes. Activation validates and saves the policy atomically; this settings review does not run traffic or regression tests.');
  } catch (error) { policyMessage(error.message, true); }
};
$('savePolicy').onclick = async () => {
  if (!policyCandidate || !$('policyConfirm').checked || policyManagerBusy) return;
  const candidate = clonePolicy(policyCandidate), owner = policyOwner, base = clonePolicy(policyBase);
  policyManagerLock(true);
  try {
    if (admin !== owner) throw Error('Management identity changed. Reopen the policy.');
    const latest = await api('/api/admin/status', owner);
    if (admin !== owner) throw Error('Management identity changed. Reopen the policy.');
    if (!latest.configuration.management_writable) throw Error('The configured policy source is read-only.');
    if (JSON.stringify(latest.policy) !== JSON.stringify(base)) throw Error('The active policy changed. Reopen the editor and review against the latest version.');
    const result = await api('/api/admin/policy', owner, candidate, 'PUT');
    if (admin !== owner) return;
    invalidatePolicyReview();
    await refresh();
    if (admin !== owner) return;
    policyBase = clonePolicy(candidate); policyWorking = clonePolicy(candidate); populatePolicyFields(candidate);
    policyMessage('Policy v' + result.policy_version + ' is active. New requests use this version; no restart is needed.');
  } catch (error) { invalidatePolicyReview(); policyMessage(error.message, true); }
  finally { policyManagerLock(false); }
};
$('reloadPolicy').onclick = async () => {
  try {
    invalidatePolicyReview();
    const owner = admin;
    await api('/api/admin/reload', owner, {});
    if (admin !== owner) return;
    await refresh();
    policyMessage('Source refreshed. Your unsaved editor values are preserved. Close and reopen the editor to load the current policy before activating.');
  } catch (error) { policyMessage(error.message, true); }
};
function openAnonymizationRule(rule = null) {
  if (!admin) { openConnection(); return; }
  if (!active) return;
  anonOwner = admin;
  const defaults = {id:'',operator:'literal',value:'',replacement:'ANONIM',direction:'both',target:'all',case_sensitive:true,allow_restore:false};
  const value = rule || defaults;
  $('anonRuleDialog').dataset.originalId = rule ? rule.id : '';
  $('anonRuleDialog').dataset.version = String(active.version);
  for (const key of ['id','operator','value','replacement','direction','target']) $('anon_' + key).value = value[key];
  for (const key of ['case_sensitive','allow_restore']) $('anon_' + key).checked = value[key];
  $('anon_id').disabled = !!rule;
  $('anonRuleMessage').textContent = '';
  $('anonRuleDialog').showModal();
}
$('anonymizationRuleBtn').onclick = () => openAnonymizationRule();
$('closeAnonRule').onclick = () => $('anonRuleDialog').close();
$('reviewAnonRule').onclick = async () => {
  try {
    if (admin !== anonOwner) throw Error('Management identity changed. Reopen this rule.');
    if (String(active.version) !== $('anonRuleDialog').dataset.version) throw Error('Policy changed. Reopen this rule before editing.');
    const next = clonePolicy(active), rule = {};
    for (const key of ['id','operator','value','replacement','direction','target']) rule[key] = $('anon_' + key).value;
    for (const key of ['case_sensitive','allow_restore']) rule[key] = $('anon_' + key).checked;
    if (!rule.replacement) rule.replacement = 'ANONIM';
    const original = $('anonRuleDialog').dataset.originalId;
    if (!original && next.anonymization.rules.some(item => item.id === rule.id)) throw Error('A rule with this ID already exists. Edit it from the rule list.');
    next.anonymization.rules = original ? next.anonymization.rules.map(item => item.id === original ? rule : item) : [...next.anonymization.rules, rule];
    next.anonymization.enabled = true;
    $('anonRuleDialog').close();
    await openPolicyManager(next);
  } catch (error) { $('anonRuleMessage').textContent = error.message; }
};
document.addEventListener('fastfence:status', event => {
  renderPolicyInventory(event.detail);
  if (studioProposal && studioProposal.base_version !== event.detail.policy.version) {
    invalidateStudioProposal(); studioMessage('The active policy changed. Draft again against the latest version.', true);
  }
});

document.addEventListener('fastfence:identity', () => { invalidatePolicyReview(); invalidateRulePreview(); invalidateStudioProposal(); policyBase = null; ruleBase = null; });

$('policyDialog').addEventListener('cancel', event => { if (policyManagerBusy) event.preventDefault(); });

function updateSemanticFields() {
  $('policySemanticInstructions').disabled = $('policySemanticProvider').value !== 'laya';
}
$('policySemanticProvider').addEventListener('change', updateSemanticFields);
