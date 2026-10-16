const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const script=fs.readFileSync('deployment/shared-entry.js','utf8');
function redirect(url){let destination=null;vm.runInNewContext(script,{URL,location:{href:url,replace:u=>destination=u}});return destination;}
const host='https://s4w66hdi1zteriq8oyfb8wzm.khdp.net';
assert.equal(redirect(host+'/proxy/8006/?lang=ko&hospital=B&ward=B-SICU&token=secret&case_id=CASE-001'),'https://icu-ward-board-20261016.kanghoun.chatgpt.site/?lang=ko&hospital=B&ward=B-SICU');
assert.equal(redirect(host+'/proxy/8006/index.html?lang=en&hospital=C'),'https://icu-ward-board-20261016.kanghoun.chatgpt.site/?lang=en&hospital=C');
for(const url of [host+'/proxy/8007/',host+'/proxy/8006/?view=private','http://127.0.0.1:8000/','https://icu-ward-board-20261016.kanghoun.chatgpt.site/'])assert.equal(redirect(url),null);
assert.equal(redirect(host+'/proxy/8006/?hospital=evil&lang=fr&nurse=patient-name'),'https://icu-ward-board-20261016.kanghoun.chatgpt.site/');
console.log('Canonical entry: preference preservation, no secret forwarding, no loops, private tools retained.');
