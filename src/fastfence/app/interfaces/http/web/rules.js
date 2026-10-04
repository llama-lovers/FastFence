let previewedRule = null;
let ruleBase = null;
let ruleOwner = '';
let ruleOriginalId = '';
let ruleBusy = false;
function textRuleDraft() {
  return {id:$('textRuleId').value, operator:$('textRuleOperator').value,
    value:$('textRuleValue').value, direction:$('textRuleDirection').value,
    target:$('textRuleTarget').value, action:'block', case_sensitive:$('textRuleCase').checked,
    ignore_invisible_characters:$('textRuleInvisible').checked};
}
function invalidateRulePreview() {
  previewedRule = null;
  $('textRuleReviewed').checked = false;
  $('activateTextRule').disabled = true;
}
function ruleMessage(message, failed = false) {
  $('textRuleMessage').textContent = message;
  $('textRuleMessage').className = 'message ' + (failed ? 'red' : 'green');
}
async function openTextRule(existing = null) {
  if (!admin) { openConnection(); return; }
  if (ruleBusy) return;
  invalidateRulePreview();
  $('textRuleResults').replaceChildren();
  ruleMessage('');
  try {
    const owner = admin;
    const status = await api('/api/admin/status', owner);
    if (admin !== owner) throw Error('Management identity changed. Open the rule again.');
    if (!status.configuration.management_writable) throw Error('This policy is read-only. Publish changes at its remote source.');
    ruleBase = status.policy; ruleOwner = owner;
    if (existing) {
      existing = status.policy.text_rules.find(rule => rule.id === existing.id);
      if (!existing) throw Error('This rule no longer exists. Refresh the policy.');
    }
    ruleOriginalId = existing ? existing.id : '';
    const rule = existing || {id:'',operator:'contains',value:'',direction:'input',target:'model',case_sensitive:false};
    for (const [field, key] of [['textRuleId','id'],['textRuleOperator','operator'],['textRuleValue','value'],['textRuleDirection','direction'],['textRuleTarget','target']]) $(field).value = rule[key];
    $('textRuleCase').checked = rule.case_sensitive;
    $('textRuleInvisible').checked = rule.ignore_invisible_characters === true;
    $('textRuleId').disabled = !!existing;
    $('textRuleSamples').value = '';
    $('textRuleTitle').textContent = existing ? 'Edit text rule' : 'Add text rule';
    $('textRuleVersion').textContent = 'Active v' + ruleBase.version + ' → proposed v' + (ruleBase.version + 1);
    $('textRuleDialog').showModal();
  } catch (error) { ruleMessage(error.message, true); $('textRuleDialog').showModal(); }
}
$('textRuleBtn').onclick = () => openTextRule();
$('closeTextRule').onclick = () => { if (!ruleBusy) $('textRuleDialog').close(); };
$('textRuleDialog').querySelectorAll('input, select, textarea').forEach(field => {
  if (field.id !== 'textRuleReviewed') field.addEventListener('input', invalidateRulePreview);
});
$('textRuleReviewed').onchange = () => {
  $('activateTextRule').disabled = !previewedRule || !$('textRuleReviewed').checked || ruleBusy;
};
$('previewTextRule').onclick = async () => {
  invalidateRulePreview();
  if (!ruleBase || admin !== ruleOwner) { ruleMessage('Reopen the rule using your current management identity.', true); return; }
  const draft = textRuleDraft(), fingerprint = JSON.stringify(draft), sampleText = $('textRuleSamples').value;
  if (!sampleText.trim()) { ruleMessage('Add at least one sample to test the match before activation.', true); return; }
  ruleBusy = true; $('previewTextRule').disabled = true;
  try {
    const owner = ruleOwner;
    const result = await api('/api/admin/rules/preview', owner, {rule:draft, samples:sampleText.split('\n')});
    if (admin !== owner || JSON.stringify(textRuleDraft()) !== fingerprint || $('textRuleSamples').value !== sampleText) throw Error('The identity or draft changed. Test it again.');
    previewedRule = result.rule;
    $('textRuleResults').replaceChildren(el('p', result.rule.ignore_invisible_characters ? 'Matching ignores U+200B, U+200C, U+200D, U+2060 and U+FEFF. Original content is unchanged.' : 'Matching preserves invisible characters. Original content is unchanged.'), ...result.matches.map((matches, index) => el('div', 'Sample ' + (index + 1) + ': ' + (matches ? 'BLOCK' : 'NO MATCH'), matches ? 'red' : 'green')));
    $('textRuleBefore').textContent = ruleOriginalId ? JSON.stringify(ruleBase.text_rules.find(item => item.id === ruleOriginalId), null, 2) : 'New rule';
    $('textRuleAfter').textContent = JSON.stringify(result.rule, null, 2);
    ruleMessage('Test complete. Review the match results and exact change, then confirm. This tests this rule only; other controls still apply.');
  } catch (error) { ruleMessage(error.message, true); }
  finally { ruleBusy = false; $('previewTextRule').disabled = false; }
};
$('activateTextRule').onclick = async () => {
  if (!previewedRule || !$('textRuleReviewed').checked || ruleBusy) return;
  const rule = previewedRule, owner = ruleOwner, base = ruleBase;
  ruleBusy = true; invalidateRulePreview();
  try {
    if (admin !== owner) throw Error('Management identity changed. Reopen this rule.');
    const status = await api('/api/admin/status', owner);
    if (admin !== owner) throw Error('Management identity changed. Reopen this rule.');
    if (!status.configuration.management_writable) throw Error('Publish this change at the configured remote source.');
    if (JSON.stringify(status.policy) !== JSON.stringify(base)) throw Error('Policy changed since editing began. Reopen the rule and test against the latest version.');
    const rules = base.text_rules || [];
    if (!ruleOriginalId && rules.some(item => item.id === rule.id)) throw Error('This rule ID already exists. Edit it from the policy list.');
    const next = ruleOriginalId ? rules.map(item => item.id === ruleOriginalId ? rule : item) : [...rules, rule];
    const result = await api('/api/admin/policy', owner, {...base, version:base.version + 1, text_rules:next}, 'PUT');
    if (admin !== owner) return;
    await refresh();
    if (admin !== owner) return;
    ruleMessage('Policy v' + result.policy_version + ' is active. New requests use the updated rule. No restart is needed.');
  } catch (error) { ruleMessage(error.message, true); }
  finally { ruleBusy = false; }
};
