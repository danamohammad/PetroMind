// Experimental facts are attributed in each case; no simulated curves are treated as measurements.
const waxSource = {
  title: 'Tai et al. (2026), ACS Omega 11, 5051–5062, Table 5',
  url: 'https://doi.org/10.1021/acsomega.5c06286',
  license: 'CC BY 4.0',
  method: 'HPμDSC, cooling at 0.8 K/min; first crystallization event. Means and sample standard deviations from triplicates. Pressure is gauge, as specified in the experimental procedure.',
};
const pressures = [0.1, 2.5, 5, 7.5, 10, 12.5, 15, 20];
function wax(id, name, gas, values, deviations) {
  return {format:'PetroMind Flow Study', version:1, id, kind:'wax', name,
    sample:'Brazilian presalt dead crude oil studied by Tai et al.; field and cylinder not identified',
    condition:gas, source:{...waxSource},
    notes:'Gas was introduced into dead oil in the calorimeter. This is not the Halfaya or Sarta live fluid. PetroMind selected 2.5 and 12.5 MPag as held-out checks; the remaining points fit a pressure trend. Error bars are experimental standard deviations, not model confidence intervals.',
    rows:pressures.map((x,i)=>({x,y:Math.round((values[i]-273.15)*100)/100,sd:deviations[i],role:[1,5].includes(i)?'validation':'training'})),
    origin:'published'};
}
export const publishedCases = [
  wax('presalt-ng','Wax · Brazilian presalt / natural gas','Natural-gas pressurization; gas composition in source Table 4',
    [327.71,327.63,327.23,326.25,326.22,325.29,324.85,324.28],[.96,.46,.35,.74,.45,.63,.76,.91]),
  wax('presalt-n2','Wax · Brazilian presalt / nitrogen','Nitrogen pressurization',
    [328.26,328.53,328.85,329.08,329.41,329.73,330.01,330.95],[.71,.69,.60,.47,.48,.52,.56,.47]),
  {format:'PetroMind Flow Study',version:1,id:'halfaya-sadi-hfx1',kind:'asphaltene',name:'Asphaltene · Halfaya Sadi / HFx1',
    sample:'Halfaya Sadi formation, well HFx1; bottomhole sample, 8 September 2011, 10:30',
    condition:'Upper asphaltene onset on pressure reduction',origin:'published',
    source:{title:'Ali, Al-Jawad & Ali (2019), Journal of Engineering 25(8), 113–128; pp. 117 and 122',url:'https://doi.org/10.31026/j.eng.2019.08.08',license:'Article: CC BY-NC 4.0; numerical facts transcribed with attribution',method:'Measured upper onset reported from the HFx1 PVT/flow-assurance report. Temperature converted from 186.98 °F. No experimental uncertainty supplied.'},
    notes:'Different well, formation and sample from HF-003 / 28873-IB and Sarta. One measured onset cannot identify an onset curve, a lower boundary or precipitated mass. The paper’s simulated envelope is not experimental validation data.',
    rows:[{x:86.1,y:7015,sd:null,role:'reference'}],
    operatingPoint:{temperature:86.1,pressure:4406.6,bubblePressure:3125}}
];

export const axes = {
  wax:{x:'Pressure · MPag',y:'Wax appearance · °C',xUnit:'MPag',yUnit:'°C'},
  asphaltene:{x:'Temperature · °C',y:'Upper asphaltene onset · psia',xUnit:'°C',yUnit:'psia'}
};
function number(value,name){if(value===null||value===''||typeof value==='boolean'||!Number.isFinite(Number(value)))throw Error(`${name} must be a finite number.`);return Number(value)}
export function validateStudy(input){
  if(!input||input.format!=='PetroMind Flow Study'||input.version!==1||!axes[input.kind])throw Error('Use a PetroMind Flow Study version 1 with kind wax or asphaltene.');
  const s=structuredClone(input);
  for(const k of ['name','sample','condition'])if(typeof s[k]!=='string'||!s[k].trim()||s[k].length>1000)throw Error(`Enter a valid ${k}.`);
  if(!Array.isArray(s.rows)||s.rows.length<1||s.rows.length>200)throw Error('Use 1–200 observations.');
  const seen=new Set();
  s.rows=s.rows.map((r,i)=>{
    const x=number(r.x,`Row ${i+1} coordinate`),y=number(r.y,`Row ${i+1} measurement`);
    if(s.kind==='wax'?(x<0||x>200||y<=-273.15||y>600):(x<=-273.15||x>600||y<=0||y>100000))throw Error(`Row ${i+1} is outside supported units/ranges.`);
    if(seen.has(x))throw Error('Use one mean observation per condition; do not treat replicates as independent pressure or temperature levels.');seen.add(x);
    if(!['training','validation','reference'].includes(r.role))throw Error(`Row ${i+1} needs a valid role.`);
    const sd=r.sd===null||r.sd===''||r.sd===undefined?null:number(r.sd,`Row ${i+1} standard deviation`);
    if(sd!==null&&sd<=0)throw Error('Standard deviations must be positive, or blank if unknown.');
    return {x,y,sd,role:r.role};
  }).sort((a,b)=>a.x-b.x);
  return s;
}
export function fitTrend(input){
  const study=validateStudy(input),train=study.rows.filter(r=>r.role==='training');
  if(train.length<4)throw Error('Fit needs at least four distinct training conditions for two coefficients. A single onset stays a reference point.');
  const weighted=train.every(r=>r.sd!==null);
  if(!weighted&&train.some(r=>r.sd!==null))throw Error('Supply all training standard deviations, or leave all blank for equal weighting.');
  const weights=train.map(r=>weighted?1/r.sd**2:1),sum=weights.reduce((a,b)=>a+b,0);
  const x0=train.reduce((a,r,i)=>a+weights[i]*r.x,0)/sum,y0=train.reduce((a,r,i)=>a+weights[i]*r.y,0)/sum;
  const xx=train.reduce((a,r,i)=>a+weights[i]*(r.x-x0)**2,0);
  if(!(xx>1e-12*sum))throw Error('Training coordinates do not distinguish slope and intercept.');
  const slope=train.reduce((a,r,i)=>a+weights[i]*(r.x-x0)*(r.y-y0),0)/xx;
  const intercept=y0-slope*x0,lo=Math.min(...train.map(r=>r.x)),hi=Math.max(...train.map(r=>r.x));
  if(!Number.isFinite(slope)||!Number.isFinite(intercept))throw Error('Fit is numerically ill-conditioned.');
  const predict=x=>x>=lo&&x<=hi?y0+slope*(x-x0):null;
  const comparisons=study.rows.map(r=>({...r,predicted:predict(r.x),error:predict(r.x)===null?null:predict(r.x)-r.y}));
  const metric=role=>{
    const r=comparisons.filter(r=>r.role===role&&r.error!==null);
    return {count:r.length,rmse:r.length?Math.sqrt(r.reduce((s,r)=>s+r.error**2,0)/r.length):null,maxError:r.length?Math.max(...r.map(r=>Math.abs(r.error))):null};
  };
  return {method:weighted?'Weighted linear least squares (1 / SD²)':'Equal-weight linear least squares',intercept,slope,x0,y0,domain:[lo,hi],training:metric('training'),validation:metric('validation'),comparisons,curve:Array.from({length:81},(_,i)=>{const x=lo+(hi-lo)*i/80;return{x,y:predict(x)}}),study};
}
export function predictTrend(fit,x){x=number(x,'Query coordinate');if(x<fit.domain[0]||x>fit.domain[1])throw Error('Outside the training range. Extrapolation is disabled.');return fit.y0+fit.slope*(x-fit.x0)}
export function onsetComparison(input,temperature,pressure){
  const s=validateStudy(input);if(s.kind!=='asphaltene')throw Error('An asphaltene study is required.');
  temperature=number(temperature,'Temperature');pressure=number(pressure,'Pressure');if(pressure<=0)throw Error('Pressure must be positive psia.');
  // Only coordinate equality within floating-point roundoff; a lone point defines no T tolerance band.
  const point=s.rows.find(r=>Math.abs(r.x-temperature)<1e-8);
  if(!point)throw Error('No measured onset at this temperature. A single-temperature measurement cannot be extrapolated.');
  return {temperature,pressure,onset:point.y,margin:pressure-point.y,statement:pressure<point.y?'Below the measured upper onset. Lower onset and precipitated quantity are unknown.':pressure>point.y?'Above the measured upper onset. This comparison is not a deposition or operating-safety assessment.':'At the measured upper onset.'};
}
