let ready;
const progress = message => postMessage({type:'progress',message});
async function boot() {
  progress('Loading scientific Python… First use may take a minute.');
  const {loadPyodide} = await import('https://cdn.jsdelivr.net/pyodide/v0.29.0/full/pyodide.mjs');
  const py = await loadPyodide({indexURL:'https://cdn.jsdelivr.net/pyodide/v0.29.0/full/'});
  progress('Loading numerical libraries…');
  await py.loadPackage(['micropip','numpy','scipy','pandas','sqlite3']);
  progress('Loading the PVT engine…');
  await py.runPythonAsync("import micropip\nawait micropip.install(['thermo==0.6.1', 'fluids==1.3.1', 'chemicals==1.5.2', 'openpyxl==3.1.5'])");
  const source=await fetch('Fluid Engine.py').then(r=>{if(!r.ok)throw Error('Engine download failed');return r.text()});
  py.globals.set('progress_callback', progress);
  py.runPython(source);
  const physical=await fetch('Physical Models.py').then(r=>{if(!r.ok)throw Error('Physical model download failed');return r.text()});
  py.globals.set('physical_source',physical);
  py.runPython("physical_namespace={}\nexec(physical_source,physical_namespace)\nphysical_dispatch=physical_namespace['physical_dispatch']");
  return py;
}
onmessage = async ({data}) => {
  try {
    ready ||= boot();
    const py = await ready;
    if(data.task==='boot'){postMessage({id:data.id,type:'ready'});return;}
    progress(data.task==='calculate'?'Solving phase equilibrium and PVT properties…':'Processing data…');
    py.globals.set('request_json', JSON.stringify(data));
    const result = await py.runPythonAsync('dispatch_json(request_json)');
    postMessage({id:data.id,type:'result',result:JSON.parse(result)});
  } catch(error) {
    postMessage({id:data.id,type:'error',message:String(error.message || error).slice(-1600)});
    ready=undefined;
  }
};
