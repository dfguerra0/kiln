from __future__ import annotations
import csv,io,json,random,urllib.request,datetime as dt
from dataclasses import dataclass,asdict
from pathlib import Path
URL='https://raw.githubusercontent.com/getdata-finance/xauusd-15m-ohlcv-metals-historical-data/sample-2026-07-31/XAUUSD_15m.csv';OUT=Path('research/output');OUT.mkdir(parents=True,exist_ok=True);SEED=20260909
@dataclass(frozen=True)
class Cfg:pivot:int;hour:int;span:int;local:int;context:int;arm:int;fill:int;hold:int;leg:int;eff:float;target:float;retrace:float;bias:bool;ctx:bool;legf:bool
def load():
 txt=urllib.request.urlopen(URL,timeout=60).read().decode();a=[]
 for r in csv.DictReader(io.StringIO(txt)):
  try:
   t=int(dt.datetime.fromisoformat(r['datetime']).timestamp()*1000);o,h,l,c=map(float,(r['open'],r['high'],r['low'],r['close']))
   if h>=max(o,c) and l<=min(o,c):a.append((t,o,h,l,c))
  except:pass
 return sorted(a)
def piv(b,p):
 n=len(b);hi=[None]*n;lo=[None]*n
 for i in range(2*p,n):
  j=i-p;v=b[j][2]
  if all(v>b[j-k][2] and v>b[j+k][2] for k in range(1,p+1)):hi[i]=(j,v)
  v=b[j][3]
  if all(v<b[j-k][3] and v<b[j+k][3] for k in range(1,p+1)):lo[i]=(j,v)
 return hi,lo
def hmap(b):
 H=3600000;m={}
 for t,o,h,l,c in b:
  k=t//H*H
  if k not in m:m[k]=[o,h,l,c]
  else:m[k][1]=max(m[k][1],h);m[k][2]=min(m[k][2],l);m[k][3]=c
 return m
def ins(t,h,s):return any(dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).hour==(h+k)%24 for k in range(s))
def legok(b,i,d,c):
 if i<c.leg:return False
 path=sum(abs(b[k][4]-b[k-1][4]) for k in range(i-c.leg+1,i+1));net=d*(b[i-c.leg][4]-b[i][4]);return path>0 and net/path>=c.eff
def run(b,start,end,c,pc,hm):
 ph,pl=pc[c.pivot];H=3600000;hi=lo=None;hij=loj=-10**9;phase=side=arm_i=sig_i=fill_i=0;br=sw=entry=stop=target=0.;active=None;tr=[];f={k:0 for k in('session','sweeps','context','bias','leg','armed','breaks','plans','fills','resolved','ambiguous','censored','missed')}
 for i,x in enumerate(b):
  t,o,h,l,cl=x
  if t>=end:break
  ap=t>=start;s=ins(t,c.hour,c.span)
  if ap and s:f['session']+=1
  ready=hi is not None and lo is not None and i-hij<=c.local and i-loj<=c.local;sl=s and ready and loj<hij and l<lo;ss=s and ready and hij<loj and h>hi
  if ap and(sl or ss):f['sweeps']+=1
  hk=t//H*H;p1=hm.get(hk-H);p4=hm.get(hk-4*H);bias=0 if not(p1 and p4) else(1 if p1[3]>p4[3] else -1 if p1[3]<p4[3] else 0);rlo=rhi=False
  if p1:
   for q in range(max(0,i-c.context),i):rlo|=b[q][3]<p1[2];rhi|=b[q][2]>p1[1]
  ctxp=(sl and(not c.ctx or rlo))or(ss and(not c.ctx or rhi));bp=(sl and(not c.bias or bias==1))or(ss and(not c.bias or bias==-1));lpL=(not c.legf)or legok(b,i,1,c);lpS=(not c.legf)or legok(b,i,-1,c);lg=(sl and lpL)or(ss and lpS)
  if ap and ctxp:f['context']+=1
  if ap and bp:f['bias']+=1
  if ap and lg:f['leg']+=1
  if phase==0:
   L=sl and(not c.ctx or rlo)and(not c.bias or bias==1)and lpL;S=ss and(not c.ctx or rhi)and(not c.bias or bias==-1)and lpS
   if L or S:side=1 if L else -1;phase=1;arm_i=i;br=hi if side==1 else lo;sw=l if side==1 else h;f['armed']+=int(ap)
  elif phase==1:
   sw=min(sw,l)if side==1 else max(sw,h)
   if i-arm_i>c.arm or not s:phase=0
   elif(side==1 and cl>br)or(side==-1 and cl<br):
    f['breaks']+=int(ap);imp=h if side==1 else l;entry=sw+c.retrace*(imp-sw);stop=sw;risk=side*(entry-stop)
    if risk>.01:target=entry+side*risk*c.target;sig_i=i;phase=2;active={'signal':t,'side':side,'entry':entry,'stop':stop,'target':target,'r':c.target,'fill':None,'exit':None,'outcome':'pending'};f['plans']+=int(ap)
    else:phase=0
  elif phase==2 and i>sig_i:
   if i-sig_i>c.fill or not s:phase=0;active=None
   else:
    if side==1:he=l<=entry;hs=l<=stop;ht=h>=target
    else:he=h>=entry;hs=h>=stop;ht=l<=target
    if ht and not he:f['missed']+=int(ap);phase=0;active=None
    elif he:
     f['fills']+=int(ap);active['fill']=t;fill_i=i
     if hs or ht:active['exit']=t;active['outcome']='ambiguous';tr.append(active);f['ambiguous']+=int(ap);phase=0;active=None
     else:phase=3
  elif phase==3 and i>fill_i:
   hs=l<=stop if side==1 else h>=stop;ht=h>=target if side==1 else l<=target
   if hs or ht:
    active['exit']=t
    if hs and ht:active['outcome']='ambiguous';f['ambiguous']+=int(ap)
    elif ht:active['outcome']='win';f['resolved']+=int(ap)
    else:active['outcome']='loss';f['resolved']+=int(ap)
    tr.append(active);phase=0;active=None
   elif i-fill_i>c.hold:active['exit']=t;active['outcome']='censored';tr.append(active);f['censored']+=int(ap);phase=0;active=None
  if ph[i]:hij,hi=ph[i]
  if pl[i]:loj,lo=pl[i]
 return[z for z in tr if start<=z['signal']<end],f
def ars(tr,bps):
 a=[]
 for z in tr:
  if z['outcome']not in('win','loss'):continue
  gross=z['r']if z['outcome']=='win'else-1.;risk=abs(z['entry']-z['stop']);a.append(gross-(2*z['entry']*(bps/10000))/risk if risk else -99)
 return a
def met(a):
 eq=pk=dd=gw=gl=0.;w=0
 for r in a:eq+=r;pk=max(pk,eq);dd=max(dd,pk-eq);gw+=max(r,0);gl+=max(-r,0);w+=r>0
 return{'trades':len(a),'wins':w,'win_rate':w/len(a)if a else None,'netR':eq,'avgR':eq/len(a)if a else None,'pf':gw/gl if gl else None,'maxDD_R':dd}
def score(tr,n):
 m=met(ars(tr,2));return -1e9 if m['trades']<n else m['netR']-.75*m['maxDD_R']+.4*min(m['pf']or 0,4)+(m['win_rate']or 0)
def cfgs(n=4000):
 r=random.Random(SEED);S=set();a=[];V={'p':[1,2,3,4],'sp':[1,2,3,4,6],'lo':[2,3,4,6,8,12,16],'cx':[2,4,6,8,12,16],'af':[1,2,3,4,6,8],'ho':[4,8,12,16,24,32],'lg':[1,2,3,4,6,8,12],'ef':[.05,.15,.25,.35,.45,.55,.65],'tg':[.75,1,1.25,1.5,2,2.5,3,3.5],'rt':[.35,.5,.618,.7]}
 while len(a)<n:
  c=Cfg(r.choice(V['p']),r.randrange(24),r.choice(V['sp']),r.choice(V['lo']),r.choice(V['cx']),r.choice(V['af']),r.choice(V['af']),r.choice(V['ho']),r.choice(V['lg']),r.choice(V['ef']),r.choice(V['tg']),r.choice(V['rt']),bool(r.getrandbits(1)),bool(r.getrandbits(1)),bool(r.getrandbits(1)))
  if c not in S:S.add(c);a.append(c)
 return a
def mc(a,N=20000,block=5):
 if not a:return None
 r=random.Random(SEED+99);F=[];D=[];n=len(a)
 for _ in range(N):
  q=[]
  while len(q)<n:
   s=r.randrange(n);q.extend(a[(s+j)%n]for j in range(block))
  eq=pk=dd=0.
  for x in q[:n]:eq+=x;pk=max(pk,eq);dd=max(dd,pk-eq)
  F.append(eq);D.append(dd)
 F.sort();D.sort();Q=lambda x,p:x[int((len(x)-1)*p)];return{'iterations':N,'block':block,'prob_profit':sum(x>0 for x in F)/N,'finalR_p05':Q(F,.05),'finalR_median':Q(F,.5),'finalR_p95':Q(F,.95),'maxDD_p50':Q(D,.5),'maxDD_p95':Q(D,.95),'maxDD_p99':Q(D,.99)}
def main():
 b=load();assert len(b)>10000;pc={p:piv(b,p)for p in(1,2,3,4)};hm=hmap(b);n=len(b);i1=int(n*.6);i2=int(n*.8);st=b[0][0];s1=b[i1][0];s2=b[i2][0];en=b[-1][0]+900000;R=[]
 for c in cfgs():
  t,_=run(b,st,s1,c,pc,hm);R.append((score(t,10),c,t))
 R.sort(key=lambda x:x[0],reverse=True);V=[]
 for sc,c,t in R[:120]:v,_=run(b,s1,s2,c,pc,hm);V.append((score(v,5),c,t,v))
 V.sort(key=lambda x:x[0],reverse=True);Q=[x for x in V if met(ars(x[2],2))['netR']>0 and met(ars(x[3],2))['netR']>0 and len(ars(x[3],2))>=5];_,c,tt,vv=(Q or V)[0];hh,hf=run(b,s2,en,c,pc,hm);ff,fff=run(b,st,en,c,pc,hm);pack=lambda t:{str(k):met(ars(t,k))for k in(0,2,5,10)};res={'source':URL,'bars':n,'range':{'from':st,'train_end':s1,'validation_end':s2,'to':en},'split':'60/20/20 chronological','holdout_used_for_selection':False,'configs':4000,'selected':asdict(c),'qualified_train_validation':bool(Q),'train':pack(tt),'validation':pack(vv),'holdout':pack(hh),'full':pack(ff),'holdout_funnel':hf,'full_funnel':fff,'monte_carlo':{str(k):mc(ars(ff,k))for k in(0,2,5,10)},'top_validation':[{'score':s,'cfg':asdict(cc),'train':pack(t),'validation':pack(v)}for s,cc,t,v in V[:20]]};(OUT/'results.json').write_text(json.dumps(res,indent=2));
 with(OUT/'selected_trades.csv').open('w',newline='')as f:w=csv.DictWriter(f,fieldnames=['signal','fill','exit','side','entry','stop','target','r','outcome']);w.writeheader();w.writerows(ff)
 print('CBR_RESULT '+json.dumps({'bars':n,'selected':asdict(c),'qualified':bool(Q),'train':res['train']['2'],'validation':res['validation']['2'],'holdout':res['holdout']['2'],'full':res['full']['2'],'mc2':res['monte_carlo']['2']}))
if __name__=='__main__':main()
