let previewedRule = null;

function textRuleDraft() {
  return {
    id: $('textRuleId').value,
    operator: $('textRuleOperator').value,
    value: $('textRuleValue').value,
    direction: $('textRuleDirection').value,
    target: $('textRuleTarget').value,
    action: 'block',
    case_sensitive: $('textRuleCase').checked,
  };
}

function invalidateRulePreview() {
  previewedRule = null;
  $('activateTextRule').disabled = true;
}

function ruleMessage(message, failed = false) {
  $('textRuleMessage').textContent = message;
  $('textRuleMessage').className = 'message ' + (failed ? 'red' : 'green');
}

$('textRuleBtn').onclick = () => {
  if (!admin) {
    $('connectDialog').showModal();
    return;
  }
  invalidateRulePreview();
  $('textRuleResults').replaceChildren();
  ruleMessage('');
  $('textRuleDialog').showModal();
};
$('closeTextRule').onclick = () => $('textRuleDialog').close();
$('textRuleDialog').querySelectorAll('input, select, textarea').forEach((field) => {
  field.addEventListener('input', invalidateRulePreview);
});

$('previewTextRule').onclick = async () => {
  invalidateRulePreview();
  $('previewTextRule').disabled = true;
  const draft = textRuleDraft();
  const fingerprint = JSON.stringify(draft);
  const sampleText = $('textRuleSamples').value;
  try {
    const result = await api('/api/admin/rules/preview', admin, {
      rule: draft,
      samples: sampleText.split('\n'),
    });
    if (JSON.stringify(textRuleDraft()) !== fingerprint || $('textRuleSamples').value !== sampleText) {
      throw Error('The draft changed. Preview it again.');
    }
    previewedRule = result.rule;
    $('textRuleResults').replaceChildren(...result.matches.map((matches, index) =>
      el('div', 'Sample ' + (index + 1) + ': ' + (matches ? 'BLOCK' : 'NO MATCH'), matches ? 'red' : 'green')
    ));
    $('activateTextRule').disabled = false;
    ruleMessage('Validated. Preview checks this rule only; other controls still apply.');
  } catch (error) {
    ruleMessage(error.message, true);
  } finally {
    $('previewTextRule').disabled = false;
  }
};

$('activateTextRule').onclick = async () => {
  if (!previewedRule) return;
  const rule = previewedRule;
  invalidateRulePreview();
  try {
    const status = await api('/api/admin/status', admin);
    if (!status.configuration.management_writable) {
      throw Error('This instance uses a remote policy source. Publish the rule at that source.');
    }
    const rules = status.policy.text_rules || [];
    if (rules.some((existing) => existing.id === rule.id)) {
      throw Error('This rule ID already exists. Choose a new ID or edit the existing policy.');
    }
    const result = await api('/api/admin/policy', admin, {
      ...status.policy,
      version: status.policy.version + 1,
      text_rules: [...rules, rule],
    }, 'PUT');
    await refresh();
    ruleMessage('Activated ' + rule.id + ' in policy v' + result.policy_version + '. Future matching requests are blocked.');
  } catch (error) {
    ruleMessage(error.message, true);
  }
};
