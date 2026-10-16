/* The KHDP presentation entry uses the canonical published dashboard.
 * Private source-record/LLM tools remain behind KHDP authentication.
 * Only navigation preferences are carried across; never credentials or patient IDs.
 */
(()=>{
 const targetOrigin='https://icu-ward-board-20261016.kanghoun.chatgpt.site';
 const here=new URL(location.href);
 if(here.hostname!=='s4w66hdi1zteriq8oyfb8wzm.khdp.net'||!/^\/proxy\/8006\/(?:index\.html)?$/.test(here.pathname))return;
 if(here.searchParams.get('view')==='private')return;
 const target=new URL('/',targetOrigin);
 const allowed={lang:/^(ko|en)$/,hospital:/^[ABC]$/,ward:/^[ABC]-(?:SICU|CSICU|NSICU|TSICU)$/,nurse:/^[ABC]-(?:SICU|CSICU|NSICU|TSICU)-(?:[1-4]|C)$/};
 for(const [key,pattern] of Object.entries(allowed)){const value=here.searchParams.get(key);if(value&&pattern.test(value))target.searchParams.set(key,value);}
 location.replace(target.href);
})();
