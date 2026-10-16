"""Loopback-only CXR research inference; consumes hash-verified private previews."""
import hashlib,json,re,threading,os
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

MODEL='StanfordAIMI/CheXagent-2-3b'
REVISION='8f19b53a2eceda4c33b0acec6c81fbc293ad80d0'
PROMPT='Describe the visible findings in this chest X-ray. Describe devices only when visible. Do not invent a comparison study or patient history. This is a research image review, not a diagnosis or treatment recommendation.'

def main():
 import argparse,torch
 from transformers import AutoTokenizer,AutoModelForCausalLM
 p=argparse.ArgumentParser();p.add_argument('--images',required=True);p.add_argument('--port',type=int,default=8016);a=p.parse_args()
 root=Path(a.images).resolve()
 print('LOADING_MODEL',MODEL,flush=True)
 tokenizer=AutoTokenizer.from_pretrained(MODEL,revision=REVISION,trust_remote_code=True)
 model=AutoModelForCausalLM.from_pretrained(MODEL,revision=REVISION,trust_remote_code=True,torch_dtype=torch.bfloat16,device_map='auto').eval()
 lock=threading.Lock();cache={}
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def reply(self,code,data):
   raw=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  def do_GET(self):
   if self.path=='/health':return self.reply(200,{'ready':True,'model':MODEL})
   self.reply(404,{'error':'Not found'})
  def do_POST(self):
   if self.path!='/review':return self.reply(404,{'error':'Not found'})
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 0<n<2048:raise ValueError()
    body=json.loads(self.rfile.read(n));key=body['image_id']
    if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{64}',key):raise ValueError()
    file=next((d/(key+'.png') for d in (root/'simulation',root) if (d/(key+'.png')).is_file()),None)
    if file is None or file.stat().st_size>12*1024*1024:raise ValueError()
    data=file.read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(data).hexdigest()!=key:raise ValueError()
   except (ValueError,KeyError,OSError,TypeError):return self.reply(400,{'error':'Invalid preview'})
   if not lock.acquire(False):return self.reply(429,{'error':'Model busy'})
   try:
    if key not in cache:
     query=tokenizer.from_list_format([{'image':str(file)},{'text':PROMPT}])
     conv=[{'from':'system','value':'You are a helpful assistant.'},{'from':'human','value':query}]
     ids=tokenizer.apply_chat_template(conv,add_generation_prompt=True,return_tensors='pt').to('cuda')
     with torch.inference_mode():out=model.generate(ids,do_sample=False,num_beams=1,use_cache=True,max_new_tokens=384)[0]
     cache[key]=tokenizer.decode(out[ids.size(1):],skip_special_tokens=True)
    self.reply(200,{'model':MODEL,'revision':REVISION,'image_id':key,'findings':cache[key],'scope':'image_only','official_report':False})
   except Exception as e:
    print('INFERENCE_FAILED',type(e).__name__,flush=True);self.reply(503,{'error':'Inference failed'})
   finally:lock.release()
 print('READY',flush=True);ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
if __name__=='__main__':main()
