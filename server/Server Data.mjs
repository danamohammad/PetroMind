import {fitTrend,predictTrend,onsetComparison} from '../public/Flow Assurance Data.mjs';
import {pressureProfile,telemetrySummary,ingestTelemetry} from '../public/Operations Data.mjs';
import {analyseProduction} from '../public/Data Tools.mjs';
let text='';for await (const chunk of process.stdin)text+=chunk;
try {
 const r=JSON.parse(text);let result;
 switch(r.kind){
 case 'flowFit':result=fitTrend(r.study);break;
 case 'flowPredict':result=predictTrend(fitTrend(r.study),r.x);break;
 case 'flowOnset':result=onsetComparison(r.study,r.temperature,r.pressure);break;
 case 'pressureProfile':result=pressureProfile(r.rows);break;
 case 'telemetrySummary':result=telemetrySummary(ingestTelemetry(r.rows).rows,r.well,Date.now(),r.limits);delete result.rows;break;
 case 'telemetrySimulation':{const n=r.index;if(!Number.isSafeInteger(n)||n<0||n>1000000)throw Error('Invalid simulation index');result={timestamp:new Date().toISOString(),well:'SIMULATED · Demo well',pressure:3000+100*Math.sin(n/6),temperature:80+2*Math.sin(n/9),oil_rate:1000+50*Math.cos(n/5),water_rate:100+n%10,choke:50};break;}
 case 'production':result=analyseProduction(r.rows);break;
 default:throw Error('Unknown data calculation');
 }
 process.stdout.write(JSON.stringify({result}));
} catch(e){process.stdout.write(JSON.stringify({error:String(e.message)}))}
