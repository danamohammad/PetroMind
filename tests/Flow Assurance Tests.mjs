import test from 'node:test';
import assert from 'node:assert/strict';
import {publishedCases,validateStudy,fitTrend,predictTrend,onsetComparison} from '../public/Flow Assurance Data.mjs';
const close=(a,b,t=1e-10)=>assert.ok(Math.abs(a-b)<t,`${a} != ${b}`);
const copy=i=>structuredClone(publishedCases[i]);
test('source units, sample distinction and Kelvin conversion',()=>{
  close(publishedCases[0].rows[0].y,54.56);close(publishedCases[1].rows[7].y,57.8);
  assert.match(publishedCases[0].source.method,/gauge/);assert.match(publishedCases[2].sample,/Sadi.*HFx1/);
  close(publishedCases[2].rows[0].x,(186.98-32)*5/9);assert.equal(publishedCases[2].rows[0].y,7015);
});
test('training recovers a known slope and intercept; validation cannot change fit',()=>{
  const s=copy(0);s.rows.forEach(r=>{r.y=2+3*r.x;r.sd=1});let f=fitTrend(s);close(f.intercept,2);close(f.slope,3);
  s.rows.filter(r=>r.role==='validation').forEach(r=>r.y+=100);f=fitTrend(s);close(f.intercept,2);close(f.slope,3);close(f.validation.rmse,100);
});
test('weighted least squares agrees with independently calculated coefficients',()=>{
  const s=copy(0);s.rows=[{x:0,y:0,sd:1,role:'training'},{x:1,y:1,sd:1,role:'training'},{x:2,y:2,sd:1,role:'training'},{x:3,y:4,sd:.5,role:'training'}];
  const f=fitTrend(s);close(f.slope,43/31);close(f.intercept,-8/31);
});
test('published wax fits retain six training and two held-out observations',()=>{
  for(const c of publishedCases.slice(0,2)){const f=fitTrend(c);assert.equal(f.training.count,6);assert.equal(f.validation.count,2);assert.ok(f.validation.rmse<.5);assert.equal(f.curve.length,81)}
  assert.ok(fitTrend(publishedCases[0]).slope<0);assert.ok(fitTrend(publishedCases[1]).slope>0);
});
test('query and validation never extrapolate',()=>{
  const s=copy(0);s.rows[0].role='validation';const f=fitTrend(s);
  assert.equal(f.comparisons[0].predicted,null);assert.throws(()=>predictTrend(f,.1),/Extrapolation/);
  assert.throws(()=>predictTrend(f,''),/finite/);assert.ok(Number.isFinite(predictTrend(f,20)));
});
test('single-point onset comparison is temperature specific and not a fitted curve',()=>{
  const s=copy(2);const r=onsetComparison(s,86.1,4406.6);close(r.margin,-2608.4);assert.match(r.statement,/unknown/);
  assert.throws(()=>onsetComparison(s,86.2,4406.6),/No measured/);assert.throws(()=>fitTrend(s),/four distinct/);
  assert.throws(()=>onsetComparison(s,86.1,0),/positive/);
});
test('rejects mixed uncertainties, duplicate coordinates, blanks and nonphysical values',()=>{
  const s=copy(0);s.rows[0].sd=null;assert.throws(()=>fitTrend(s),/all training/);
  const d=copy(0);d.rows[1].x=d.rows[0].x;assert.throws(()=>validateStudy(d),/one mean/);
  const b=copy(0);b.rows[0].y='';assert.throws(()=>validateStudy(b),/finite/);
  b.rows[0].y=-274;assert.throws(()=>validateStudy(b),/ranges/);
});
test('equal weights work without scatter estimates and do not invent confidence intervals',()=>{
  const s=copy(0);s.rows.forEach(r=>r.sd=null);const f=fitTrend(s);assert.match(f.method,/Equal-weight/);assert.equal(f.confidenceInterval,undefined);
});
test('reference rows never enter fitting; imported fit summaries are recomputed',()=>{
  const s=copy(0);s.rows.push({x:100,y:500,sd:1,role:'reference'});s.fit={slope:1000};const f=fitTrend(s);close(f.slope,fitTrend(publishedCases[0]).slope);assert.equal(f.comparisons.at(-1).predicted,null);
});
