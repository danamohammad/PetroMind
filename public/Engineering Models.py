"""PetroMind engineering models. SI internally where indicated; no control actions.
References and applicability are documented in Engineering Methods.html.
"""
import json, math
from datetime import datetime, timezone
import numpy as np
from scipy.optimize import least_squares, brentq
from scipy.interpolate import PchipInterpolator

def number(v,name,lo=-math.inf,hi=math.inf):
    if v is None or isinstance(v,bool) or str(v).strip()=='': raise ValueError(name+' is required')
    x=float(v)
    if not math.isfinite(x) or not lo<=x<=hi: raise ValueError(f'{name} must be between {lo} and {hi}')
    return x

def values(p,spec): return {k:number(p.get(k),k,*bounds) for k,bounds in spec.items()}
def metric(y,p):
    a=np.array(y,float);b=np.array(p,float);e=b-a
    return {'count':len(a),'RMSE':float(np.sqrt(np.mean(e*e))),'MAE':float(np.mean(abs(e))),'bias':float(np.mean(e))}
def diagnostics(fit,names):
    norms=np.linalg.norm(fit.jac,axis=0);scaled=fit.jac/np.maximum(norms,1e-30);s=np.linalg.svd(scaled,compute_uv=False);rank=int(np.sum(s>s[0]*1e-8)) if len(s) else 0
    return {'converged':bool(fit.success),'rank':rank,'parameterCount':len(names),'boundHits':[n for n,a in zip(names,fit.active_mask) if a!=0],'eligible':bool(fit.success and rank==len(names) and not np.any(fit.active_mask))}
def timestamp(s):
    s=str(s);d=datetime.fromisoformat(s.replace('Z','+00:00'))
    if d.tzinfo is None:
        if len(s)!=10: raise ValueError('Timestamps must include Z or a UTC offset')
        d=d.replace(tzinfo=timezone.utc)
    return d.timestamp()
def time_rows(rows,minrows=8):
    if not minrows<=len(rows)<=10000: raise ValueError(f'Use {minrows} to 10000 observations')
    a=sorted([{**r,'epoch':timestamp(r.get('date',r.get('timestamp','')))} for r in rows],key=lambda r:r['epoch'])
    if len({r['epoch'] for r in a})!=len(a): raise ValueError('Duplicate timestamps: aggregate or correct before fitting')
    for r in a:r['day']=(r['epoch']-a[0]['epoch'])/86400
    return a

def scal(p,rows,action):
    p=values(p,{'swc':(0,.9),'sor':(0,.9),'krwEnd':(.001,1),'kroEnd':(.001,1),'nw':(.1,12),'no':(.1,12),'entry':(.001,1e5),'lam':(.1,12),'muWater':(.01,10000),'muOil':(.01,100000),'length':(.01,1000),'diameter':(.01,100),'poreVolume':(.000001,1e6),'flow':(.000001,1e6),'deltaPressure':(.000001,10000),'coreViscosity':(.001,100000)})
    if p['swc']+p['sor']>=.98:raise ValueError('Swc + Sor must be less than 0.98')
    bulk=math.pi*p['diameter']**2/4*p['length'];phi=p['poreVolume']/bulk
    if not 0<phi<1:raise ValueError('Pore volume must be less than cylindrical bulk volume')
    permeability=(p['flow']/60*1e-6*p['coreViscosity']*.001*p['length']*.01/(math.pi*(p['diameter']*.01)**2/4*p['deltaPressure']*1e5))/9.869233e-16
    def curve(sw,x):
        se=min(1,max(0,(sw-p['swc'])/(1-p['swc']-p['sor'])));drain=(sw-p['swc'])/(1-p['swc'])
        kw=x['krwEnd']*se**x['nw'];ko=x['kroEnd']*(1-se)**x['no'];den=kw/p['muWater']+ko/p['muOil']
        return {'sw':sw,'krw':kw,'kro':ko,'pc':None if drain<=0 else x['entry']*drain**(-1/x['lam']),'waterFractionalFlow':kw/p['muWater']/den if den>0 else None}
    obs=[]
    if len(rows)>250:raise ValueError('Use at most 250 SCAL observations')
    for r in rows:
        sw=number(r.get('sw'),'Water saturation',p['swc'],1-p['sor']);role=r.get('role','training')
        if role not in ['training','validation','reference']:raise ValueError('Invalid measurement role')
        for prop in ['krw','kro','pc']:
            if r.get(prop) not in [None,'']:
                measured=number(r[prop],prop,0,1 if prop!='pc' else 1e7)
                if prop=='pc' and sw<=p['swc']:raise ValueError('Capillary pressure is singular at Swc; use Sw > Swc')
                obs.append({'sw':sw,'property':prop,'measured':measured,'role':role})
    fitinfo=None
    if action=='fit':
        train=[r for r in obs if r['role']=='training'];names=['krwEnd','kroEnd','nw','no','entry','lam'];lower=[.001,.001,.1,.1,.001,.1];upper=[1,1,12,12,1e5,12]
        if len(train)<10 or any(sum(r['property']==k for r in train)<3 for k in ['krw','kro','pc']):raise ValueError('Fit requires at least three training values for each of krw, kro and Pc, and ten values in total')
        scales={k:max(max(r['measured'] for r in train if r['property']==k),.01) for k in ['krw','kro','pc']}
        count={k:sum(r['property']==k for r in train) for k in scales}
        def residual(x):
            params={**p,**dict(zip(names,x))};return [(curve(r['sw'],params)[r['property']]-r['measured'])/scales[r['property']]/math.sqrt(count[r['property']]) for r in train]
        fit=least_squares(residual,[p[n] for n in names],bounds=(lower,upper),x_scale='jac',max_nfev=1500);fitinfo=diagnostics(fit,names)
        p.update(dict(zip(names,map(float,fit.x))))
    checks=[{**r,'predicted':curve(r['sw'],p)[r['property']]} for r in obs]
    metrics=[]
    for role in ['training','validation','reference']:
        for prop in ['krw','kro','pc']:
            rr=[r for r in checks if r['role']==role and r['property']==prop]
            if rr:metrics.append({'role':role,'property':prop,**metric([r['measured'] for r in rr],[r['predicted'] for r in rr])})
    return {'parameters':p,'fit':fitinfo,'metrics':metrics,'checks':checks,'rows':[curve(float(sw),p) for sw in np.linspace(p['swc'],1-p['sor'],101)],'summary':{'porosityFraction':phi,'bulkVolumeCm3':bulk,'liquidPermeabilityMd':permeability},'note':'Core Darcy calculation assumes steady single-liquid flow. Corey endpoints use Swc/Sor; Brooks–Corey drainage Pc uses (Sw−Swc)/(1−Swc). Pc is undefined at Swc. No hysteresis, three-phase relperm or gas-slip correction.'}

PSI=6894.757293168;BBL=.158987294928

def nodal_parameters(p):
    n=values(p,{'pr':(.1,30000),'pb':(0,30000),'pi':(.00001,1000),'whp':(.1,30000),'tvd':(0,10000),'length':(.1,30000),'diameter':(.01,.5),'roughness':(0,.005),'density':(100,2000),'viscosity':(.01,10000),'fvf':(.1,5)})
    n.update(ipr=p.get('ipr','composite'),vlp=p.get('vlp','measured'))
    if n['ipr'] not in ['linear','composite'] or n['vlp'] not in ['measured','liquid']:raise ValueError('Unknown IPR or VLP method')
    if n['tvd']>n['length']:raise ValueError('TVD cannot exceed measured tubing length')
    if n['roughness']/n['diameter']>.05:raise ValueError('Relative roughness must be at most 0.05')
    if n['vlp']=='liquid' and (n['ipr']!='linear' or n['whp']<n['pb']):raise ValueError('Single-liquid VLP requires linear IPR and wellhead pressure at or above bubble pressure; use measured VLP for gas-liberating flow')
    return n

def ipr(p,pwf):
    pr=p['pr'];pb=min(p['pb'],pr);j=p['pi']
    if p['ipr']=='linear' or pb==0 or pwf>=pb:return j*(pr-pwf)
    return j*(pr-pb)+j*pb/1.8*(1-.2*pwf/pb-.8*(pwf/pb)**2)

def liquid_vlp(p,q):
    v=q*BBL/86400*p['fvf']/(math.pi*p['diameter']**2/4);re=p['density']*v*p['diameter']/(p['viscosity']*.001)
    # Smooth transition between laminar and turbulent formulas; transitional predictions are approximate.
    if re==0:f=0
    elif re<=2300:f=64/re
    else:
        turbulent=(-1.8*math.log10((p['roughness']/p['diameter']/3.7)**1.11+6.9/re))**-2
        f=turbulent if re>=4000 else (64/re)*(4000-re)/1700+turbulent*(re-2300)/1700
    friction=f*p['length']/p['diameter']*p['density']*v*v/2/PSI
    return {'pwf':p['whp']+p['density']*9.80665*p['tvd']/PSI+friction,'velocity':v,'Re':re,'frictionPsi':friction}

def nodal(p,rows):
    p=nodal_parameters(p);qmax=ipr(p,0);qlo=0;qhi=qmax
    if p['vlp']=='measured':
        if not 2<=len(rows)<=500:raise ValueError('Enter 2 to 500 measured VLP points')
        rr=sorted([(number(r.get('rate'),'VLP rate',0,1e7),number(r.get('pwf'),'VLP bottomhole pressure',.1,30000)) for r in rows])
        if len({q for q,_ in rr})!=len(rr):raise ValueError('VLP rates must be unique')
        qlo=max(0,rr[0][0]);qhi=min(qmax,rr[-1][0])
        if qlo>=qhi:raise ValueError('VLP data does not overlap the IPR rate range')
        def vlp(q):return float(np.interp(q,[v[0] for v in rr],[v[1] for v in rr]))
    else:
        def vlp(q):return liquid_vlp(p,q)['pwf']
    def pressure(q):return p['pr']-q/p['pi'] if p['ipr']=='linear' else brentq(lambda pw:ipr(p,pw)-q,0,p['pr']) if 0<q<qmax else p['pr'] if q==0 else 0
    grid=np.unique(np.r_[np.linspace(qlo,qhi,301),[q for q,_ in rr if qlo<=q<=qhi] if p['vlp']=='measured' else []]);roots=[]
    def diff(q):return pressure(q)-vlp(q)
    for a,b in zip(grid[:-1],grid[1:]):
        fa=diff(a);fb=diff(b)
        root=float(a) if abs(fa)<1e-8 else float(b) if abs(fb)<1e-8 else float(brentq(diff,a,b)) if fa*fb<0 else None
        if root is not None and not any(abs(root-x)<1e-5 for x in roots):roots.append(root)
    operating=[{'rate':q,'pwf':vlp(q),'residualPsi':diff(q),**({'velocity':liquid_vlp(p,q)['velocity']} if p['vlp']=='liquid' else {})} for q in roots]
    return {'parameters':p,'rows':[{'rate':float(q),'iprPressure':pressure(q),'vlpPressure':vlp(q)} for q in grid],'operatingPoints':operating,'summary':{'aofStbDay':qmax,'intersections':len(roots),'firstOperatingRate':roots[0] if roots else None},'note':'All pressures are absolute. Measured VLP uses linear interpolation only within its supplied range. All detected crossings are reported. Single-liquid mode uses constant properties and Darcy–Weisbach; it excludes gas slip, acceleration, artificial lift and heat transfer. Tangential contacts may require finer measured curves.'}

def optimize(p):
    n=nodal_parameters({**p,'ipr':'linear','vlp':'liquid'});bounds=values(p,{'minWhp':(.1,30000),'maxWhp':(.1,30000),'minDiameter':(.01,.5),'maxDiameter':(.01,.5),'maxVelocity':(.01,50),'maxRate':(.1,1e7),'maxDrawdown':(.1,30000)})
    if bounds['minWhp']>bounds['maxWhp'] or bounds['minDiameter']>bounds['maxDiameter']:raise ValueError('Scenario lower bounds must not exceed upper bounds')
    if bounds['minWhp']<n['pb']:raise ValueError('All single-liquid scenarios must stay above bubble pressure')
    results=[]
    for whp in np.linspace(bounds['minWhp'],bounds['maxWhp'],9):
        for diameter in np.linspace(bounds['minDiameter'],bounds['maxDiameter'],9):
            a=nodal({**n,'whp':whp,'diameter':diameter},[]);op=a['operatingPoints'];r={'whp':float(whp),'diameter':float(diameter),'rate':None,'pwf':None,'velocity':None,'feasible':False}
            if op:r.update(op[0]);r['feasible']=bool(r['rate']<=bounds['maxRate'] and r['velocity']<=bounds['maxVelocity'] and n['pr']-r['pwf']<=bounds['maxDrawdown'])
            results.append(r)
    feasible=[r for r in results if r['feasible']];best=max(feasible,key=lambda r:r['rate']) if feasible else None
    return {'rows':results,'summary':{'testedScenarios':len(results),'feasibleScenarios':len(feasible),'bestRate':best['rate'] if best else None,'bestWhp':best['whp'] if best else None,'bestDiameter':best['diameter'] if best else None},'note':'Best feasible point among an explicit 9×9 grid, maximizing liquid rate. This is a planning scenario, not a continuous global optimum or an operating command. Assumes single-liquid flow, fixed PI/density/viscosity/FVF and no gas liberation. No equipment rating is inferred.'}

def decline_rate(t,qi,di,b,terminal=0):
    t=np.asarray(t,float)
    if b<1e-7:return qi*np.exp(-di*t)
    switch=max(0,(di/terminal-1)/(b*di)) if terminal>0 and di>0 else math.inf
    base=qi*np.exp(-np.log1p(b*di*np.minimum(t,switch))/b)
    return base*np.exp(-terminal*np.maximum(0,t-switch)) if math.isfinite(switch) else base

def history(p,rows):
    data=time_rows(rows);cut=max(5,int(len(data)*.8));train=data[:cut];valid=data[cut:]
    method=p.get('method','hyperbolic')
    if method=='tank':
        bo=number(p.get('bo'),'Oil FVF',.1,5);bw=number(p.get('bw'),'Water FVF',.5,2);ct=number(p.get('ct'),'Total compressibility 1/psi',1e-8,.01)
        net=0;last=None
        for r in data:
            rate=number(r.get('oil_rate'),'Oil rate',0,1e7)*bo+number(r.get('water_rate'),'Water rate',0,1e7)*bw-number(r.get('injection_rate'),'Injection rate',0,1e7)*bw
            if last:net+=(rate+last[1])/2*(r['day']-last[0])
            r['netWithdrawal']=net;last=(r['day'],rate);r['measured']=number(r.get('pressure'),'Reservoir pressure',.1,30000)
        x=np.array([r['netWithdrawal'] for r in train]);y=np.array([r['measured'] for r in train]);scale=max(float(np.ptp(x)),1)
        fit=least_squares(lambda a:(a[0]-a[1]*x/scale-y)/max(np.std(y),1),[y[0],max(float(np.ptp(y)),1)],bounds=([.1,1e-9],[30000,1e6]),x_scale='jac')
        capacity=scale/fit.x[1];predict=lambda r:float(fit.x[0]-r['netWithdrawal']/capacity)
        for r in data:r['predicted']=predict(r);r['role']='training' if r in train else 'validation'
        return {'rows':data,'summary':{'initialPressurePsi':float(fit.x[0]),'storageRbPerPsi':float(capacity),'poreVolumeRbGivenCt':float(capacity/ct),'assumedCt':ct},'fit':diagnostics(fit,['initialPressure','storageSlope']),'metrics':[{'role':role,**metric([r['measured'] for r in a],[r['predicted'] for r in a])} for role,a in [('training',train),('validation',valid)]] ,'note':'Closed, constant-compressibility single-tank material balance; net withdrawal integrates rates by trapezoids. Fit identifies storage PV×ct, not PV and ct separately. No aquifer, gas-cap, free-gas expansion or spatial reservoir simulation. Assumed ct determines reported pore volume; use average reservoir pressure, not flowing pressure.'}
    if method not in ['exponential','hyperbolic','harmonic']:raise ValueError('Choose a supported decline model')
    for r in data:r['measured']=number(r.get('oil_rate'),'Oil rate',0,1e7)
    t=np.array([r['day'] for r in train]);q=np.array([r['measured'] for r in train]);scale=max(float(np.max(q)),1)
    if np.count_nonzero(q)>0 and np.std(t)>0:pass
    else:raise ValueError('Need positive production over distinct dates')
    fixed=0 if method=='exponential' else 1;names=['qi','di']+(['b'] if method=='hyperbolic' else [])
    def unpack(a):return [a[0],a[1],a[2] if method=='hyperbolic' else fixed]
    fit=least_squares(lambda a:(decline_rate(t,*unpack(a))-q)/scale,[max(q[0],1),.001]+([.5] if len(names)==3 else []),bounds=([1e-6,1e-8]+([0] if len(names)==3 else []),[max(scale*20,10),1]+([1] if len(names)==3 else [])),x_scale='jac',max_nfev=2000)
    qi,di,b=map(float,unpack(fit.x));diag=diagnostics(fit,names)
    for i,r in enumerate(data):r.update(predicted=float(decline_rate(r['day'],qi,di,b)),role='training' if i<cut else 'validation')
    metrics=[{'role':role,**metric([r['measured'] for r in a],[r['predicted'] for r in a])} for role,a in [('training',train),('validation',valid)]]
    days=int(number(p.get('horizon',365),'Forecast days',1,3650));terminal=number(p.get('terminal',.0001),'Terminal nominal decline 1/day',0,.5);capacity=number(p.get('capacity',1e6),'Rate capacity',.001,1e7);economic=number(p.get('economic',0),'Economic rate limit',0,1e7)
    if terminal>di:raise ValueError('Terminal decline cannot exceed fitted initial decline; reduce the terminal value')
    start=data[-1]['day'];forecast=[];cum=0;previous=None;stopped=False
    for day in range(days+1):
        tnew=start+day;potential=float(decline_rate(tnew,qi,di,b,terminal));rate=min(potential,capacity)
        if rate<economic:stopped=True
        if stopped:rate=0
        if previous is not None:cum+=(previous+rate)/2
        previous=rate;forecast.append({'day':tnew,'date':datetime.fromtimestamp(data[0]['epoch']+tnew*86400,timezone.utc).date().isoformat(),'potentialRate':potential,'forecastRate':rate,'cumulativeForecastStb':cum})
    return {'rows':data,'forecast':forecast,'summary':{'qiStbDay':qi,'initialDeclinePerDay':di,'b':b,'forecastVolumeStb':cum,'trainingRows':len(train),'validationRows':len(valid)},'fit':diag,'metrics':metrics,'note':'Arps rate-history match on the earliest 80% only; latest 20% are held out and never refitted. Rates are calendar-day STB/day. Zero rates are retained. Forecast starts at the last observation with fixed fitted parameters, terminal nominal decline, capacity and economic-rate cutoff. Empirical planning forecast, not a spatial reservoir history match or reserves classification.'}

def machine_learning(p,rows):
    data=time_rows(rows,30);features=['pressure','temperature','choke'];cut=int(.8*len(data));train=data[:cut];valid=data[cut:]
    for r in data:
        for k in features:r[k]=number(r.get(k),k,0 if k!='temperature' else -100,1e7)
        r['oil_rate']=number(r.get('oil_rate'),'oil_rate',0,1e7)
        if r['choke']>100:raise ValueError('Choke must be a percentage from 0 to 100')
    X=np.array([[r[k] for k in features] for r in train]);y=np.array([r['oil_rate'] for r in train]);inner=int(.75*cut)
    def fit_ridge(x,y,alpha):
        mean=x.mean(axis=0);sd=x.std(axis=0)
        if np.any(sd<1e-9):raise ValueError('Each AI feature needs variation in the training window')
        z=(x-mean)/sd;design=np.c_[np.ones(len(z)),z];reg=np.diag([0,alpha,alpha,alpha]);coef=np.linalg.solve(design.T@design+reg,design.T@y)
        return mean,sd,coef
    def predict(model,x):
        mean,sd,coef=model;return np.c_[np.ones(len(x)),(x-mean)/sd]@coef
    candidates=[]
    for alpha in [.001,.01,.1,1,10,100]:
        model=fit_ridge(X[:inner],y[:inner],alpha);score=metric(y[inner:],predict(model,X[inner:]))['RMSE'];candidates.append((score,alpha))
    alpha=min(candidates)[1];model=fit_ridge(X,y,alpha);xt=np.array([[r[k] for k in features] for r in valid]);pred=predict(model,xt);baseline=np.full(len(valid),y[-1]);m=metric([r['oil_rate'] for r in valid],pred);base=metric([r['oil_rate'] for r in valid],baseline)
    for i,r in enumerate(data):r.update(predicted=float(predict(model,np.array([[r[k] for k in features]]))[0]),role='training' if i<cut else 'validation')
    query=np.array([[number(p.get(k),'Prediction '+k) for k in features]]);inside=bool(np.all(query>=X.min(axis=0)) and np.all(query<=X.max(axis=0)))
    return {'rows':data,'metrics':[{'role':'held-out model',**m},{'role':'held-out last-rate baseline',**base}],'summary':{'trainingRows':cut,'validationRows':len(valid),'ridgeAlpha':alpha,'predictionStbDay':float(predict(model,query)[0]) if inside else None,'queryWithinTrainingRange':inside,'beatsBaseline':m['RMSE']<base['RMSE']},'model':{'algorithm':'standardized ridge regression','features':features,'mean':model[0].tolist(),'scale':model[1].tolist(),'coefficients':model[2].tolist(),'alpha':alpha,'minimum':X.min(axis=0).tolist(),'maximum':X.max(axis=0).tolist()},'note':'Open, inspectable statistical learning model. Chronological 80/20 evaluation; alpha chosen on an inner chronological training split; scaling uses training only. Same-time prediction is not a future forecast or causal choke recommendation. Queries outside training min/max are refused; an in-range query may still be unfamiliar. Negative predictions are retained as diagnostics, not clipped into apparent accuracy.'}

def engineering_dispatch(request):
    kind=request.get('kind');p=request.get('parameters',{});rows=request.get('rows',[])
    if kind=='core':return scal(p,rows,request.get('action','calculate'))
    if kind=='nodal':return nodal(p,rows)
    if kind=='history' or kind=='forecast':return history(p,rows)
    if kind=='optimize':return optimize(p)
    if kind=='learning':return machine_learning(p,rows)
    raise ValueError('Unknown engineering module')
