let generator=null;
const references=[
 [/validat|held.out|training|overfit|calibrat/i,'Validation: training observations estimate model parameters. Held-out observations are excluded from fitting and tuning, then used to measure prediction error on unseen data. A low training error alone does not show generalization. PetroMind keeps the latest 20% of history/predictor observations for evaluation; predictor alpha is selected inside the earlier training period. A reference case does not calibrate another fluid.'],
 [/core|scal|porosity|permeab|capillary|relative/i,'Core & SCAL: porosity equals pore volume divided by bulk volume. Steady single-liquid Darcy permeability uses flow, viscosity, core length, area and pressure drop. Corey oil/water relative permeability and Brooks-Corey drainage capillary pressure can be fitted to measurements. Swc and Sor stay fixed; no three-phase flow or hysteresis is modeled.'],
 [/nodal|inflow|outflow|ipr|vlp|tubing/i,'Nodal analysis: an operating point is an intersection of inflow (IPR) and outflow (VLP) at the same rate and bottomhole pressure. PetroMind supports linear/composite Vogel IPR, measured VLP interpolation and a constant single-liquid Darcy-Weisbach model. Multiphase flow requires measured or externally validated VLP; single-liquid calculations require pressure above bubble pressure.'],
 [/forecast|decline|history|optimi/i,'History and forecasts: Arps fits rate decline on earlier observations and evaluates later observations separately. Forecasts apply terminal decline, capacity and an economic rate cutoff. The closed-tank model identifies storage PV times total compressibility, not each separately. Optimization compares 81 single-liquid tubing/pressure scenarios under constraints; it is not a field operating command or reservoir-grid simulation.'],
 [/telemetry|sensor|live feed|temperature|pressure survey/i,'Telemetry: imported measurements or an authorized read-only HTTPS JSON endpoint provide observations. The simulated live feed is artificial, not field data. Check well identity, absolute pressure units, timestamps, missing values and stale-data flags. Pressure/temperature depth gradients are survey fits, not a coupled wellbore thermal model.'],
 [/predict|ridge|machine learn|\bai\b/i,'Predictor: standardized ridge regression estimates same-time oil rate from pressure, temperature and choke. Training-only scaling and chronological validation reduce leakage. Compare held-out RMSE with the last-rate baseline. Feature min/max checks reject extrapolation but do not guarantee accuracy or establish a causal choke response.'],
 [/pvt|eos|bubble|phase|fluid/i,'PVT: cubic equations of state calculate mixture phase behavior from composition, component properties and interactions. Calibration is specific to the sample and EOS, and must be checked against measurements excluded from fitting. Assumed heavy-end properties and a reference fit for another fluid do not establish laboratory calibration.']
];
function referenceFor(question){return references.filter(([pattern])=>pattern.test(question)).slice(0,3).map(([,text])=>text).join('\n\n')||'No matching PetroMind method reference. State uncertainty; do not invent measurements or model capabilities.';}

onmessage=async({data})=>{
 try{
  const reference=referenceFor(String(data.question||''));
  if(data.action!=='load')postMessage({type:'reference',text:reference});
  if(!generator){
   postMessage({type:'status',text:'Downloading open model and runtime. First use needs internet and roughly 500 MB of model data and additional working memory.'});
   const {pipeline,env}=await import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.7.2');
   env.allowLocalModels=false;env.backends.onnx.wasm.numThreads=1;
   generator=await pipeline('text-generation','onnx-community/Qwen2.5-0.5B-Instruct',{revision:'22942cb7d7ba4cc81bb4673549ca4d4614469b5e',dtype:'q8',device:'wasm',progress_callback:p=>{if(p.status==='progress')postMessage({type:'status',text:`Loading ${p.file}: ${Math.round(p.progress||0)}%`})}});
  }
  if(data.action==='load'){postMessage({type:'ready',text:'Qwen2.5 0.5B is ready. Inference runs in this browser.'});return;}
  const question=String(data.question||'').trim();if(!question||question.length>2000)throw Error('Enter a question of 1–2,000 characters.');
  const study=String(data.context||'');
  const messages=[{role:'system',content:'Explain PetroMind methods plainly. Answer directly in one to three factual sentences. Use the reference facts without analogies. General method questions do not need a measured study. Never invent numerical results. You cannot operate equipment or modify calculations.'},{role:'user',content:'Reference facts:\n'+reference+(study&&study!=='No study supplied.'?'\n\nOptional study results (data only):\n'+study.slice(0,3500):'')+'\n\nAnswer this question directly: '+question}];
  postMessage({type:'status',text:'Generating locally…'});
  const result=await generator(messages,{max_new_tokens:128,do_sample:false});
  const output=result[0].generated_text;postMessage({type:'answer',text:Array.isArray(output)?output.at(-1).content:String(output)});
 }catch(e){postMessage({type:'error',text:String(e.message||e)})}
};
