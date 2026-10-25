"""PetroMind public workbench. Same code runs in CPython and browser Pyodide.
No network requests or filesystem persistence of user inputs.
"""
import json, math, io, base64, csv, hashlib
from datetime import date, datetime
import numpy as np
from thermo import ChemicalConstantsPackage, PropertyCorrelationsPackage, CEOSGas, CEOSLiquid, PRMIX, PR78MIX, SRKMIX, FlashVL, HeatCapacityGas

PSI = 6894.757293168
SCF = 35.3146667215
STB = 6.2898107704
VERSION = '1.1.0'

# Preserve the requested V-L EOS branches. Thermo's default PIP post-sort can
# relabel a dense vapor branch as a second liquid without changing equilibrium.
# This workbench solves V-L only; it does not claim liquid-liquid equilibrium.
class PetroleumGas(CEOSGas):
    force_phase = 'g'

class PetroleumLiquid(CEOSLiquid):
    force_phase = 'l'

def finite(v, name, low=None, high=None):
    if isinstance(v, bool) or v is None or str(v).strip() == '':
        raise ValueError(f'{name} must be a number.')
    v = float(v)
    if not math.isfinite(v) or (low is not None and v < low) or (high is not None and v > high):
        raise ValueError(f'{name} must be finite and between {low} and {high}.')
    return v

def clean(x):
    if isinstance(x, (date, datetime)): return x.strftime("%Y-%m-%d")
    if isinstance(x, dict): return {str(k): clean(v) for k,v in x.items()}
    if isinstance(x, (list,tuple,np.ndarray)): return [clean(v) for v in x]
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (float,np.floating)): return float(x) if math.isfinite(x) else None
    if isinstance(x, (np.bool_,)): return bool(x)
    return x

def build(req):
    catalog = {c['id']:c.copy() for c in req['catalog']}
    rows = req['composition']
    if not 2 <= len(rows) <= 30: raise ValueError('Use 2 to 30 distinct components.')
    names = [str(r['component']).strip().upper() for r in rows]
    if len(names) != len(set(names)): raise ValueError('Duplicate components are not allowed.')
    if any(n not in catalog for n in names): raise ValueError('A composition component is not in the fluid catalog.')
    z = [finite(r['fraction'], f'{n} mole fraction', 0, 1) for n,r in zip(names,rows)]
    total = sum(z)
    if abs(total-1) > 1e-6: raise ValueError(f'Mole fractions total {total:.8f}. Use Normalize explicitly before calculating.')
    keep = [i for i,x in enumerate(z) if x > 0]
    names = [names[i] for i in keep]; z = [z[i]/total for i in keep]
    if len(names)<2: raise ValueError('At least two components must have a positive fraction.')
    data=[catalog[n] for n in names]
    for c in data:
        c['Tc']=finite(c['Tc'],c['id']+' critical temperature (K)',50,2000)
        c['Pc']=finite(c['Pc'],c['id']+' critical pressure (Pa)',1000,1e9)
        c['MW']=finite(c['MW'],c['id']+' molecular weight (g/mol)',1,2000)
        c['omega']=finite(c['omega'],c['id']+' acentric factor',-.5,3)
    const=ChemicalConstantsPackage(names=names, Tcs=[c['Tc'] for c in data], Pcs=[c['Pc'] for c in data], omegas=[c['omega'] for c in data], MWs=[c['MW'] for c in data])
    # T-P equilibrium needs no heat capacity model. Constant placeholders only satisfy
    # library construction; no enthalpy/entropy/energy-balance results are exposed.
    cps=[HeatCapacityGas(poly_fit=(50,2000,[30.0])) for _ in names]
    props=PropertyCorrelationsPackage(constants=const,HeatCapacityGases=cps,skip_missing=True)
    interactions=req.get('interactions',{})
    kij=[[0.0 if a==b else finite(interactions.get(a+'|'+b,interactions.get(b+'|'+a,0)),f'kij {a}/{b}',-1,1) for b in names] for a in names]
    models={'PR':PRMIX,'PR78':PR78MIX,'SRK':SRKMIX}
    model=req.get('model','PR')
    if model not in models: raise ValueError('Unsupported equation of state.')
    kw=dict(Tcs=const.Tcs,Pcs=const.Pcs,omegas=const.omegas,kijs=kij)
    gas=PetroleumGas(models[model],eos_kwargs=kw,HeatCapacityGases=cps)
    liquid=PetroleumLiquid(models[model],eos_kwargs=kw,HeatCapacityGases=cps)
    flasher=FlashVL(const,props,gas=gas,liquid=liquid)
    return flasher,z,names,data

def conditions(req):
    c=dict(req['conditions'])
    for k in ('temperature','separatorTemperature','tankTemperature','standardTemperature'):
        c[k]=finite(c[k],k+' (°C)',-200,600)
    for k in ('pressure','separatorPressure','tankPressure','standardPressure','minPressure','maxPressure'):
        c[k]=finite(c[k],k+' (psia)',.1,30000)
    if c['maxPressure']<=c['minPressure']: raise ValueError('Maximum sweep pressure must exceed minimum pressure.')
    if c['separatorPressure']<c['tankPressure']: raise ValueError('Separator pressure must be at least stock-tank pressure.')
    n=finite(c.get('points',25),'Sweep points',5,80)
    if n!=int(n): raise ValueError('Sweep point count must be an integer.')
    c['points']=int(n)
    return c

def flash(f,z,t,p):
    result=f.flash(T=t+273.15,P=p*PSI,zs=z)
    beta=float(result.VF)
    if not math.isfinite(beta) or not -1e-8<=beta<=1+1e-8: raise ValueError('Solver returned an invalid vapor fraction.')
    beta=max(0,min(1,beta))
    liq=result.liquid0 if result.liquid_count else None
    gas=result.gas
    x=liq.zs if liq is not None else None
    y=gas.zs if gas is not None else None
    balance=max(abs(v-((1-beta)*x[i] if x else 0)-(beta*y[i] if y else 0)) for i,v in enumerate(z))
    if balance>1e-7: raise ValueError(f'Component balance failed ({balance:.3g}).')
    fugacity=0.0
    if 1e-8<beta<1-1e-8 and liq is not None and gas is not None:
        fl,fg=liq.fugacities(),gas.fugacities()
        fugacity=max(abs(math.log(a/b)) for a,b,zi in zip(fl,fg,z) if zi>1e-12 and a>0 and b>0)
        if fugacity>1e-5: raise ValueError(f'Phase fugacities did not converge ({fugacity:.3g}).')
    def phase(s):
        if s is None:return None
        vm=float(s.V()); mw=float(s.MW())
        if vm<=0 or not math.isfinite(vm):raise ValueError('Invalid molar volume.')
        return dict(z=list(s.zs),Z=float(s.Z()),density=mw/(1000*vm),MW=mw,volume=vm)
    return dict(phase='Liquid + vapor' if 1e-8<beta<1-1e-8 else 'Vapor' if beta>=1-1e-8 else 'Liquid',vaporFraction=beta,liquid=phase(liq),gas=phase(gas),balance=balance,fugacityResidual=fugacity)

def surface(f,z,state,t,p,c):
    out=dict(Bo=None,Rs=None,Bg=None,shrinkage=None,stockDensity=None,stages=[],balance=None,warnings=[])
    def gas_volume(comp,n):
        ref=flash(f,comp,c['standardTemperature'],c['standardPressure'])
        if ref['vaporFraction']<1-1e-7:raise ValueError('Gas condenses at the chosen standard conditions; dry-gas volume basis is unavailable.')
        return n*ref['gas']['volume']
    if state['gas'] and state['vaporFraction']>1e-8:
        try:out['Bg']=state['gas']['volume']/gas_volume(state['gas']['z'],1)*STB/SCF
        except Exception as e:out['warnings'].append('Bg: '+str(e))
    if not state['liquid'] or state['vaporFraction']>=1-1e-8:
        out['warnings'].append('No reservoir liquid: Bo and Rs are not applicable.');return out
    oil_n=1-state['vaporFraction'];oil_z=state['liquid']['z'];initial=np.array(oil_z)*oil_n
    reservoir_volume=oil_n*state['liquid']['volume'];gas_components=np.zeros(len(z));gas_std=0;gas_valid=True
    for title,temp,pres in [('Separator',c['separatorTemperature'],c['separatorPressure']),('Stock tank',c['tankTemperature'],c['tankPressure'])]:
        stage=flash(f,oil_z,temp,pres); n_gas=oil_n*stage['vaporFraction'];n_liq=oil_n-n_gas
        out['stages'].append(dict(stage=title,temperature=temp,pressure=pres,feedMoles=oil_n,gasMoles=n_gas,liquidMoles=n_liq,balance=stage['balance']))
        if n_gas>1e-10:
            gas_components+=np.array(stage['gas']['z'])*n_gas
            try:gas_std+=gas_volume(stage['gas']['z'],n_gas)
            except Exception as e:gas_valid=False;out['warnings'].append(title+': '+str(e))
        if n_liq<=1e-10 or stage['liquid'] is None:
            out['warnings'].append('No stock-tank liquid remains; Bo and Rs are unavailable.');return out
        oil_n=n_liq;oil_z=stage['liquid']['z'];last=stage['liquid']
    residual=initial-gas_components-np.array(oil_z)*oil_n
    out['balance']=float(max(abs(residual)))
    if out['balance']>1e-7:raise ValueError('Surface train component balance failed.')
    stock_volume=oil_n*last['volume']
    out.update(Bo=reservoir_volume/stock_volume,Rs=gas_std*SCF/(stock_volume*STB) if gas_valid else None,shrinkage=stock_volume/reservoir_volume,stockDensity=last['density'])
    out['components']=[dict(component=i,feed=float(initial[i]),gas=float(gas_components[i]),oil=float(oil_n*oil_z[i]),residual=float(residual[i])) for i in range(len(z))]
    if out['Bo']<1:out['warnings'].append('Bo is below one; inspect volume calibration and reference conditions.')
    return out

def saturation(f,z,t,vf):
    # Bound browser work: omit nested pressure-bracketing/PT-flash fallback.
    # Failed direct Newton roots remain explicitly unresolved.
    f.dew_T_flash_algos = f.dew_T_flash_algos[:2]
    f.bubble_T_flash_algos = f.bubble_T_flash_algos[:2]
    f.DEW_BUBBLE_QUASI_NEWTON_MAXITER = 80
    try:
        r=f.flash(T=t+273.15,VF=vf,zs=z)
        p=float(r.P)/PSI
        if not math.isfinite(p) or not .1<=p<=30000:raise ValueError('Outside supported pressure range.')
        if r.gas is None or not r.liquid_count:raise ValueError('No distinct incipient phases.')
        separation=max(abs(a-b) for a,b in zip(r.gas.zs,r.liquid0.zs))
        if separation<1e-5:raise ValueError('Trivial or near-critical root rejected.')
        fg,fl=r.gas.fugacities(),r.liquid0.fugacities()
        err=max(abs(math.log(a/b)) for a,b,zi in zip(fg,fl,z) if zi>1e-12 and a>0 and b>0)
        if err>1e-5:raise ValueError('Saturation fugacity residual exceeds tolerance.')
        return dict(pressure=p,error=None,residual=err)
    except Exception as e:return dict(pressure=None,error='Direct saturation solver did not converge.' if isinstance(e, UnboundLocalError) else str(e)[:180])

def calculate(req):
    f,z,names,data=build(req);c=conditions(req);t=c['temperature'];p=c['pressure']
    state=flash(f,z,t,p);surf=surface(f,z,state,t,p,c)
    sat={k:saturation(f,z,t,vf) for k,vf in [('bubble',0),('dew',1)]}
    pressures=list(np.linspace(c['minPressure'],c['maxPressure'],c['points']))
    pressures.append(p)
    for s in sat.values():
        if s['pressure'] and c['minPressure']<=s['pressure']<=c['maxPressure']:pressures.extend([s['pressure']*.999,s['pressure'],s['pressure']*1.001])
    pressures=sorted(set(float(x) for x in pressures if c['minPressure']<=x<=c['maxPressure'] or x==p))
    rows=[]
    for pressure in pressures:
        row=dict(pressure=pressure,temperature=t)
        try:
            a=flash(f,z,t,pressure);b=surface(f,z,a,t,pressure,c)
            row.update(phase=a['phase'],vaporFraction=a['vaporFraction'],Bo=b['Bo'],Rs=b['Rs'],Bg=b['Bg'],liquidDensity=a['liquid']['density'] if a['liquid'] else None,gasDensity=a['gas']['density'] if a['gas'] else None,liquidZ=a['liquid']['Z'] if a['liquid'] else None,gasZ=a['gas']['Z'] if a['gas'] else None,balance=a['balance'],fugacityResidual=a['fugacityResidual'],warnings='; '.join(b['warnings']))
        except Exception as e:row.update(error=str(e)[:200],phase='Unresolved')
        rows.append(row)
    for i,row in enumerate(rows):
        row['compressibility']=None
        # Fixed-composition liquid isothermal compressibility. No derivative across phase boundaries.
        if row.get('phase')=='Liquid':
            try:
                dp=max(.01,row['pressure']*.001)
                before=flash(f,z,t,max(.1,row['pressure']-dp));after=flash(f,z,t,row['pressure']+dp)
                if before['phase']==after['phase']=='Liquid':
                    row['compressibility']=-(math.log(after['liquid']['volume'])-math.log(before['liquid']['volume']))/(2*dp)
            except Exception:pass
    return dict(version=VERSION,model=req.get('model','PR'),names=names,z=z,state=state,surface=surf,saturation=sat,sweep=rows,conditions=c,signature=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest(),warnings=['Heavy-end properties require sample-specific characterization and validation.'] if any(d['pseudo'] for d in data) else [])

def report(message):
    """Worker progress callback is optional so the same engine runs in CPython."""
    callback = globals().get('progress_callback')
    if callback: callback(message)


def envelope(req):
    """Pseudo-arclength continuation of a fixed-composition V-L boundary.

    The parent composition stays z and the incipient composition is z*exp(k).
    Dividing equilibrium equations by ||k|| removes attraction to the trivial
    equal-composition solution. Root labels swap as the light-component k
    changes sign at the critical point. No interpolation bridges failed steps.
    """
    from scipy.optimize import root, least_squares
    f,z,names,data=build(req);z=np.array(z);n=len(z)
    lo=finite(req.get('envelopeMin',-200),'Minimum temperature',-200,550)+273.15
    hi=finite(req.get('envelopeMax',600),'Maximum temperature',-150,600)+273.15
    pmin=finite(req.get('envelopePressure',14.7),'Envelope pressure floor',.1,10000)*PSI
    if hi<=lo:raise ValueError('Envelope maximum temperature must exceed minimum.')
    budget=finite(req.get('envelopePoints',500),'Maximum continuation steps',100,1600)
    if budget!=int(budget):raise ValueError('Maximum steps must be an integer.')
    budget=int(budget);light=int(np.argmin([d['Tc'] for d in data]))
    def states(u):
        k=u[:n];T,P=np.exp(u[n:]);w=z*np.exp(k);sw=sum(w)
        if not np.isfinite(sw) or sw<=0:raise ValueError('Invalid trial composition.')
        parent,trial=(f.liquid,f.gas) if k[light]>=0 else (f.gas,f.liquid)
        a=parent.to(T=float(T),P=float(P),zs=z.tolist())
        b=trial.to(T=float(T),P=float(P),zs=(w/sw).tolist())
        return a,b,sw
    def residual(u):
        if not np.all(np.isfinite(u)) or max(abs(u[:n]))>300 or not 3< u[-2]<8 or not 0<u[-1]<22:
            raise ValueError('Continuation iterate outside EOS bounds.')
        a,b,sw=states(u);k=u[:n]
        return np.r_[k+np.array(b.lnphis())-a.lnphis()-math.log(sw),math.log(sw)]/max(np.linalg.norm(k),1e-10)
    def tangent(u):
        h=1e-5;eye=np.eye(n+2)*h
        j=np.array([(residual(u+d)-residual(u-d))/(2*h) for d in eye]).T
        return np.linalg.svd(j)[2][-1]
    def point(u):
        a,b,sw=states(u);T,P=np.exp(u[-2:]);k=u[:n]
        err=float(max(abs(residual(u)))*np.linalg.norm(k))
        if err>1e-6 or abs(sw-1)>1e-7:raise ValueError('Equilibrium tolerance exceeded.')
        bubble=k[light]>=0;x=a.zs if bubble else b.zs;y=b.zs if bubble else a.zs
        return dict(temperature=float(T-273.15),pressure=float(P/PSI),branch='bubble' if bubble else 'dew',
                    fugacityResidual=err,compositionResidual=abs(sw-1),liquidVolume=a.V() if bubble else b.V(),gasVolume=b.V() if bubble else a.V(),
                    liquidComposition=list(x),gasComposition=list(y))
    # Start at an ordinary noncritical bubble point, then trace both directions.
    f.dew_T_flash_algos=f.dew_T_flash_algos[:2];f.bubble_T_flash_algos=f.bubble_T_flash_algos[:2]
    f.DEW_BUBBLE_QUASI_NEWTON_MAXITER=80
    candidates=[float(np.dot(z,[d['Tc'] for d in data]))*.7,finite(req['conditions']['temperature'],'Temperature',-200,600)+273.15]
    candidates+=list(np.linspace(max(lo,100),min(hi,750),24))
    seed=None
    for T in candidates:
        if not lo<T<hi:continue
        try:
            s=f.flash(T=float(T),VF=0,zs=z.tolist())
            if s.gas is None or not s.liquid_count or not pmin<s.P<30000*PSI:continue
            k=np.log(np.array(s.gas.zs)/z);u=np.r_[k,math.log(T),math.log(s.P)]
            if np.linalg.norm(k)>.2 and k[light]>0 and max(abs(residual(u)))<1e-7:
                point(u);seed=u;break
        except Exception:continue
    if seed is None:raise ValueError('No nontrivial starting boundary found inside these limits. Expand the temperature range or lower the pressure floor.')
    limits=[(n,math.log(lo),'Minimum temperature'),(n,math.log(hi),'Maximum temperature'),(n+1,math.log(pmin),'Pressure floor'),(n+1,math.log(30000*PSI),'Pressure ceiling')]
    def trace(direction):
        u=seed.copy();tan=tangent(u);tan*=direction*(1 if tan[-2]>0 else -1);ds=.12;path=[]
        for step in range(budget):
            if step%20==0:report(f'Tracing phase envelope: {step} steps on branch {1 if direction>0 else 2}…')
            accepted=False
            for attempt in range(12):
                pred=u+ds*tan
                pivot=int(np.argmax(abs(tan[:n]))) if np.linalg.norm(u[:n])<.7 else None
                if pivot is not None and abs(pred[pivot])<.02:
                    target=-math.copysign(.02,u[pivot]) if u[pivot]*tan[pivot]<0 else math.copysign(.02,u[pivot])
                    pred=u+(target-u[pivot])/tan[pivot]*tan
                specification=(lambda v:v[pivot]-pred[pivot]) if pivot is not None else (lambda v:np.dot(v-pred,tan))
                try:
                    equations=lambda v:np.r_[residual(v),specification(v)]
                    sol=root(equations,pred,tol=1e-9,options={'maxfev':(n+2)*40,'eps':1e-8})
                    nxt=sol.x
                    if pivot is not None and max(abs(equations(nxt)))>=1e-7:
                        nxt=least_squares(equations,pred,jac='3-point',diff_step=1e-4,max_nfev=60,gtol=1e-11,ftol=1e-11,xtol=1e-11).x
                    if max(abs(residual(nxt)))<1e-7 and np.linalg.norm(nxt-pred)<(.2 if pivot is not None else .8*ds) and np.linalg.norm(nxt[:n])>max(1e-5,.2*np.linalg.norm(pred[:n])):
                        point(nxt);accepted=True;break
                except Exception:pass
                ds*=.5
                if ds<1e-5:break
            if not accepted:return path,'Corrector did not converge; trace stops here.'
            # Land exactly on the first requested boundary instead of clipping a line.
            crossed=[]
            for idx,bound,label in limits:
                if (u[idx]-bound)*(nxt[idx]-bound)<0:
                    crossed.append(((bound-u[idx])/(nxt[idx]-u[idx]),idx,bound,label))
            if crossed:
                frac,idx,bound,label=min(crossed)
                guess=u+frac*(nxt-u)
                try:
                    end=root(lambda v:np.r_[residual(v),v[idx]-bound],guess,tol=1e-9)
                    if max(abs(residual(end.x)))>1e-7 or abs(end.x[idx]-bound)>1e-7:raise ValueError()
                    point(end.x);path.append(end.x)
                    return path,label
                except Exception:return path,'Boundary corrector failed; last converged point retained.'
            path.append(nxt);u=nxt
            try:newtan=tangent(u);newtan*=1 if newtan@tan>0 else -1;tan=newtan
            except Exception:return path,'Tangent calculation failed; last converged point retained.'
            ds=min(.12 if np.linalg.norm(u[:n])<1 else .5,ds*1.25)
        return path,'Step budget reached; increase the maximum steps.'
    forward,reason1=trace(1);backward,reason2=trace(-1)
    path=list(reversed(backward))+[seed]+forward
    rows=[point(u) for u in path]
    critical=None
    # Solve actual mixture criticality: zero smallest stability eigenvalue and
    # zero third derivative along its eigenvector (Michelsen T,P formulation).
    crossing=next(((a,b) for a,b in zip(path,path[1:]) if a[light]*b[light]<0),None)
    if crossing:
        report('Refining the mixture critical point and envelope turning points…')
        a,b=crossing;q=(a[-2:]*abs(b[light])+b[-2:]*abs(a[light]))/(abs(a[light])+abs(b[light]))
        sq=np.sqrt(z)
        def criticality(q):
            T,P=np.exp(q)
            def matrix(Y):
                total=sum(Y);ph=f.gas.to(T=float(T),P=float(P),zs=(Y/total).tolist())
                d=np.array(ph.eos_mix.dlnphis_dns(ph.Z()))/total
                return np.diag(z/Y)+sq[:,None]*d*sq[None,:]
            B=matrix(z);ev,U=np.linalg.eigh((B+B.T)/2);v=U[:,0];v*=1 if v[np.argmax(abs(v))]>=0 else -1
            direction=sq*v;h=min(.0002,.001*min(z/np.maximum(abs(direction),1e-30)))
            third=float(v@(matrix(z+h*direction)-matrix(z-h*direction))@v/(2*h))
            return np.array([ev[0],third])
        try:
            cr=root(criticality,q,tol=1e-8,options={'eps':1e-6,'maxfev':100})
            checks=criticality(cr.x);T,P=np.exp(cr.x)
            if max(abs(checks))<1e-5 and max(abs(cr.x-q))<.05:
                critical=dict(temperature=float(T-273.15),pressure=float(P/PSI),stabilityEigenvalue=float(checks[0]),thirdDerivative=float(checks[1]),method='Mixture stability criticality equations')
        except Exception:pass
    extrema={}
    for label,idx in [('cricondentherm',n),('cricondenbar',n+1)]:
        best=max(range(len(path)),key=lambda j:path[j][idx])
        if 0<best<len(path)-1:
            try:
                sol=root(lambda v:np.r_[residual(v),tangent(v)[idx]],path[best],tol=1e-8,options={'maxfev':(n+2)*35})
                if max(abs(residual(sol.x)))<1e-7 and abs(tangent(sol.x)[idx])<1e-5 and np.linalg.norm(sol.x-path[best])<1:
                    extrema[label]=point(sol.x)
            except Exception:pass
    # A complete supported envelope must traverse the critical neighborhood and
    # return to the pressure floor on both sides. Other exits are partial traces.
    complete=reason1==reason2=='Pressure floor' and critical is not None and len(extrema)==2
    status='Complete within pressure limits' if complete else 'Partial trace'
    note=f'{status}. {len(rows)} converged points. Endpoints: {reason2}; {reason1}. '
    note+='Critical point verified by mixture stability equations. ' if critical else 'Critical point not verified. '
    note+='Vapor–liquid model only; disconnected branches, liquid–liquid equilibria and solids are outside this trace. Limits do not represent experimental validation.'
    return dict(rows=rows,critical=critical,extrema=extrema,complete=complete,status=status,note=note,
                endpoints=[reason2,reason1],method='Adaptive pseudo-arclength predictor–corrector',names=names,
                inputSignature=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest())


def tune(req):
    """Bounded weighted least-squares calibration. Never mutates the input model."""
    import copy
    from scipy.optimize import least_squares
    build(req);conditions(req)
    specs=req.get('tuningParameters',[])
    if not 1<=len(specs)<=6:raise ValueError('Select between one and six tuning parameters.')
    keys=[];starts=[];lower=[];upper=[];parameters=[]
    present={r['component'] for r in req['composition'] if float(r['fraction'])>0}
    cats={c['id']:c for c in req['catalog']}
    for s in specs:
        kind=s.get('kind');name=str(s.get('name',''));key=(kind,name)
        if kind=='kij':
            pair=name.split('|')
            if len(pair)!=2 or pair[0]==pair[1] or not set(pair)<=present:raise ValueError('Tuning interaction pair must contain two active components.')
            name='|'.join(sorted(pair));key=(kind,name)
            initial=float(req.get('interactions',{}).get(name,req.get('interactions',{}).get('|'.join(reversed(name.split('|'))),0)))
            allowed=(-.5,.5)
        elif kind in ('Tc','Pc','omega'):
            if name not in present or not cats[name].get('pseudo'):raise ValueError('Critical-property tuning is limited to active pseudocomponents.')
            initial=float(cats[name][kind]);allowed={'Tc':(50,2000),'Pc':(1000,1e9),'omega':(-.5,3)}[kind]
        else:raise ValueError('Unsupported tuning parameter.')
        if key in keys:raise ValueError('Duplicate tuning parameter.')
        low=finite(s.get('lower'),name+' lower bound',*allowed);high=finite(s.get('upper'),name+' upper bound',*allowed)
        if not low<high or not low<=initial<=high:raise ValueError('Bounds must contain the current parameter value and have positive width.')
        keys.append(key);starts.append(initial);lower.append(low);upper.append(high);parameters.append(dict(kind=kind,name=name,before=initial,lower=low,upper=high))
    before=comparison(req);observations=before['rows']
    if len(observations)<max(3,len(specs)+2):raise ValueError('Use at least three measured values and at least two more measurements than fitted parameters.')
    if len(observations)>150:raise ValueError('Automatic tuning accepts at most 150 measured values per fit.')
    if any(r['predicted'] is None for r in observations):raise ValueError('The initial model cannot predict every selected measurement. Remove inapplicable measurements or correct the starting model.')
    # Each property receives equal total weight. Zero measurements use an explicit
    # scale floor; they are not dropped or divided by zero.
    floors={'Bo':.01,'Rs':1.,'Bg':1e-5,'density':1.,'bubble':1.,'relativeVolume':.01}
    counts={p:sum(r['property']==p for r in observations) for p in floors}
    weights=req.get('tuningWeights',{})
    scales=np.array([max(abs(r['measured']),floors[r['property']])*math.sqrt(counts[r['property']])/math.sqrt(finite(weights.get(r['property'],1),'Property weight',.01,100)) for r in observations])
    measured=np.array([r['measured'] for r in observations]);lower=np.array(lower);upper=np.array(upper);width=upper-lower
    evaluations=0;invalid=0;cache={}
    def candidate(v):
        model=copy.deepcopy(req);values=lower+width*v
        for p,value in zip(parameters,values):
            if p['kind']=='kij':
                model.setdefault('interactions',{})[p['name']]=float(value)
                model['interactions'].pop('|'.join(reversed(p['name'].split('|'))),None)
            else:next(c for c in model['catalog'] if c['id']==p['name'])[p['kind']]=float(value)
        return model
    def objective(v):
        nonlocal evaluations,invalid
        key=tuple(v)
        if key in cache:return cache[key]
        evaluations+=1
        if evaluations%5==1:report(f'Fitting EOS: {evaluations} model evaluations…')
        try:
            rows=comparison(candidate(v))['rows'];pred=np.array([r['predicted'] if r['predicted'] is not None else np.nan for r in rows])
            if len(rows)!=len(measured) or not np.all(np.isfinite(pred)):raise ValueError('Unavailable prediction')
            residual=(pred-measured)/scales
        except Exception:
            invalid+=1;residual=np.full(len(measured),1e3+np.linalg.norm(v))
        cache[key]=residual
        return residual
    start=(np.array(starts)-lower)/width;initial=objective(start)
    fit=least_squares(objective,start,bounds=(np.zeros(len(specs)),np.ones(len(specs))),diff_step=1e-4,
                      max_nfev=100,ftol=1e-8,xtol=1e-8,gtol=1e-7)
    fitted=candidate(fit.x);after=comparison(fitted)
    final=objective(fit.x);beforeScore=float(np.linalg.norm(initial));afterScore=float(np.linalg.norm(final))
    if any(r['predicted'] is None for r in after['rows']):raise ValueError('Final fitted model has unavailable predictions; no fit is offered.')
    singular=np.linalg.svd(fit.jac,compute_uv=False);rank=int(sum(singular>max(singular[0]*1e-6,1e-8)))
    condition=float(singular[0]/singular[-1]) if singular[-1]>1e-14 else None
    for p,value,x in zip(parameters,lower+width*fit.x,fit.x):p.update(after=float(value),atBound=bool(x<.001 or x>.999))
    warnings=[]
    if not fit.success:warnings.append('Optimizer stopped before convergence; candidate cannot be applied.')
    if rank<len(specs) or condition is None or condition>1e6:warnings.append('Parameters are not independently identifiable from these measurements; candidate cannot be applied.')
    if any(p['atBound'] for p in parameters):warnings.append('A parameter reached its bound. Inspect physical plausibility before applying.')
    if invalid:warnings.append(f'{invalid} trial models failed to predict all observations and were penalized.')
    improved=afterScore<beforeScore*(1-1e-5)
    if not improved:warnings.append('No material improvement over the starting model.')
    eligible=bool(fit.success and improved and rank==len(specs) and condition is not None and condition<=1e6)
    rows=[dict(**{k:v for k,v in a.items() if k not in ('predicted','error','relativeError')},before=a['predicted'],after=b['predicted'],beforeError=a['error'],afterError=b['error']) for a,b in zip(before['rows'],after['rows'])]
    return dict(parameters=parameters,rows=rows,beforeMetrics=before['metrics'],afterMetrics=after['metrics'],beforeScore=beforeScore,afterScore=afterScore,
                improvementPercent=100*(1-afterScore/beforeScore) if beforeScore else 0,evaluations=evaluations,converged=bool(fit.success),eligible=eligible,
                rank=rank,conditionNumber=condition,warnings=warnings,message=str(fit.message),
                candidate=dict(catalog=fitted['catalog'],interactions=fitted.get('interactions',{})),
                note='Bounded local least squares; relative residuals with equal total weight per property. This is a training-data fit, not independent validation. Review held-out data and physical plausibility.',
                inputSignature=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest())


def comparison(req):
    f,z,names,data=build(req);c=conditions(req);rows=req['lab'];out=[]
    if not 1<=len(rows)<=250:raise ValueError('Use 1 to 250 laboratory rows.')
    keys={'Bo':'Bo','Rs':'Rs','Bg':'Bg','density':'liquidDensity','bubble':'bubble','relativeVolume':'relativeVolume'}
    saturation_cache={}
    for i,r in enumerate(rows):
        p=finite(r.get('pressure'),f'Lab row {i+1} pressure',.1,30000)
        t=finite(r.get('temperature',c['temperature']),f'Lab row {i+1} temperature',-200,600)
        needed=[k for k in keys if r.get(k) not in (None,'')]
        predictions={}
        if any(k!='bubble' for k in needed):
            a=flash(f,z,t,p)
            if any(k in needed for k in ('Bo','Rs','Bg')):predictions.update(surface(f,z,a,t,p,c))
            predictions['density']=a['liquid']['density'] if a['liquid'] else None
        if any(k in needed for k in ('bubble','relativeVolume')):
            if t not in saturation_cache:saturation_cache[t]=saturation(f,z,t,0)['pressure']
            pb=saturation_cache[t];predictions['bubble']=pb
            if 'relativeVolume' in needed:
                predictions['relativeVolume']=None
                if pb is not None:
                    reference=f.liquid.to(T=t+273.15,P=pb*PSI,zs=z).V()
                    volume=sum(a['vaporFraction']*a['gas']['volume'] if phase=='gas' else (1-a['vaporFraction'])*a['liquid']['volume'] for phase in ('gas','liquid') if a[phase])
                    predictions['relativeVolume']=volume/reference
        for prop in keys:
            if r.get(prop) is None or r.get(prop)=='':continue
            measured=finite(r[prop],f'Lab row {i+1} {prop}',0,None);pred=predictions.get(prop)
            out.append(dict(row=i+1,pressure=p,temperature=t,property=prop,measured=measured,predicted=pred,error=None if pred is None else pred-measured,relativeError=None if pred is None or measured==0 else 100*(pred-measured)/measured))
    if not out:raise ValueError('No supported measured properties. Use Bo, Rs, Bg, density, bubble or relativeVolume columns.')
    metrics=[]
    for prop in keys:
        rr=[x for x in out if x['property']==prop and x['error'] is not None]
        if rr:
            rel=[abs(x['relativeError']) for x in rr if x['relativeError'] is not None]
            metrics.append(dict(property=prop,count=len(rr),RMSE=math.sqrt(sum(x['error']**2 for x in rr)/len(rr)),MAE=sum(abs(x['error']) for x in rr)/len(rr),AARD=sum(rel)/len(rel) if rel else None))
    return dict(rows=out,metrics=metrics)

def read_file(req):
    raw=base64.b64decode(req['data'],validate=True)
    if len(raw)>5_000_000:raise ValueError('File exceeds the 5 MB import limit.')
    name=req['filename'].lower()
    if name.endswith('.xlsx'):
        import zipfile
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sum(i.file_size for i in z.infolist())>30_000_000:raise ValueError('Expanded workbook exceeds 30 MB.')
        import openpyxl
        book=openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
        sheet=book.active
        values=list(sheet.iter_rows(max_row=1002,values_only=True));book.close()
        if len(values)>1001:raise ValueError('Use at most 1,000 rows.')
        if not values:raise ValueError('Workbook is empty.')
        columns=[str(x or '').strip() for x in values[0]]
        if any(not c for c in columns) or len(columns)!=len(set(columns)):raise ValueError('Duplicate or blank column headings.')
        rows=[dict(zip(columns,row)) for row in values[1:] if any(x is not None for x in row)]
    elif name.endswith('.csv'):
        text=raw.decode('utf-8-sig');reader=csv.DictReader(io.StringIO(text));rows=list(reader)
        if len(rows)>1000:raise ValueError('Use at most 1,000 rows.')
        columns=reader.fieldnames or []
        if len(columns)!=len(set(columns)):raise ValueError('Duplicate column headings.')
        if any(None in row for row in rows):raise ValueError('A CSV row has more values than the header.')
    else:raise ValueError('Use CSV or XLSX files.')
    if not rows:raise ValueError('The file has no data rows.')
    return dict(columns=columns,rows=rows)

def dispatch_json(text):
    req=json.loads(text); task=req.get('task')
    fun={'calculate':calculate,'envelope':envelope,'compare':comparison,'tune':tune,'import':read_file}.get(task)
    if fun is None:raise ValueError('Unknown calculation request.')
    return json.dumps(clean(fun(req)),allow_nan=False)
