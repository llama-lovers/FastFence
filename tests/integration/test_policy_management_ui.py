"""Execute policy management browser logic, including stale-write prevention."""

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
const scripts=JSON.parse(raw), fields=new Map(), listeners=new Map(), calls=[];
function element(id='') { return {id,value:'',checked:false,disabled:false,dataset:{},children:[],
 classList:{add(){},remove(){},toggle(){}},replaceChildren(...items){this.children=items},
 append(...items){this.children.push(...items)},querySelectorAll(){return []},
 addEventListener(){},showModal(){},close(){},textContent:''}; }
function get(id){if(!fields.has(id))fields.set(id,element(id));return fields.get(id)}
const context=vm.createContext({console,JSON,Object,Array,Set,Error,Boolean,String,
 document:{addEventListener(name,fn){listeners.set(name,[...(listeners.get(name)||[]),fn])}},
 $:get,el:(tag,text='')=>Object.assign(element(),{textContent:text}),
 admin:'owner',active:null,openConnection(){},refresh:async()=>{},
 invalidateStudioProposal(){},listeners,calls,assert});
vm.runInContext(scripts.rules,context);vm.runInContext(scripts.manager,context);
await vm.runInContext(`(async()=>{
 const policy={version:7,description:'Old',privacy:{enabled:true,input:'block',output:'redact',detector_actions:{}},
 anonymization:{enabled:false,mode:'irreversible',rules:[]},semantic:{provider:'disabled',model:'qwen3:4b',threshold:0.7,timeout_ms:30000,scan_output:true},signatures_enabled:true,text_rules:[]};
 const status={policy,configuration:{management_writable:true}};
 active=policy;api=async(path,token,body,method)=>{calls.push({path,token,body,method});return status};
 await openPolicyManager();$('policyDescription').value='New';$('policyReview').onclick();
 assert.equal(policyCandidate.version,8);assert.equal($('savePolicy').disabled,true);
 $('policyConfirm').checked=true;$('policyConfirm').onchange();assert.equal($('savePolicy').disabled,false);
 invalidatePolicyReview();assert.equal(policyCandidate,null);assert.equal($('savePolicy').disabled,true);
 $('policyReview').onclick();$('policyConfirm').checked=true;
 api=async(path,token,body,method)=>{calls.push({path,method});if(method==='PUT')throw Error('must not write');return {...status,policy:{...policy,version:8}}};
 await $('savePolicy').onclick();assert.match($('policyMessage').textContent,/active policy changed/);
 assert.equal(calls.filter(call=>call.method==='PUT').length,0);
 assert.equal($('policyDescription').value,'New');
 api=async()=>status;await openPolicyManager();$('policyDescription').value='Retained';$('policyReview').onclick();
 $('policyConfirm').checked=true;admin='different';await $('savePolicy').onclick();
 assert.match($('policyMessage').textContent,/identity changed/);assert.equal($('policyDescription').value,'Retained');
 admin='owner';api=async()=>({...status,configuration:{management_writable:false}});
 await openPolicyManager();assert.equal($('policyReview').disabled,true);assert.match($('policyMessage').textContent,/Read-only/);
 api=async()=>status;await openPolicyManager();$('policyJsonMode').checked=true;
 $('policyJson').value=JSON.stringify({...policy,version:999,description:'Advanced'});$('policyReview').onclick();
 assert.equal(policyCandidate.version,8);$('policyConfirm').checked=true;
 api=async(path,token,body,method)=>{if(method==='PUT')throw Error('invalid candidate');return status};
 await $('savePolicy').onclick();assert.equal(policyCandidate,null);assert.match($('policyJson').value,/Advanced/);
 api=async()=>status;await openTextRule();assert.equal($('textRuleValue').value,'');
 $('textRuleId').value='custom';$('textRuleValue').value='blocked';$('textRuleSamples').value='hello';
 api=async()=>({rule:textRuleDraft(),matches:[false]});await $('previewTextRule').onclick();
 assert.equal($('activateTextRule').disabled,true);$('textRuleReviewed').checked=true;$('textRuleReviewed').onchange();
 assert.equal($('activateTextRule').disabled,false);listeners.get('fastfence:identity').forEach(fn=>fn());
 assert.equal(previewedRule,null);assert.equal(ruleBase,null);assert.equal($('activateTextRule').disabled,true);
 api=async()=>status;await openLayaRule();
 $('layaRuleId').value='financial-advice';$('layaRuleInstruction').value='Block personalized investment recommendations';
 $('layaRuleDirection').value='input';$('layaRuleTarget').value='model';$('layaRuleSample').value='Buy this stock';
 api=async(path,token,body)=>({decision:'blocked',semantic_score:1,provider:'laya',model:'qwen3:4b',rule_applied:true,base_version:7,latency_ms:20});
 await $('layaRuleTest').onclick();assert.equal($('reviewLayaRule').disabled,false);
 assert.equal(layaRulePreview.instruction,'Block personalized investment recommendations');
 invalidateLayaRuleTest();assert.equal($('reviewLayaRule').disabled,true);
 await $('layaRuleTest').onclick();api=async()=>status;await $('reviewLayaRule').onclick();
 assert.equal($('policyJsonMode').checked,false);assert.equal($('policyAdvanced').open,false);
 $('policyReview').onclick();assert.equal(policyCandidate.semantic.rules[0].id,'financial-advice');
 assert.equal(policyCandidate.semantic.provider,'laya');assert.equal(policyCandidate.semantic.timeout_ms,30000);
 assert.equal(policyCandidate.version,8);

})()`,context);
"""


def test_policy_review_rejects_stale_identity_and_preserves_failed_edits():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Browser lifecycle fixture requires Node.js")
    result = subprocess.run(
        [node, "--input-type=module", "-e", HARNESS],
        input=json.dumps(
            {
                "rules": (WEB / "rules.js").read_text(),
                "manager": (WEB / "policy-manager.js").read_text(),
            }
        ),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
