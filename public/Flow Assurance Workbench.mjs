import {publishedCases,axes,validateStudy} from './Flow Assurance Data.mjs';

export function initializeFlowAssurance({download,csv,error,toast,callEngine}){
  const $=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=x=>x===null||x===undefined?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:4});
  let study=structuredClone(publishedCases[0]),fit=null,comparison=null;
  const key='PetroMind Flow Assurance Studies v1';
  const safeUrl=url=>{try{const u=new URL(url);return ['https:','http:'].includes(u.protocol)?u.href:''}catch{return ''}};
  function saved(){try{const x=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(x)?x:[]}catch{return []}}
  function refreshOptions(){
    $('flowCase').innerHTML='<optgroup label="Published reference cases">'+publishedCases.map((s,i)=>`<option value="public:${i}">${esc(s.name)}</option>`).join('')+'</optgroup><optgroup label="Your saved studies">'+saved().map((s,i)=>`<option value="saved:${i}">${esc(s.name)}</option>`).join('')+'</optgroup>';
  }
  function invalidate(){fit=null;comparison=null;$('flowResults').innerHTML='';$('flowExportResults').disabled=true;$('flowQueryResult').textContent='';$('flowFitStatus').textContent='Measurements changed · run the fit or comparison again.';}
  function edit(){study.origin='user-edited';invalidate();$('flowOrigin').textContent='User-edited study · source retained for provenance; edited values are not verified publication data.';}
  function readMetadata(){study.name=$('flowName').value;study.sample=$('flowSample').value;study.condition=$('flowCondition').value;}
  function render(){
    invalidate();const a=axes[study.kind];
    $('flowName').value=study.name;$('flowSample').value=study.sample;$('flowCondition').value=study.condition;
    $('flowOrigin').textContent=study.origin==='published'?'Published experimental reference · independent of your active EOS project':'User study · verify sample identity and source before fitting';
    const source=study.source||{},url=safeUrl(source.url);
    $('flowSource').innerHTML=`<p>${url?`<a href="${esc(url)}" target="_blank" rel="noopener">${esc(source.title||url)} ↗</a>`:esc(source.title||'User-entered data')}</p><p>${esc(source.method||'Measurement method not supplied')}</p><p>${esc(source.license||'')}</p><p>${esc(study.notes||'')}</p>`;
    $('flowRows').innerHTML=`<table><thead><tr><th>${a.x}</th><th>${a.y}</th><th>SD · ${a.yUnit}</th><th>Role</th><th></th></tr></thead><tbody>${study.rows.map((r,i)=>`<tr><td><input type="number" step="any" data-flow-row="${i}" data-key="x" aria-label="Condition ${i+1}" value="${esc(r.x)}"></td><td><input type="number" step="any" data-flow-row="${i}" data-key="y" aria-label="Measured value ${i+1}" value="${esc(r.y)}"></td><td><input type="number" step="any" min="0" data-flow-row="${i}" data-key="sd" aria-label="Standard deviation ${i+1}" value="${esc(r.sd)}"></td><td><select data-flow-row="${i}" data-key="role" aria-label="Observation role ${i+1}">${['training','validation','reference'].map(role=>`<option ${role===r.role?'selected':''}>${role}</option>`).join('')}</select></td><td><button class="remove-row" data-flow-remove="${i}" aria-label="Remove observation ${i+1}">×</button></td></tr>`).join('')}</tbody></table>`;
    $('flowOnsetControls').classList.toggle('hidden',study.kind!=='asphaltene');
    $('flowQueryLabel').textContent=a.x;$('flowQuery').value=study.kind==='wax'?10:study.rows[0]?.x??86.1;
    $('flowCheckTemperature').value=study.operatingPoint?.temperature??study.rows[0]?.x??86.1;
    $('flowCheckPressure').value=study.operatingPoint?.pressure??4406.6;
    $('flowFitStatus').textContent=study.kind==='wax'?'Fit a two-coefficient pressure trend; review held-out errors before using it.':'The supplied Halfaya case has one measured onset. Compare at that temperature; no fitted curve is claimed.';
    draw();
  }
  function draw(){
    const a=axes[study.kind],colors={training:'#075184',validation:'#cc4b00',reference:'#075184'};
    const traces=['training','validation','reference'].map(role=>{const rows=study.rows.filter(r=>r.role===role&&r.x!==''&&r.y!==''&&Number.isFinite(Number(r.x))&&Number.isFinite(Number(r.y)));return {x:rows.map(r=>Number(r.x)),y:rows.map(r=>Number(r.y)),mode:'markers',name:role==='validation'?'Held-out data':role==='training'?'Training data':'Measured onset',marker:{size:11,color:colors[role],symbol:role==='validation'?'diamond-open':'circle'},error_y:{type:'data',array:rows.map(r=>r.sd===null||r.sd===''?0:Number(r.sd)),visible:rows.some(r=>r.sd!==null&&r.sd!==''),color:'#000'}}}).filter(t=>t.x.length);
    if(fit)traces.push({x:fit.curve.map(r=>r.x),y:fit.curve.map(r=>r.y),mode:'lines',name:'Fitted trend',line:{color:'#008ba8',width:3}});
    if(comparison)traces.push({x:[comparison.temperature],y:[comparison.pressure],mode:'markers',name:'Comparison pressure',marker:{color:'#cc4b00',symbol:'diamond',size:13}});
    Plotly.react('flowChart',traces,{margin:{t:20,b:90,l:85,r:30},font:{family:'Arial, sans-serif',size:16,color:'#000',weight:700},xaxis:{title:{text:a.x},zeroline:false,gridcolor:'#e5edf2'},yaxis:{title:{text:a.y},zeroline:false,gridcolor:'#e5edf2'},legend:{orientation:'h',y:-.22},paper_bgcolor:'#fff',plot_bgcolor:'#fff'},{responsive:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d','select2d','sendDataToCloud','sendChartToCloud'],toImageButtonOptions:{filename:'PetroMind Flow Assurance'}});
  }
  function metric(label,value,unit=''){return `<div class="metric"><div class="label">${esc(label)}</div><div class="value">${fmt(value)}</div><div class="unit">${esc(unit)}</div></div>`}
  async function runFit(){try{
    readMetadata();const input=structuredClone(study),out=await callEngine('data',{kind:'flowFit',study:input});if(JSON.stringify(input)!==JSON.stringify(study))throw Error('Study changed; fit again.');fit=out;study=fit.study;comparison=null;const a=axes[study.kind];
    $('flowFitStatus').textContent=`${fit.method}. Fits ${fit.training.count} conditions; checks ${fit.validation.count} held-out conditions within the training range.`;
    $('flowResults').innerHTML=`<div class="metric-grid">${metric('Training RMSE',fit.training.rmse,a.yUnit)}${metric('Held-out RMSE',fit.validation.rmse,a.yUnit)}${metric('Largest held-out error',fit.validation.maxError,a.yUnit)}</div><article class="panel padded"><h3>Calibrated empirical trend</h3><p>${esc(a.y)} = ${fmt(fit.intercept)} + (${fmt(fit.slope)}) × ${esc(a.x)}.</p><p>Valid only for this named sample and test condition, from ${fmt(fit.domain[0])} to ${fmt(fit.domain[1])} ${a.xUnit}. This regression does not alter your EOS or represent a solid-phase equilibrium model. ${fit.validation.count?'Held-out checks come from the same experimental study; they are not independent field validation.':'No in-range held-out measurements: validation is unavailable.'}</p><p>No confidence band is inferred from the reported replicate scatter. Points outside the training range are left unpredicted.</p><div class="scroll-table"><table><thead><tr><th>${a.x}</th><th>Measured · ${a.yUnit}</th><th>Fitted · ${a.yUnit}</th><th>Residual · ${a.yUnit}</th><th>Role</th></tr></thead><tbody>${fit.comparisons.map(r=>`<tr><td>${fmt(r.x)}</td><td>${fmt(r.y)}</td><td>${fmt(r.predicted)}</td><td>${fmt(r.error)}</td><td>${esc(r.role)}</td></tr>`).join('')}</tbody></table></div></article>`;
    $('flowExportResults').disabled=false;$('flowQueryResult').textContent='';draw();
  }catch(e){invalidate();error(e)}}
  $('flowRows').oninput=e=>{const {flowRow,key:k}=e.target.dataset;if(flowRow===undefined)return;study.rows[Number(flowRow)][k]=e.target.value;edit();draw();};
  $('flowRows').onchange=e=>{if(e.target.dataset.flowRow!==undefined)draw()};
  $('flowRows').onclick=e=>{const b=e.target.closest('[data-flow-remove]');if(!b)return;study.rows.splice(Number(b.dataset.flowRemove),1);edit();render();};
  for(const id of ['flowName','flowSample','flowCondition'])$(id).oninput=()=>{readMetadata();edit();draw()};
  $('flowLoad').onclick=()=>{try{const [type,index]=$('flowCase').value.split(':');study=validateStudy(type==='public'?publishedCases[Number(index)]:saved()[Number(index)]);render();toast('Flow study loaded. Your active EOS project is unchanged.')}catch(e){error(e)}};
  $('flowAdd').onclick=()=>{study.rows.push({x:'',y:'',sd:null,role:'training'});edit();render()};
  $('flowFit').onclick=runFit;
  $('flowQueryButton').onclick=async()=>{try{if(!fit)throw Error('Fit the current observations first.');const input=JSON.stringify(study),x=$('flowQuery').value,value=await callEngine('data',{kind:'flowPredict',study:structuredClone(study),x});if(input!==JSON.stringify(study)||x!==$('flowQuery').value)throw Error('Inputs changed; predict again.');$('flowQueryResult').textContent=`Fitted ${axes[study.kind].y}: ${fmt(value)}. Applies only to ${study.sample} / ${study.condition}.`}catch(e){$('flowQueryResult').textContent='';error(e)}};
  $('flowCheck').onclick=async()=>{try{readMetadata();const input=JSON.stringify(study),temperature=$('flowCheckTemperature').value,pressure=$('flowCheckPressure').value,out=await callEngine('data',{kind:'flowOnset',study:structuredClone(study),temperature,pressure});if(input!==JSON.stringify(study)||temperature!==$('flowCheckTemperature').value||pressure!==$('flowCheckPressure').value)throw Error('Inputs changed; compare again.');comparison=out;fit=null;$('flowQueryResult').textContent='';$('flowResults').innerHTML=`<div class="metric-grid">${metric('Measured upper onset',comparison.onset,'psia')}${metric('Comparison pressure',comparison.pressure,'psia')}${metric('Pressure minus onset',comparison.margin,'psi')}</div><div class="notice"><div>${esc(comparison.statement)} The measurement applies to ${esc(study.sample)} at ${fmt(comparison.temperature)} °C. No lower boundary or precipitation amount is available.</div></div>`;$('flowFitStatus').textContent='Measured-point comparison · no parameter fit or envelope validation';$('flowExportResults').disabled=false;draw()}catch(e){invalidate();error(e)}};
  for(const id of ['flowCheckTemperature','flowCheckPressure'])$(id).oninput=()=>{invalidate();draw()};
  $('flowQuery').oninput=()=>$('flowQueryResult').textContent='';
  $('flowSave').onclick=()=>{try{readMetadata();const s=validateStudy(study),items=saved();items.push({...s,savedAt:new Date().toISOString()});if(items.length>100)throw Error('Export your studies; this browser already contains 100 saved copies.');localStorage.setItem(key,JSON.stringify(items));refreshOptions();$('flowCase').value=`saved:${items.length-1}`;toast('Saved a separate flow study in this browser. Export JSON for backup.')}catch(e){error(e)}};
  $('flowExport').onclick=()=>{try{readMetadata();download('PetroMind Flow Study.json',JSON.stringify(validateStudy(study),null,2),'application/json')}catch(e){error(e)}};
  $('flowExportResults').onclick=()=>{const a=axes[study.kind];if(fit)csv('PetroMind Flow Calibration.csv',fit.comparisons.map(r=>({sample:study.sample,condition:study.condition,source:study.source?.url||'',origin:study.origin,method:fit.method,xUnit:a.xUnit,yUnit:a.yUnit,...r})));else if(comparison)csv('PetroMind Onset Comparison.csv',[{sample:study.sample,condition:study.condition,source:study.source?.url||'',origin:study.origin,...comparison}])};
  $('flowImport').onclick=()=>$('flowFile').click();
  $('flowFile').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>500000)throw Error('Flow study JSON must be below 500 kB.');const next=validateStudy(JSON.parse(await file.text()));next.origin='user-imported';study=next;render();toast('Imported a separate flow study.')}catch(err){error(err)}finally{e.target.value=''}};
  $('flowNew').onclick=()=>{study={format:'PetroMind Flow Study',version:1,kind:$('flowNewKind').value,name:'My flow assurance measurements',sample:'Enter field, formation and sample cylinder',condition:'Enter gas composition and test method',origin:'user',source:{title:'User laboratory measurements',url:'',method:'Record the measurement method in the exported JSON'},notes:'Enter one mean value per condition. Assign validation rows before fitting.',rows:[{x:'',y:'',sd:null,role:'training'}]};render()};
  refreshOptions();render();
}
