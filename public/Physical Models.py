"""Separate NaCl brine, ideal multisolid wax and binary Flory–Huggins models.
SI internally, UI units explicitly named. Never modifies a hydrocarbon EOS project.
"""
import copy
import math
import numpy as np
from scipy.optimize import brentq, least_squares
from chemicals.iapws import iapws95_Psat
R = 8.31446261815324

def number(v, name, lo, hi):
    if isinstance(v, bool) or v is None or v == '': raise ValueError(name+' is required.')
    v=float(v)
    if not math.isfinite(v) or not lo<=v<=hi: raise ValueError(f'{name} must be between {lo} and {hi}.')
    return v

def brine(t,p,m,densityScale=1,viscosityScale=1):
    t=number(t,'Temperature °C',20,150);p=number(p,'Absolute pressure MPa',.1,35);m=number(m,'NaCl molality',0,6)
    ds=number(densityScale,'Density scale',.95,1.05);vs=number(viscosityScale,'Viscosity scale',.9,1.1)
    if p*1e6 < iapws95_Psat(t+273.15): raise ValueError('Pressure is below the conservative pure-water saturation limit. Use a liquid state.')
    L=sum(a*(20-t)**i for i,a in enumerate([1.2378,-.001303,3.06e-6,2.55e-8],1))/(96+t)
    A=.03324*m+.003624*m*m-.0001879*m**3;B=-.0396*m+.0102*m*m-.000702*m**3
    bw=-1.297+.0574*t-.000697*t*t+4.47e-6*t**3-1.05e-8*t**4
    ms=6.044+.0028*t+.000036*t*t;r=m/ms
    beta=bw+(.545+.0028*t-bw)*(2.5*r-2*r*r+.5*r**3)
    mu=1.002*10**(L+A+B*L)*(1+beta*p/1000)*vs
    def volume(temp,pressure):
        T=temp+273.15;w=m*.05844277/(1+m*.05844277)
        a=sum(c*T**i for i,c in zip(range(-2,3),[100.6741,-1.127522,.005916365,-1.035794e-5,9.270048e-9]))
        b=sum(c*T**i for i,c in zip(range(-2,3),[1.042948,-.011933677,5.307535e-5,-1.0688768e-7,8.492739e-11]))
        c=1.23268e-9-6.861928e-12*T
        d=-.0025166+1.11766e-5*T-1.70552e-8*T*T
        e=.00284851-1.54305e-5*T+2.23982e-8*T*T
        f=-1.5106e-5+8.4605e-8*T-1.2715e-10*T*T
        g=2.7676e-5-1.5694e-7*T+2.3102e-10*T*T
        h=6.4633e-8-4.1671e-10*T+6.8599e-13*T*T
        # The concentration factor in the quadratic salt term is essential.
        # Verified against the published dynamic/kinematic table ratios.
        v=a-b*pressure-c*pressure**2+w*d+w*w*e-w*f*pressure-w*w*g*pressure-.5*w*h*pressure**2
        dv=-b-2*c*pressure-w*f-w*w*g-w*h*pressure
        return v,dv
    v,dv=volume(t,p);vref,_=volume(20,.1)
    if v<=0 or dv>=0: raise ValueError('Unphysical brine volume or compressibility.')
    rho=ds/v
    return dict(temperature=t,pressure=p,molality=m,density=rho,viscosity=mu,kinematicViscosity=mu*1000/rho,Bw=v/vref,compressibility=-dv/v,saltMassPercent=100*m*.05844277/(1+m*.05844277))

def wax_components(rows):
    if not isinstance(rows,list) or not 2<=len(rows)<=30: raise ValueError('Use 2–30 wax/carrier components.')
    out=[]
    for c in rows:
        c=copy.deepcopy(c);c['name']=str(c.get('name','')).strip()[:100]
        if not c['name']: raise ValueError('Each component needs a name.')
        c['MW']=number(c.get('MW'),'Molecular weight g/mol',10,3000)
        c['massFraction']=number(c.get('massFraction'),'Mass fraction',0,1)
        if not isinstance(c.get('solid'),bool): raise ValueError('solid must be true or false.')
        if c['solid']:
            c['Tm']=number(c.get('Tm'),'Crystallization / melting temperature K',200,500)
            c['H']=number(c.get('H'),'Transition enthalpy J/mol',1000,400000)
            c['Htr']=number(c.get('Htr',0),'Solid transition enthalpy J/mol',0,100000)
            c['Ttr']=number(c.get('Ttr',200),'Solid transition temperature K',100,c['Tm'])
            c['deltaCp']=number(c.get('deltaCp',0),'Liquid minus solid heat capacity J/mol/K',-500,500)
            c['deltaV']=number(c.get('deltaV',0),'Solid minus liquid molar volume m³/mol',-.001,.001)
        out.append(c)
    if len({c['name'] for c in out})!=len(out): raise ValueError('Component names must be unique.')
    if abs(sum(c['massFraction'] for c in out)-1)>1e-8: raise ValueError('Mass fractions must sum to 1; no silent normalization.')
    if sum(c['massFraction'] for c in out if not c['solid'])<1e-6: raise ValueError('A noncrystallizing liquid carrier is required.')
    if not any(c['solid'] and c['massFraction']>0 for c in out): raise ValueError('Include at least one wax component.')
    return out

def wax_log_solubility(c,T,p,scale):
    out=scale*c['H']/R*(1/c['Tm']-1/T)+c['deltaCp']/R*(c['Tm']/T-1+math.log(T/c['Tm']))
    if T<c['Ttr']:out+=scale*c['Htr']/R*(1/c['Ttr']-1/T)
    return out+c['deltaV']*(p-.1)*1e6/(R*T)

def wax_state(components,t,p=.1,enthalpyScale=1):
    c= wax_components(components);T=number(t,'Temperature °C',-50,200)+273.15;p=number(p,'Pressure MPa',.1,100)
    scale=number(enthalpyScale,'Enthalpy multiplier',.7,1.3)
    moles=np.array([r['massFraction']/r['MW'] for r in c]);z=moles/sum(moles);mw=np.array([r['MW'] for r in c])
    k=np.array([math.exp(max(-700,min(700,wax_log_solubility(r,T,p,scale)))) if r['solid'] else 1e100 for r in c])
    carrier=sum(z[i] for i,r in enumerate(c) if not r['solid'])
    fun=lambda L:sum(np.minimum(z,L*k))-L
    L=1. if fun(1.)>=-1e-14 else brentq(fun,carrier,1,xtol=1e-14)
    n=np.minimum(z,L*k);s=z-n;x=n/L
    balance=float(max(abs(z-n-s)))
    if abs(sum(x)-1)>1e-8 or balance>1e-10: raise ValueError('Wax material balance failed.')
    return dict(temperature=t,pressure=p,waxMassPercent=float(100*np.dot(s,mw)/np.dot(z,mw)),liquidMoleFraction=L,balance=balance,components=[dict(name=r['name'],feedMoles=float(z[i]),liquidMoles=float(n[i]),solidMoles=float(s[i]),liquidComposition=float(x[i])) for i,r in enumerate(c)])

def wax_onset(components,p=.1,enthalpyScale=1):
    c=wax_components(components);p=number(p,'Pressure MPa',.1,100);scale=number(enthalpyScale,'Enthalpy multiplier',.7,1.3)
    moles=np.array([r['massFraction']/r['MW'] for r in c]);z=moles/sum(moles);roots=[]
    for r,zi in zip(c,z):
        if not r['solid'] or zi==0:continue
        f=lambda T:wax_log_solubility(r,T,p,scale)-math.log(zi)
        # Bracket all crossings, rather than assuming monotonicity with arbitrary Cp inputs.
        ts=np.linspace(223.15,473.15,151)
        for a,b in zip(ts[:-1],ts[1:]):
            if f(a)*f(b)<=0:roots.append(brentq(f,a,b)-273.15)
    return max(roots) if roots else None

# Pure-liquid properties at 298.15 K / 0.1 MPa from thermo 0.6.1 Chemical,
# HEOS_FIT volume and vaporization enthalpy; delta=sqrt((Hvap-RT)/Vm).
CARRIERS={
 'toluene':dict(MW=92.13842,rho=862.3391830080506,delta=18.24328797618057),
 'pentane':dict(MW=72.14878,rho=621.2559132733339,delta=14.362647937568972),
 'heptane':dict(MW=100.20194,rho=679.7205861114508,delta=15.20821810430986),
 'decane':dict(MW=142.28168,rho=726.6229692565404,delta=15.80118790251466)}

def fh_binodal(N,chi):
    N=number(N,'Asphaltene/carrier volume ratio',1.01,1000);chi=number(chi,'FH interaction',0,100)
    critical=.5*(1+1/math.sqrt(N))**2
    if chi<=critical*(1+1e-9):return None
    sl,sh=np.sort(np.roots([2*chi*N,N-1-2*chi*N,1]))
    def residual(y):
        l=math.exp(y[0]);q=math.exp(y[1]);h=1-q
        return [math.log1p(-l)+(1-1/N)*l+chi*l*l-(y[1]+(1-1/N)*h+chi*h*h),
         (y[0]+(1-N)*(1-l)+N*chi*(1-l)**2-(math.log1p(-q)+(1-N)*q+N*chi*q*q))/N]
    upper=np.log([sl,1-sh])-1e-10
    mid=(sl+sh)/2;gap=(sh-sl)*.9
    start=np.log([max(1e-100,mid-gap),max(1e-100,1-mid-gap)])
    fit=least_squares(residual,np.minimum(start,upper-1e-8),bounds=([-700,-700],upper),gtol=1e-15,xtol=1e-13,ftol=1e-13,max_nfev=300)
    l=math.exp(fit.x[0]);h=-math.expm1(fit.x[1]);err=max(abs(x) for x in residual(fit.x))
    if not fit.success or err>1e-7 or not l<sl<sh<h: raise ValueError('Asphaltene common-tangent calculation did not converge.')
    return dict(lean=l,rich=h,residual=err,logLean=float(fit.x[0]))

def asph_state(wp,wa,precipitant='heptane',delta=21.6,volume=.002,density=1200):
    wp=number(wp,'Precipitant mass fraction',0,.98);wa=number(wa,'Asphaltene mass fraction',1e-8,.2)
    if wp+wa>=1:raise ValueError('Leave a positive toluene mass fraction.')
    if precipitant not in ('pentane','heptane','decane'):raise ValueError('Choose pentane, heptane or decane.')
    delta=number(delta,'Asphaltene solubility parameter MPa½',19,30);volume=number(volume,'Asphaltene molar volume m³/mol',.0005,.05);density=number(density,'Asphaltene density kg/m³',1000,1500)
    pc=CARRIERS[precipitant];sc=CARRIERS['toluene'];ws=1-wp-wa
    vp=wp/pc['rho'];vs=ws/sc['rho'];va=wa/density;phi=va/(va+vp+vs)
    vm=(vp+vs)/(wp/(pc['MW']/1000)+ws/(sc['MW']/1000));dm=(vp*pc['delta']+vs*sc['delta'])/(vp+vs)
    N=volume/vm;chi=vm*(dm-delta)**2*1e6/R/298.15;b=fh_binodal(N,chi)
    split=0.;gain=0.;lean=rich=phi;res=0.
    if b:
        lean=b['lean'];rich=b['rich'];res=b['residual']
        if lean<phi<rich:
            split=(phi-lean)/(rich-lean)
            def g(x):return x/N*math.log(x)+(1-x)*math.log1p(-x)+chi*x*(1-x)
            gain=g(phi)-((1-split)*g(lean)+split*g(rich))
            if gain < -1e-10:raise ValueError('Unstable asphaltene split: Gibbs energy increased.')
    # Outside the miscibility gap, no separate precipitate phase is assigned.
    balance=abs((1-split)*lean+split*rich-phi) if split else 0.
    return dict(precipitant=precipitant,precipitantMassFraction=wp,asphalteneMassFraction=wa,feedVolumeFraction=phi,leanVolumeFraction=lean,richVolumeFraction=rich,richPhaseVolumeFraction=split,asphalteneSeparatedPercent=100*split*rich/phi,asphalteneMassPercent=100*wa*split*rich/phi,chemicalPotentialResidual=res,balance=balance,gibbsReduction=gain,N=N,chi=chi,onsetResidual=math.log(phi)-b['logLean'] if b else None,state='two liquid phases' if split else 'single liquid phase')

def asph_onset(wa0,precipitant,delta,volume,density=1200):
    # wa0 is mass fraction in starting asphaltene+toluene stock. Diluent is
    # then added: wa=wa0*(1-wp), preserving the stock solvent/asphaltene ratio.
    wa0=number(wa0,'Stock asphaltene mass fraction',.00001,.2)
    def f(w):
        a=asph_state(w,wa0*(1-w),precipitant,delta,volume,density)
        return a['onsetResidual'] if a['onsetResidual'] is not None else -100.
    grid=np.linspace(0,.95,41)
    if f(0)>=0:return dict(pressure=None,precipitantMassFraction=0,status='Stock already at or beyond onset')
    for a,b in zip(grid[:-1],grid[1:]):
        if f(a)<0<=f(b):return dict(precipitantMassFraction=brentq(f,a,b,xtol=1e-9),status='Onset found')
    return dict(precipitantMassFraction=None,status='No onset within 0–95 wt% precipitant')

def physical_dispatch(req):
    s=copy.deepcopy(req.get('study',{}));kind=s.get('kind');action=req.get('action','calculate')
    if kind not in ('brine','wax','asphaltene'):raise ValueError('Unknown physical model.')
    if action not in ('calculate','fit'):raise ValueError('Unknown physical model action.')
    if not str(s.get('sample','')).strip() or not str(s.get('source','')).strip():raise ValueError('Sample identity and source are required.')
    obs=s.get('observations',[])
    if not isinstance(obs,list) or len(obs)>100:raise ValueError('Use at most 100 observations.')
    for o in obs:
        if o.get('role') not in ('training','validation','reference'):raise ValueError('Observation role must be training, validation or reference.')
    params=s.setdefault('parameters',{})
    keys={'brine':['densityScale','viscosityScale'],'wax':['enthalpyScale'],'asphaltene':['delta','volume']}[kind]
    defaults={'densityScale':1,'viscosityScale':1,'enthalpyScale':1,'delta':21.6,'volume':.002}
    bounds={'densityScale':(.95,1.05),'viscosityScale':(.9,1.1),'enthalpyScale':(.7,1.3),'delta':(19,30),'volume':(.0005,.05)}
    for k in keys:params[k]=number(params.get(k,defaults[k]),k,*bounds[k])
    if kind=='asphaltene':params['density']=number(params.get('density',1200),'Asphaltene density',1000,1500)
    def prediction(o,par):
        if kind=='brine':
            if o.get('property') not in ('density','viscosity'):raise ValueError('Brine observations need density or viscosity.')
            return brine(o.get('temperature'),o.get('pressure'),o.get('molality'),**par)[o['property']]
        if kind=='wax':
            cs=copy.deepcopy(s['components']);fraction=number(o.get('massFraction'),'Measured binary wax mass fraction',.00001,.8)
            if len(cs)!=2 or cs[0]['solid'] or not cs[1]['solid']:raise ValueError('Wax fitting requires carrier first and one wax second; multicomponent prediction remains available.')
            cs[0]['massFraction']=1-fraction;cs[1]['massFraction']=fraction
            val=wax_onset(cs,o.get('pressure',.1),par['enthalpyScale'])
            if val is None:raise ValueError('Wax onset is outside the supported temperature range.')
            return val
        wp=number(o.get('measured'),'Measured precipitant mass fraction',.001,.94);wa=number(o.get('asphalteneMassFraction'),'Measured asphaltene mass fraction',.00001,.2)
        onset=asph_onset(wa/(1-wp),o.get('precipitant'),par['delta'],par['volume'],par['density'])
        if onset['precipitantMassFraction'] is None:raise ValueError('No predicted onset for an observation.')
        return onset['precipitantMassFraction']
    fitinfo=None
    if action=='fit':
        train=[o for o in obs if o['role']=='training']
        if kind=='brine':keys=[k for k in keys if any(o.get('property')==('density' if k=='densityScale' else 'viscosity') for o in train)]
        if not keys or len(train)<len(keys)+2:raise ValueError('Need at least parameter count + 2 training observations. Reference tables are not independent measurements.')
        if kind=='brine' and any(sum(o.get('property')==('density' if k=='densityScale' else 'viscosity') for o in train)<2 for k in keys):raise ValueError('Each brine scale needs at least two training measurements.')
        scales=np.array([.002 if k=='volume' else 1 for k in keys]);lo=np.array([bounds[k][0] for k in keys])/scales;hi=np.array([bounds[k][1] for k in keys])/scales
        def unpack(x):return dict(params,**dict(zip(keys,x*scales)))
        def residual(x):
            par=unpack(x);out=[]
            for o in train:
                measured=number(o.get('measured'),'Measured value',-50 if kind=='wax' else 1e-10,10000)
                if kind=='asphaltene':
                    state=asph_state(measured,o.get('asphalteneMassFraction'),o.get('precipitant'),par['delta'],par['volume'],par['density'])
                    # Fit the saturation equality directly; displayed errors use
                    # predicted onset with the stock composition held constant.
                    val=state['onsetResidual']
                    if val is None:val=-3-10*(.5*(1+1/math.sqrt(state['N']))**2-state['chi'])
                    out.append(val)
                else:out.append((prediction(o,par)-measured)/(measured if kind=='brine' else 1))
            return out
        fit=least_squares(residual,np.array([params[k] for k in keys])/scales,bounds=(lo,hi),max_nfev=120,ftol=1e-10,xtol=1e-10,gtol=1e-10)
        sv=np.linalg.svd(fit.jac,compute_uv=False);rank=int(sum(sv>sv[0]*1e-7)) if len(sv) and sv[0]>0 else 0
        hits=[k for i,k in enumerate(keys) if min(fit.x[i]-lo[i],hi[i]-fit.x[i]) < 1e-4*(hi[i]-lo[i])]
        params.update(unpack(fit.x));fitinfo=dict(converged=bool(fit.success),rank=rank,parameterCount=len(keys),condition=float(sv[0]/sv[-1]) if len(sv) and sv[-1]>1e-15 else None,boundHits=hits,eligible=bool(fit.success and rank==len(keys) and not hits),parameters={k:params[k] for k in keys},objective='Log saturation equality' if kind=='asphaltene' else 'Relative residual' if kind=='brine' else 'Temperature residual °C')
    checks=[]
    for o in obs:
        measured=number(o.get('measured'),'Measured value',-50 if kind=='wax' else 1e-10,10000);pred=prediction(o,params)
        checks.append(dict(o,predicted=pred,error=pred-measured))
    metrics=[]
    for role in ('training','validation','reference'):
        for prop in sorted({o.get('property',kind) for o in checks}):
            group=[o for o in checks if o['role']==role and o.get('property',kind)==prop]
            if group:metrics.append(dict(role=role,property=prop,n=len(group),rmse=float(np.sqrt(np.mean([o['error']**2 for o in group]))),maxAbsoluteError=max(abs(o['error']) for o in group)))
    c=s.get('conditions',{});sweep=s.get('sweep',{});count=number(sweep.get('points',41),'Sweep points',2,101)
    if count!=int(count):raise ValueError('Sweep points must be a whole number.')
    count=int(count)
    if kind=='brine':
        state=brine(c.get('temperature'),c.get('pressure'),c.get('molality'),**params)
        low=number(sweep.get('min',.5),'Sweep minimum pressure MPa',.1,35);high=number(sweep.get('max',35),'Sweep maximum pressure MPa',low,35)
        rows=[brine(c['temperature'],float(p),c['molality'],**params) for p in np.linspace(low,high,count)];onset=None
    elif kind=='wax':
        state=wax_state(s.get('components'),c.get('temperature'),c.get('pressure',.1),**params)
        low=number(sweep.get('min',20),'Sweep minimum temperature °C',-50,200);high=number(sweep.get('max',100),'Sweep maximum temperature °C',low,200)
        rows=[wax_state(s['components'],float(t),c.get('pressure',.1),**params) for t in np.linspace(low,high,count)];onset=wax_onset(s['components'],c.get('pressure',.1),**params)
    else:
        if number(c.get('temperature',25),'Asphaltene temperature',25,25)!=25 or number(c.get('pressure',.1),'Asphaltene pressure',.1,.1)!=.1:raise ValueError('Asphaltene reference properties apply at 25 °C and 0.1 MPa only.')
        stock=number(c.get('stockAsphaltene',.02),'Stock asphaltene mass fraction',.00001,.2);wp=number(c.get('precipitantMassFraction',.5),'Precipitant fraction',0,.95);prec=c.get('precipitant','heptane')
        state=asph_state(wp,stock*(1-wp),prec,**params)
        low=number(sweep.get('min',0),'Sweep minimum precipitant fraction',0,.95);high=number(sweep.get('max',.9),'Sweep maximum precipitant fraction',low,.95)
        rows=[asph_state(float(w),stock*(1-w),prec,**params) for w in np.linspace(low,high,count)];onset=asph_onset(stock,prec,**params)
    return dict(kind=kind,study=s,fit=fitinfo,state=state,onset=onset,rows=rows,checks=checks,metrics=metrics)
