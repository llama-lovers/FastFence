"""Execute reviewed semantic authoring UI with adversarial async responses."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path("src/fastfence/app/interfaces/http/web")
HARNESS = r"""
import assert from 'node:assert/strict';
import vm from 'node:vm';
let raw='';for await(const chunk of process.stdin)raw+=chunk;
const scripts=JSON.parse(raw),fields=new Map(),listeners=new Map();
const ids=['layaRuleId','layaRuleInstruction','layaRuleDirection','layaRuleTarget',
'layaRuleBlockSamples','layaRulePermitSamples','layaRuleConfirmed','layaRuleTest','activateLayaRule','closeLayaRule'];
function element(id='') {return {id,value:'',checked:false,disabled:false,hidden:false,dataset:{},children:[],textContent:'',events:new Map(),
 replaceChildren(...items){this.children=items},append(...items){this.children.push(...items)},
 querySelectorAll(selector){return ids.filter(name=>!selector.includes('button')?!['layaRuleTest','activateLayaRule','closeLayaRule'].includes(name):true).map(get)},
 addEventListener(name,fn){this.events.set(name,fn)},showModal(){this.open=true},close(){this.open=false}};}
function get(id){if(!fields.has(id))fields.set(id,element(id));return fields.get(id)}
const context=vm.createContext({JSON,Object,Array,Set,Error,Date,TextEncoder,assert,console,
 setInterval(){return 1},document:{addEventListener(name,fn){listeners.set(name,[...(listeners.get(name)||[]),fn])}},
 $:get,el:(tag,text='',className='')=>Object.assign(element(),{textContent:text,className}),
 clonePolicy:value=>JSON.parse(JSON.stringify(value)),admin:'owner',openConnection(){},refresh:async()=>{},listeners});
vm.runInContext(scripts.review,context);vm.runInContext(scripts.regressions,context);
await vm.runInContext(`(async()=>{
 const status={policy:{version:7,semantic:{provider:'laya',rules:[]}},feed:{version:3,signatures:[]},configuration:{management_writable:true}};
 let posts=[],mode='pass',pendingResolve;
 const saved={schema_version:1,suite_digest:'digest',policy_version:7,suites:[]};
 function review(body) {
   const cases=body.cases.map(item=>({...item,rule_id:body.rule.id,
     before:{status:'evaluated',decision:'no_semantic_block',latency_ms:2},
     after:{status:'evaluated',decision:item.expected,latency_ms:3},passed:true}));
   if(mode==='fail') {cases[0].passed=false;cases[0].after.decision='no_semantic_block';}
   if(mode==='inherited') cases.push({...cases[0],id:'prior',rule_id:'other',passed:false});
   if(mode==='missing') cases.pop();
   return {scope:'semantic_only',review_id:mode==='pass'?'review-token':null,base_version:7,candidate_version:8,feed_version:3,
     expires_at:'2099-01-01T00:00:00Z',model:'fixture',yaml_diff:'--- active\\n+++ candidate',cases,tests_passed:mode==='pass',warnings:[],missing_rules:[]};
 }
 api=async(path,token,body,method)=>{
   if(method==='PUT')throw Error('Generic policy writes forbidden for reviewed semantic rules');
   if(path==='/api/admin/status')return status;
   if(path==='/api/admin/semantic/tests')return saved;
   posts.push({path,token,body});
   if(path.endsWith('/review')){
     if(mode==='error')throw Error('Unavailable');
     if(mode==='pending')return await new Promise(resolve=>pendingResolve=()=>resolve(review(body)));
     return review(body);
   }
   if(path.endsWith('/activate'))return {policy_version:8,feed_version:3,tests_saved:false};
   throw Error('Unexpected path '+path);
 };
 await openLayaRule();$('layaRuleId').value='advice';$('layaRuleInstruction').value='Block private advice';
 $('layaRuleBlockSamples').value='buy this';$('layaRulePermitSamples').value='education';
 assert.equal(semanticCases().length,8);assert.equal(new Set(semanticCases().map(x=>x.direction+'/'+x.target)).size,4);
 $('layaRuleBlockSamples').value='one\\ntwo\\nthree\\nfour';
 await $('layaRuleTest').onclick();assert.equal(posts.length,0);assert.match($('layaRuleMessage').textContent,/16 scoped/);
 $('layaRuleBlockSamples').value='buy this';mode='fail';await $('layaRuleTest').onclick();
 $('layaRuleConfirmed').checked=true;$('layaRuleConfirmed').onchange();assert.equal($('activateLayaRule').disabled,true);assert.equal(layaRulePreview,null);
 mode='inherited';await $('layaRuleTest').onclick();assert.equal(layaRulePreview,null);
 mode='missing';await $('layaRuleTest').onclick();assert.equal(layaRulePreview,null);assert.match($('layaRuleMessage').textContent,/does not match/);
 mode='error';await $('layaRuleTest').onclick();assert.equal($('layaRuleBlockSamples').value,'buy this');assert.equal(layaRulePreview,null);
 mode='pass';await $('layaRuleTest').onclick();assert.ok(layaRulePreview);assert.equal($('activateLayaRule').disabled,true);
 $('layaRuleConfirmed').checked=true;$('layaRuleConfirmed').onchange();assert.equal($('activateLayaRule').disabled,false);
 $('layaRulePermitSamples').value='updated';$('layaRulePermitSamples').events.get('input')();assert.equal(layaRulePreview,null);
 await $('layaRuleTest').onclick();listeners.get('fastfence:status').forEach(fn=>fn({detail:{...status,policy:{...status.policy,version:8}}}));assert.equal(layaRulePreview,null);
 mode='pending';let pending=$('layaRuleTest').onclick();await Promise.resolve();await Promise.resolve();
 const before=posts.length;await $('layaRuleTest').onclick();assert.equal(posts.length,before);
 $('layaRuleInstruction').value='Changed while pending';invalidateLayaRuleTest();mode='pass';pendingResolve();await pending;assert.equal(layaRulePreview,null);
 await $('layaRuleTest').onclick();$('layaRuleConfirmed').checked=true;
 await $('activateLayaRule').onclick();assert.equal(posts.at(-1).path,'/api/admin/semantic/activate');assert.equal(posts.at(-1).body.confirmed,true);
 assert.equal(posts.at(-1).body.review_id,'review-token');assert.match($('layaRuleMessage').textContent,/already active/);assert.match($('layaRuleMessage').textContent,/saving.*failed/);
 await openLayaRule();$('layaRuleId').value='advice';$('layaRuleInstruction').value='Do not leak';$('layaRuleBlockSamples').value='deny';$('layaRulePermitSamples').value='permit';
 mode='pending';pending=$('layaRuleTest').onclick();await Promise.resolve();await Promise.resolve();
 admin='other';listeners.get('fastfence:identity').forEach(fn=>fn());mode='pass';pendingResolve();await pending;
 assert.equal(layaRulePreview,null);assert.equal($('layaRuleInstruction').value,'');assert.equal($('layaRuleDialog').open,false);
 admin='owner';const rule={id:'advice',instruction:'Keep scopes',direction:'both',target:'all'};status.policy.semantic.rules=[rule];
 saved.suites=[{rule,status:'policy_changed',cases:[{id:'saved',rule_id:'advice',text:'exact saved text',direction:'output',target:'tool',expected:'blocked'}]}];
 await openLayaRule(rule);assert.equal(semanticCases().length,1);assert.equal(semanticCases()[0].direction,'output');assert.equal(semanticCases()[0].target,'tool');
 assert.equal($('layaRuleNewCases').hidden,true);assert.equal($('layaRuleId').disabled,true);
 $('layaRuleSavedCases').children.at(-1).onclick();assert.equal(layaRuleSavedCases,null);assert.equal($('layaRuleNewCases').hidden,false);
})()`,context);
"""


def test_semantic_review_gate_rejects_failed_stale_and_unconfirmed_changes():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Browser lifecycle fixture requires Node.js")
    result = subprocess.run(
        [node, "--input-type=module", "-e", HARNESS],
        input=json.dumps(
            {
                "review": (WEB / "semantic-review.js").read_text(),
                "regressions": (WEB / "semantic-regressions.js").read_text(),
            }
        ),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
