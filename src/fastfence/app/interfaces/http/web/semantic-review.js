let layaRuleBase = null;
let layaRuleFeed = null;
let layaRuleOwner = '';
let layaRuleOriginal = '';
let layaRulePreview = null;
let layaRuleRevision = 0;
let layaRuleBusy = false;
function layaRuleDraft() {
  return {id:$('layaRuleId').value, instruction:$('layaRuleInstruction').value,
    direction:$('layaRuleDirection').value, target:$('layaRuleTarget').value};
}
function semanticCases() {
  if (layaRuleSavedCases !== null) return clonePolicy(layaRuleSavedCases);
  const rule = layaRuleDraft();
  const directions = rule.direction === 'both' ? ['input','output'] : [rule.direction];
  const targets = rule.target === 'all' ? ['model','tool'] : [rule.target];
  const cases = [];
  for (const [field, expected, prefix] of [['layaRuleBlockSamples','blocked','block'],['layaRulePermitSamples','no_semantic_block','permit']]) {
    const lines = $(field).value.split('\n').filter(text => text.trim());
    if (!lines.length) throw Error('Add at least one blocked example and one permitted example.');
    for (const [index,text] of lines.entries()) {
      if (new TextEncoder().encode(text).length > 4096) throw Error('Each example must fit within 4096 UTF-8 bytes.');
      for (const direction of directions) for (const target of targets) cases.push({id:prefix + '-' + (index+1) + '-' + direction + '-' + target,text,direction,target,expected});
    }
  }
  if (cases.length > 16) throw Error('At most 16 scoped cases fit in one review. With input/output and models/tools selected, use at most four example lines in total.');
  return cases;
}
function semanticFingerprint() {
  return JSON.stringify({rule:layaRuleDraft(),block:$('layaRuleBlockSamples').value,permit:$('layaRulePermitSamples').value,saved:layaRuleSavedCases});
}
function semanticMessage(text, failed = false) {
  $('layaRuleMessage').textContent = text;
  $('layaRuleMessage').className = 'message ' + (failed ? 'red' : 'green');
}
function semanticActivationState() {
  const ready = layaRulePreview && layaRulePreview.fingerprint === semanticFingerprint() &&
    layaRulePreview.owner === admin && Date.parse(layaRulePreview.expires_at) > Date.now();
  $('activateLayaRule').disabled = layaRuleBusy || !ready || !$('layaRuleConfirmed').checked;
}
function updateSemanticCaseCount() {
  try {
    const count = semanticCases().length;
    $('layaRuleCallCount').textContent = count + ' submitted scoped cases · up to ' + (count*2) + ' Laya assessments for these cases, plus saved regressions from other active rules (at most 128 assessments total, 120-second deadline). No business model or tool is executed.';
  } catch (error) { $('layaRuleCallCount').textContent = error.message; }
}
function invalidateLayaRuleTest() {
  layaRuleRevision += 1; layaRulePreview = null;
  $('layaRuleConfirmed').checked = false;
  $('layaRuleResults').replaceChildren();
  $('layaRuleDiff').textContent = '';
  $('layaRuleWarnings').textContent = '';
  $('layaRuleTestResult').textContent = '';
  semanticActivationState(); updateSemanticCaseCount();
}
function lockSemanticReview(locked) {
  layaRuleBusy = locked;
  $('layaRuleDialog').querySelectorAll('input,textarea,select,button').forEach(field => { field.disabled = locked; });
  $('layaRuleId').disabled = locked || !!layaRuleOriginal;
  semanticActivationState();
}
async function openLayaRule(existing = null) {
  if (!admin) { openConnection(); return; }
  if (layaRuleBusy) return;
  invalidateLayaRuleTest(); layaRuleBase = null; layaRuleFeed = null;
  const owner = admin;
  lockSemanticReview(true);
  try {
    const status = await api('/api/admin/status', owner);
    if (admin !== owner) return;
    if (!status.configuration.management_writable) throw Error('This policy is read-only. Publish changes at its remote source.');
    const rule = existing ? (status.policy.semantic.rules || []).find(item => item.id === existing.id) : {id:'',instruction:'',direction:'both',target:'all'};
    if (!rule) throw Error('The rule was removed. Refresh the policy list.');
    layaRuleBase = clonePolicy(status.policy); layaRuleFeed = clonePolicy(status.feed); layaRuleOwner = owner;
    layaRuleOriginal = existing ? rule.id : '';
    for (const [field,key] of [['layaRuleId','id'],['layaRuleInstruction','instruction'],['layaRuleDirection','direction'],['layaRuleTarget','target']]) $(field).value = rule[key];
    $('layaRuleBlockSamples').value = ''; $('layaRulePermitSamples').value = '';
    resetSavedSemanticCases();
    if (existing) await loadSavedSemanticCases(rule,owner);
    if (admin !== owner) return;
    $('layaRuleTitle').textContent = existing ? 'Review a Laya rule change' : 'Add a reviewed Laya rule';
    updateSemanticCaseCount();
    semanticMessage('Define expected outcomes, compare active and proposed behavior, then explicitly confirm activation.');
    $('layaRuleDialog').showModal();
  } catch (error) { if (admin === owner) { semanticMessage(error.message,true); $('layaRuleDialog').showModal(); } }
  finally { lockSemanticReview(false); }
}
function assessmentLabel(result) {
  if (result.status === 'not_evaluated') return 'Not evaluated · ' + (result.reason || 'Not applicable').replaceAll('_',' ');
  if (result.status === 'error') return 'Error · ' + (result.reason || 'Assessment failed').replaceAll('_',' ') + ' · ' + result.latency_ms + ' ms';
  return (result.decision === 'blocked' ? 'Block' : 'No semantic block') + ' · ' + result.latency_ms + ' ms';
}
function renderSemanticReview(result) {
  $('layaRuleResults').replaceChildren(...result.cases.map(item => {
    const row = el('tr');
    [(item.rule_id || '') + ' · ' + item.target + ' ' + item.direction, item.text,
      item.expected === 'blocked' ? 'Block' : 'No semantic block', assessmentLabel(item.before),
      assessmentLabel(item.after), item.passed ? 'PASS' : 'FAIL'].forEach((value,index) => {
      const cell = el('td',value); cell.dataset.label = ['Rule / scope','Example','Expected','Active policy','Proposed policy','Result'][index];
      if (index === 0) cell.title = item.id; row.append(cell);
    });
    return row;
  }));
  $('layaRuleDiff').textContent = result.yaml_diff;
  $('layaRuleWarnings').textContent = [...(result.warnings || []), ...(result.missing_rules || []).map(id => 'Missing reviewed cases for active rule: ' + id)].join(' · ');
  $('layaRuleTestResult').textContent = result.tests_passed ? 'All reviewed expectations passed. Inspect every result and the exact change before confirming.' : 'Some expectations failed or could not be evaluated. Nothing was activated. Edit the rule or reviewed cases and test again.';
}
function validSemanticReview(result, cases) {
  if (result.scope !== 'semantic_only' || result.base_version !== layaRuleBase.version ||
      result.candidate_version !== layaRuleBase.version + 1 || result.feed_version !== layaRuleFeed.version ||
      !Array.isArray(result.cases) || result.cases.length < cases.length || result.cases.length > 64 ||
      typeof result.yaml_diff !== 'string') return false;
  const keys = result.cases.map(item => item.rule_id + '/' + item.id);
  if (new Set(keys).size !== keys.length) return false;
  const submitted = result.cases.filter(item => item.rule_id === layaRuleDraft().id);
  return submitted.length === cases.length && cases.every(source => {
    const item = submitted.find(row => row.id === source.id);
    return item && ['id','text','direction','target','expected'].every(key => item[key] === source[key]);
  });
}
$('layaRuleBtn').onclick = () => openLayaRule();
$('closeLayaRule').onclick = () => { if (!layaRuleBusy) { invalidateLayaRuleTest(); $('layaRuleDialog').close(); } };
$('layaRuleDialog').querySelectorAll('input,textarea,select').forEach(field => {
  if (field.id !== 'layaRuleConfirmed') field.addEventListener('input', invalidateLayaRuleTest);
});
$('layaRuleConfirmed').onchange = semanticActivationState;
$('layaRuleTest').onclick = async () => {
  if (layaRuleBusy) return;
  invalidateLayaRuleTest();
  if (!layaRuleBase || admin !== layaRuleOwner) { semanticMessage('Reopen the editor with your current management identity.',true); return; }
  const rule = layaRuleDraft(), owner = admin, revision = layaRuleRevision, fingerprint = semanticFingerprint();
  let cases;
  try {
    if (!rule.id.trim() || !rule.instruction.trim()) throw Error('Enter a rule ID and its instruction.');
    cases = semanticCases();
  } catch (error) { semanticMessage(error.message,true); return; }
  lockSemanticReview(true);
  $('layaRuleTestResult').textContent = 'Comparing ' + cases.length + ' scoped cases with actual Laya. Your active policy is unchanged…';
  try {
    const status = await api('/api/admin/status', owner);
    if (owner !== admin || revision !== layaRuleRevision || fingerprint !== semanticFingerprint()) return;
    if (!status.configuration.management_writable) throw Error('This configuration is read-only.');
    if (!layaRuleOriginal && (status.policy.semantic.rules || []).some(item => item.id === rule.id)) throw Error('This ID already exists. Reopen it from the rule list.');
    layaRuleBase = clonePolicy(status.policy); layaRuleFeed = clonePolicy(status.feed);
    const result = await api('/api/admin/semantic/review', owner, {base_version:layaRuleBase.version,rule,cases});
    if (owner !== admin || revision !== layaRuleRevision || fingerprint !== semanticFingerprint()) return;
    if (!validSemanticReview(result,cases)) throw Error('The review does not match this draft or configuration. Review again.');
    renderSemanticReview(result);
    const passed = result.tests_passed === true && !(result.missing_rules || []).length && result.cases.every(item => item.passed === true && item.after.status === 'evaluated' && item.after.decision === item.expected && item.before.status !== 'error');
    if (passed && typeof result.review_id === 'string' && result.review_id && Date.parse(result.expires_at) > Date.now()) {
      layaRulePreview = {...result,owner,fingerprint};
      semanticMessage('Reviewed v' + result.base_version + ' → v' + result.candidate_version + ' · ' + result.model + '. No semantic block is not a full gateway ALLOW.');
    } else semanticMessage('Activation is unavailable until every expected outcome passes a complete review.',true);
  } catch (error) { if (owner === admin && revision === layaRuleRevision) { $('layaRuleTestResult').textContent = 'Review failed. The active policy is unchanged.'; semanticMessage(error.message,true); } }
  finally { lockSemanticReview(false); }
};
$('activateLayaRule').onclick = async () => {
  if (layaRuleBusy || !layaRulePreview || !$('layaRuleConfirmed').checked) return;
  const receipt = layaRulePreview, owner = receipt.owner, fingerprint = receipt.fingerprint;
  if (owner !== admin || fingerprint !== semanticFingerprint() || Date.parse(receipt.expires_at) <= Date.now()) { invalidateLayaRuleTest(); semanticMessage('The review changed or expired. Review again.',true); return; }
  lockSemanticReview(true);
  try {
    const status = await api('/api/admin/status',owner);
    if (owner !== admin || fingerprint !== semanticFingerprint() || layaRulePreview !== receipt) return;
    if (!status.configuration.management_writable || JSON.stringify(status.policy) !== JSON.stringify(layaRuleBase) || JSON.stringify(status.feed) !== JSON.stringify(layaRuleFeed)) throw Error('The configuration changed. Review the cases again.');
    const result = await api('/api/admin/semantic/activate',owner,{review_id:receipt.review_id,base_version:receipt.base_version,confirmed:true});
    if (owner !== admin) return;
    if (result.policy_version !== receipt.candidate_version || result.feed_version !== receipt.feed_version) throw Error('Activation response did not confirm the reviewed version. Refresh the active configuration.');
    invalidateLayaRuleTest(); layaRuleBase = null;
    const saved = result.tests_saved === true;
    const message = 'Policy v' + result.policy_version + ' is active. ' + (saved ? 'The reviewed expectations were saved with this activation.' : 'Warning: saving the reviewed expectations failed. The policy is already active; save or restore the regression suite before relying on replay.');
    semanticMessage(message,!saved);
    try { await refresh(); } catch { semanticMessage(message + ' Refreshing the workspace also failed; refresh before another edit.',true); }
  } catch (error) { if (owner === admin) { invalidateLayaRuleTest(); semanticMessage(error.message + ' Review again before retrying activation.',true); } }
  finally { lockSemanticReview(false); }
};
$('layaRuleDialog').addEventListener('cancel', event => { if (layaRuleBusy) event.preventDefault(); else invalidateLayaRuleTest(); });
document.addEventListener('fastfence:status', event => {
  if (layaRuleBase && (JSON.stringify(event.detail.policy) !== JSON.stringify(layaRuleBase) || JSON.stringify(event.detail.feed) !== JSON.stringify(layaRuleFeed) || !event.detail.configuration.management_writable)) {
    invalidateLayaRuleTest(); semanticMessage('The active configuration changed. Review the cases again.',true);
  }
});
document.addEventListener('fastfence:identity', () => {
  invalidateLayaRuleTest(); layaRuleBase = null; layaRuleFeed = null; layaRuleOwner = '';
  for (const id of ['layaRuleId','layaRuleInstruction','layaRuleBlockSamples','layaRulePermitSamples']) $(id).value = '';
  resetSavedSemanticCases(); $('layaRuleDialog').close();
});
setInterval(() => {
  if (layaRulePreview && Date.parse(layaRulePreview.expires_at) <= Date.now()) {
    invalidateLayaRuleTest(); semanticMessage('This review expired. Review the cases again before activation.',true);
  }
},1000);
