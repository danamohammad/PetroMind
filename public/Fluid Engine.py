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
VERSION = '1.0.0'

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
    return dict(version=VERSION,model=req.get('model','PR'),names=names,z=z,state=state,surface=surf,saturation=sat,sweep=rows,conditions=c,signature=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest(),warnings=['Heavy-end properties are inherited assumptions, not a laboratory characterization.'] if any(d['pseudo'] for d in data) else [])

def envelope(req):
    f,z,names,data=build(req)
    lo=finite(req.get('envelopeMin',-50),'Envelope minimum temperature',-200,550)
    hi=finite(req.get('envelopeMax',400),'Envelope maximum temperature',-150,600)
    if hi<=lo:raise ValueError('Envelope maximum temperature must exceed minimum.')
    n=int(finite(req.get('envelopePoints',25),'Envelope points',8,60));rows=[]
    for t in np.linspace(lo,hi,n):
        row=dict(temperature=float(t))
        for k,vf in [('bubble',0),('dew',1)]:
            s=saturation(f,z,float(t),vf);row[k]=s['pressure'];row[k+'Error']=s['error']
        rows.append(row)
    return dict(rows=rows,note='Independent isothermal saturation roots. Gaps are unresolved; no fabricated critical point or interpolation across gaps. Retrograde/multiple-root envelopes may require continuation in a specialist simulator.')

def comparison(req):
    f,z,names,data=build(req);c=conditions(req);rows=req['lab'];out=[]
    if not 1<=len(rows)<=250:raise ValueError('Use 1 to 250 laboratory rows.')
    keys={'Bo':'Bo','Rs':'Rs','Bg':'Bg','density':'liquidDensity','bubble':'bubble'}
    for i,r in enumerate(rows):
        p=finite(r.get('pressure'),f'Lab row {i+1} pressure',.1,30000)
        t=finite(r.get('temperature',c['temperature']),f'Lab row {i+1} temperature',-200,600)
        a=flash(f,z,t,p);b=surface(f,z,a,t,p,c)
        predictions={**b,'density':a['liquid']['density'] if a['liquid'] else None}
        if r.get('bubble') is not None:predictions['bubble']=saturation(f,z,t,0)['pressure']
        for prop in keys:
            if r.get(prop) is None or r.get(prop)=='':continue
            measured=finite(r[prop],f'Lab row {i+1} {prop}',0,None);pred=predictions.get(prop)
            out.append(dict(row=i+1,pressure=p,temperature=t,property=prop,measured=measured,predicted=pred,error=None if pred is None else pred-measured,relativeError=None if pred is None or measured==0 else 100*(pred-measured)/measured))
    if not out:raise ValueError('No supported measured properties. Use Bo, Rs, Bg, density or bubble columns.')
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
    fun={'calculate':calculate,'envelope':envelope,'compare':comparison,'import':read_file}.get(task)
    if fun is None:raise ValueError('Unknown calculation request.')
    return json.dumps(clean(fun(req)),allow_nan=False)
