import {fitTrend,predictTrend,onsetComparison} from '../public/Flow Assurance Data.mjs';
import {pressureProfile,telemetrySummary,ingestTelemetry} from '../public/Operations Data.mjs';
import {analyseProduction} from '../public/Data Tools.mjs';

export function calculateData(r){
 switch(r.kind){
 case 'flowFit':return fitTrend(r.study);
 case 'flowPredict':return predictTrend(fitTrend(r.study),r.x);
 case 'flowOnset':return onsetComparison(r.study,r.temperature,r.pressure);
 case 'pressureProfile':return pressureProfile(r.rows);
 case 'telemetrySummary':{const result=telemetrySummary(ingestTelemetry(r.rows).rows,r.well,Date.now(),r.limits);delete result.rows;return result;}
 case 'telemetrySimulation':{const n=r.index;if(!Number.isSafeInteger(n)||n<0||n>1000000)throw Error('Invalid simulation index');return {timestamp:new Date().toISOString(),well:'SIMULATED · Demo well',pressure:3000+100*Math.sin(n/6),temperature:80+2*Math.sin(n/9),oil_rate:1000+50*Math.cos(n/5),water_rate:100+n%10,choke:50};}
 case 'production':return analyseProduction(r.rows);
 default:throw Error('Unknown data calculation');
 }
}
