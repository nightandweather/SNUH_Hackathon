// Dependency-free orchestration checks. Real browser layout is checked separately.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
class Element {
 constructor(){this.children=[];this.nodes={};this.value='';this.disabled=false;this.classList={toggle(){}};this.scrollHeight=20;}
 querySelector(s){return this.nodes[s]??=new Element();}
 append(e){this.children.push(e);}
 appendChild(e){this.append(e);}
 replaceChildren(){this.children=[];}
 remove(){this.removed=true;}
 focus(){}
 after(e){this.afterElement=e;}
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup({images=[],badContext=false}={}){
 const calls=[],document={createElement:()=>new Element()},parent=new Element();
 const facts=[{kind:'vital',name:'hr',value:90,unit:'bpm'}];
 const context={facts,context_hash:'bound-hash',as_of_minute:10};
 const imageResponse={case_id:'TEST',row_index:0,image_id:'image-a',context_hash:'bound-hash',image_input:true,model:'test-vision',availability_known:true,review:{summary:'Image review',image_quality:'Preview',visible_findings:['Finding'],uncertainties:['Uncertain'],clinician_review:['Review'],nursing_focus:['Observe']}};
 const fetch=async(url,options={})=>{
  calls.push({url,body:options.body&&JSON.parse(options.body)});
  let result=url.startsWith('api/case-images')?{images}:url==='api/discussion/open'?{session_id:'session',context,role_prompts:{agent:'test'}}:url==='api/cxr-review'?{...imageResponse,...(badContext?{case_id:'OTHER'}:{})}:{case_id:'TEST',row_index:0,context_hash:'bound-hash',model:'text-model',revision:1,reply:{evidence_ids:[],discussion:'text',questions:[],actions:[],order_review:[],escalation:'',sbar:{},uncertainties:[]},audit:{}};
  return {ok:true,json:async()=>result};
 };
 const sandbox={window:{},document,fetch,AbortController,URLSearchParams,setInterval,clearInterval,Date};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/grounded-chat.js'),'utf8'),sandbox);
 sandbox.window.GroundedChat.mount(parent,{id:'TEST',rows:[{minute:10}]},0,'en');
 const section=parent.querySelector('.record-time-note').afterElement;
 return {section,calls,chat:sandbox.window.GroundedChat};
}
const image={image_id:'image-a',name:'Chest X-ray',modality:'CR',chart_minute:5};
test('unlinked patient shows why CXR cannot be sent',async()=>{
 const {section}=setup();await tick();
 assert.equal(section.querySelector('.cxr-select').disabled,true);
 assert.match(section.querySelector('.cxr-status').textContent,/No linked CXR/);
 assert.match(section.querySelector('.ai-vitals').textContent,/HR 90/);
});
test('linked CXR uses patient/time-bound vision route and renders reply',async()=>{
 const {section,calls}=setup({images:[image]});await tick();
 const selector=section.querySelector('.cxr-select');assert.equal(selector.disabled,false);
 selector.value='image-a';selector.onchange();
 assert.match(section.querySelector('.cxr-preview').children[0].src,/case_id=TEST&row_index=0&image_id=image-a/);
 section.querySelector('textarea').value='What is visible?';await section.querySelector('.send').onclick();
 const call=calls.find(x=>x.url==='api/cxr-review');assert.deepEqual(call.body,{case_id:'TEST',row_index:0,image_id:'image-a',language:'en',question:'What is visible?',compare_chexagent:true});
 assert.equal(calls.some(x=>x.url==='api/discussion/turn'),false);
 assert.match(section.querySelector('.status').textContent,/1 CXR replies/);
 assert.ok(section.querySelector('.transcript').children.some(x=>/Image review/.test(x.innerHTML)));
 assert.equal(section.querySelector('.send').disabled,false);
});
test('mismatched image response is rejected and question restored',async()=>{
 const {section}=setup({images:[image],badContext:true});await tick();
 section.querySelector('.cxr-select').value='image-a';section.querySelector('textarea').value='Review';
 await section.querySelector('.send').onclick();assert.match(section.querySelector('.status').textContent,/context mismatch/);
 assert.equal(section.querySelector('textarea').value,'Review');
});
test('default selection retains text conversation endpoint',async()=>{
 const {section,calls}=setup({images:[image]});await tick();section.querySelector('textarea').value='Check patient';
 await section.querySelector('.send').onclick();assert.ok(calls.some(x=>x.url==='api/discussion/turn'));assert.equal(calls.some(x=>x.url==='api/cxr-review'),false);
});

test('random simulation CXR is previewed and labeled without a fake timestamp',async()=>{
 const {section}=setup({images:[{...image,linkage:'random_simulation',chart_minute:null}]});await tick();
 assert.equal(section.querySelector('.cxr-select').value,'image-a');
 assert.match(section.querySelector('.cxr-status').textContent,/Not this patient/);
 assert.ok(section.querySelector('.cxr-preview').children.length);
 assert.doesNotMatch(section.querySelector('.cxr-select').children[0].textContent,/null/);
});
