#!/usr/bin/env python3
"""Validate exported SIR-1. This is not an IR deserializer/compiler input mode."""
import argparse,json
from pathlib import Path
OPS={'+','-','*','/','%','==','!=','<','>','<=','>=','and','or'}
def validate(m):
 def require(ok,message):
  if not ok:raise ValueError(message)
 require(m['format']=='Sovren SIR' and m['version']==1,'unsupported SIR version')
 require(m['overflow'] in ['trap','wrap'],'overflow policy')
 fs=m['functions'];ns=m['nodes'];ss=m['statements'];rows=m['rows']
 require(fs and len({f['name'] for f in fs})==len(fs),'duplicate or missing functions')
 require(sum(f['name']=='main' for f in fs)==1,'main required')
 for i,f in enumerate(fs):
  require(f['id']==i,'function IDs must be dense');names=f['parameters']+f['locals']
  require(len(names)==len(set(names)),'duplicate local symbol')
  require(0<=f['first_row']<len(rows),'source row')
 for i,n in enumerate(ns):
  require(n['id']==i and n['type']=='i64','node ID/type');f=n['function']
  require(type(f)==int and 0<=f<len(fs) and n['line']>0,'node location')
  for child in ([n['left'],n['right']] if n['kind']=='binary' else n['arguments']):
   require(type(child)==int and 0<=child<i and ns[child]['function']==f,'invalid DAG edge')
  kind=n['kind'];text=n['text']
  if kind in ['integer','negative-integer']:require(text.isascii() and text.isdecimal() and int(text)<2**64,'integer range')
  elif kind=='binary':require(text in OPS,'binary opcode')
  elif kind=='call':
   target=n['symbol'];require(type(target)==int and 0<=target<len(fs),'call target')
   require(fs[target]['name']==text and len(fs[target]['parameters'])==len(n['arguments']),'call binding/arity')
  elif kind=='local':
   names=fs[f]['parameters']+fs[f]['locals'];symbol=n['symbol']
   require(type(symbol)==int and 0<=symbol<len(names) and names[symbol]==text,'local binding')
  else:raise ValueError('unknown expression '+kind)
  if kind!='binary':require(n['left']==n['right']==-1,'unexpected binary operands')
  if kind!='call':require(n['arguments']==[],'unexpected arguments')
 for f,line,node in m['expression_sites']:
  require(0<=node<len(ns) and ns[node]['function']==f and ns[node]['line']==line,'expression site')
 last_function=-1;stack=[];last_closed=None;seen=set()
 for s in ss:
  f=s['function'];kind=s['kind'];root=s['expression'];aux=s['auxiliary']
  require(type(f)==int and last_function<=f<len(fs),'statement function order')
  if f!=last_function:require(not stack,'unclosed previous function');last_closed=None
  last_function=f;seen.add(f)
  if root!=-1:require(0<=root<len(ns) and ns[root]['function']==f,'statement expression')
  if kind in ['if','while','else']:
   if kind=='else':require(last_closed=='if' and root==-1,'unmatched else')
   else:require(root>=0,'missing condition')
   stack.append(kind);last_closed=None
  elif kind=='end':require(bool(stack),'extra end');last_closed=stack.pop()
  else:
   last_closed=None
   if kind=='break':require('while' in stack,'break outside loop')
   elif kind=='assign':
    names=fs[f]['parameters']+fs[f]['locals'];require(0<=aux<len(names) and names[aux]==s['text'] and root>=0,'assignment binding')
   elif kind in ['print-i64','return','expression']:require(root>=0,'missing expression')
   elif kind=='print-text':
    text=s['text'];require(len(text)>=2 and text[0] in "'\"" and text[0]==text[-1],'text literal')
    require(aux==-1 or 0<=aux<len(ns) and ns[aux]['kind']=='integer' and ns[aux]['function']==f,'repeat count')
   elif kind=='return-default':require(root==-1 and not stack,'default return')
   else:raise ValueError('unknown statement '+kind)
 require(not stack and seen==set(range(len(fs))),'incomplete function body')
 return {'functions':len(fs),'nodes':len(ns),'statements':len(ss)}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('file',type=Path);a=p.parse_args()
 try:print(json.dumps(validate(json.loads(a.file.read_text()))))
 except (KeyError,TypeError,ValueError,IndexError) as e:p.exit(1,'Invalid SIR: '+str(e)+'\n')
