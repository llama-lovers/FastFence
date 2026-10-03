"""Execute the delivered browser code against a minimal DOM/network fixture."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path("src/fastfence/app/interfaces/http/web")

HARNESS = r"""
import assert from 'node:assert/strict';
import vm from 'node:vm';
let raw=''; for await (const chunk of process.stdin) raw+=chunk;
const payload=JSON.parse(raw);
const fields=new Map(); const calls=[];
function element(id='') {
  return {value:'',checked:false,textContent:'',children:[],disabled:false,dataset:{},
    classList:{toggle(){},add(){},remove(){}},style:{},
    replaceChildren(...children){this.children=children},append(...children){this.children.push(...children)},prepend(...children){this.children.unshift(...children)},
    setAttribute(){},removeAttribute(){},focus(){},
    addEventListener(){},querySelectorAll(){return []},showModal(){this.open=true},close(){this.open=false}};
}
function get(id){if(!fields.has(id))fields.set(id,element(id));return fields.get(id)}
const storage=new Map();let sequence=0;
const context=vm.createContext({
  console,JSON,Number,Object,Date,Error,crypto:{randomUUID(){return 'conversation-'+(++sequence)}},
  sessionStorage:{getItem(k){return storage.get(k)},setItem(k,v){storage.set(k,v)},removeItem(k){storage.delete(k)}},
  document:{getElementById:get,querySelectorAll(){return []},createElement(){return element()},addEventListener(){},dispatchEvent(){}},
  window:{addEventListener(){}},location:{hash:'',origin:'http://fixture.invalid'},history:{replaceState(){}},
  CustomEvent:class {constructor(type,options){this.type=type;this.detail=options?.detail}},
  setInterval(){},fetch(){throw Error('unexpected real network')}
});
vm.runInContext(payload.inline,context);
vm.runInContext(payload.playground,context);
vm.runInContext(payload.studio,context);
context.get=get;context.calls=calls;context.storage=storage;context.assert=assert;
await vm.runInContext(`(async()=>{
  agent='agent-a'; admin=''; refresh=async()=>{};
  api=async(path,token,body)=>{calls.push({path,token,body}); return {
    request_id:'request',decision:'redacted',reason:'privacy_redacted',policy_version:1,
    feed_version:2,latency_ms:1,upstream_executed:true,anonymized:true,restored:false,
    output:{text:'ANONIM_1'},findings:[],tokens:1
  }};
  get('playgroundMode').value='tool';get('tool').value='knowledge.search';
  get('arguments').value='{"query":"Private project"}';
  await get('invokeBtn').onclick();
  assert.equal(Object.hasOwn(calls[0].body,'conversation_id'),false);
  assert.equal(calls[0].body.restore_originals,false);
  get('playgroundMode').value='model';get('completionModel').value='fixture-model';
  get('completionPrompt').value='Private project';get('completionTokens').value='8';
  await get('invokeBtn').onclick();
  assert.equal(calls[1].path,'/api/models/complete');
  assert.equal(Object.hasOwn(calls[1].body,'conversation_id'),false);
  assert.equal(calls[1].body.restore_originals,false);
  get('restoreOriginals').checked=true;await get('invokeBtn').onclick();
  assert.equal(calls[2].body.restore_originals,true);
  api=async()=>({subject:'actor-b',tenant:'blue',admin:false});
  get('agentToken').value='agent-b';get('adminToken').value='';
  get('restoreOriginals').checked=true;await get('saveConnect').onclick();
  assert.equal(agent,'agent-b');assert.equal(get('restoreOriginals').checked,false);
  assert.deepEqual([...storage.keys()],[]);
  let resolve;api=()=>new Promise(done=>resolve=done);
  const pending=get('invokeBtn').onclick();resetPlaygroundConversation();
  resolve({decision:'allowed',reason:'allowed'});await pending;
  assert.equal(get('result').children[0].textContent,'No request sent for this identity.');
  const effect=policyEffect({type:'upsert_anonymization_rule',rule:{
    operator:'literal',value:'Private project',replacement:'PROJECT',case_sensitive:true,
    target:'all',direction:'both',allow_restore:false
  }});
  assert.match(effect,/scoped PROJECT/);assert.match(effect,/not permitted/);
  assert.match(policyEffect({type:'remove_anonymization_rule',rule_id:'project'}),/only anonymization rule project/);
  admin='management';studioProposal={proposal_id:'fixture-proposal'};
  get('policySamples').value='Hello';get('policySampleTarget').value='model';get('policySampleDirection').value='input';
  get('policyGeneratedTests').value=JSON.stringify([{label:'reviewed',text:'Cat',expected_decision:'no_local_match'}]);
  const before={decision:'no_local_match',reason:'no_local_match',findings:[],safe_text:'Cat'};
  const after={decision:'blocked',reason:'input_text_rule',findings:['letter-a'],safe_text:null};
  const comparison={before,after,changed:true};
  api=async(path,token,body)=>({results:[],comparisons:[],tests_passed:false,test_results:[{test:body.tests[0],passed:false,comparison}]});
  await get('previewPolicy').onclick();get('policyReviewed').checked=true;updateStudioActivation();
  assert.equal(get('activatePolicyDraft').disabled,true);
  assert.equal(JSON.parse(get('policyGeneratedTests').value)[0].expected_decision,'no_local_match');
  assert.match(get('policyRegressionResults').children[0].children[0].textContent,/FAIL/);
  get('policyGeneratedTests').value=JSON.stringify([{label:'reviewed',text:'Cat',expected_decision:'blocked'}]);
  api=async(path,token,body)=>({results:[],comparisons:[],tests_passed:true,test_results:[{test:body.tests[0],passed:true,comparison}]});
  await get('previewPolicy').onclick();
  assert.equal(get('policyReviewed').checked,false);
  get('policyReviewed').checked=true;updateStudioActivation();assert.equal(get('activatePolicyDraft').disabled,false);

})()`,context);
"""


def test_browser_stateless_calls_require_explicit_restoration_consent():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Browser lifecycle fixture requires Node.js")
    html = (WEB / "index.html").read_text()
    inline = (WEB / "console.js").read_text()
    result = subprocess.run(
        [node, "--input-type=module", "-e", HARNESS],
        input=json.dumps(
            {
                "inline": inline,
                "playground": (WEB / "playground.js").read_text(),
                "studio": (WEB / "policy-studio.js").read_text(),
            }
        ),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert 'id="restoreOriginals" type="checkbox"' in html
    assert 'id="restoreOriginals" type="checkbox" checked' not in html


class AliasAuthorFixture:
    """Explicit operation-generation fixture; it makes no live inference claim."""

    def __init__(self):
        self.calls = 0

    async def draft(self, request):
        self.calls += 1
        assert "UpsertAnonymizationRule" in request["schema"]["$defs"]
        assert request["catalog"]["anonymization"]["rules"] == []
        return {
            "source": "real_laya",
            "model": "qwen3:4b",
            "inference_ms": 0,
            "proposal": {
                "supported": True,
                "operations": [
                    {
                        "type": "upsert_anonymization_rule",
                        "rule": {
                            "id": "private-project",
                            "operator": "literal",
                            "value": "Private project",
                            "replacement": "PROJECT",
                            "allow_restore": True,
                        },
                    },
                ],
            },
        }


def test_reviewed_alias_policy_drafts_and_activates_without_second_generation(
    client, tokens, app
):
    from tests.fixtures.auth import headers

    author = AliasAuthorFixture()
    app.state.policy_authoring.author = author
    before = app.state.runtime.snapshot().policy
    credentials = headers(tokens, "security-admin")
    draft = client.post(
        "/api/admin/policies/draft",
        headers=credentials,
        json={
            "instruction": "Anonymize a private project with explicit restoration permission",
            "base_version": before.version,
        },
    )
    assert draft.status_code == 200, draft.text
    proposal = draft.json()
    rule = proposal["operations"][0]["rule"]
    assert rule["replacement"] == "PROJECT" and rule["allow_restore"] is True
    assert before.anonymization.enabled is False
    preview = client.post(
        "/api/admin/policies/preview",
        headers=credentials,
        json={
            "proposal_id": proposal["proposal_id"],
            "samples": [],
        },
    )
    assert preview.status_code == 200, preview.text
    activation = client.post(
        "/api/admin/policies/activate",
        headers=credentials,
        json={
            "proposal_id": proposal["proposal_id"],
            "base_version": before.version,
        },
    )
    assert activation.status_code == 200, activation.text
    active = app.state.runtime.snapshot().policy
    assert active.anonymization.enabled
    assert active.anonymization.rules[0].allow_restore is True
    assert active.privacy == before.privacy
    assert active.budgets == before.budgets
    assert author.calls == 1
