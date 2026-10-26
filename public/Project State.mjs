// Calibration evidence belongs to one composition, EOS and parameter set.
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function evidenceMatches(input,evidence){
 const candidate=evidence?.appliedCandidate||evidence?.fit?.candidate;
 return !!(evidence?.fit?.eligible&&candidate&&evidence.fitInput&&
  same(candidate.catalog,input.catalog)&&same(candidate.interactions,input.interactions)&&
  same(evidence.fitInput.composition,input.composition)&&evidence.fitInput.model===input.model);
}
export function calibrationMessage({valid,calibration,isExample,name}){
 if(valid){
  if(calibration.synthetic)return {title:'Synthetic demonstration fit',description:'This fit uses generated test data, not laboratory measurements.'};
  return {title:calibration.fit?.parameters?.some(p=>p.atBound)?'Laboratory fit · parameter-bound qualification':'Laboratory-calibrated project',description:`${name}. This fit covers the recorded measurements for this fluid and EOS. Review held-out errors and qualifications in Laboratory & tuning.`};
 }
 if(calibration)return {title:'Fluid changed since calibration',description:'The active composition, EOS or properties differ from the fitted model. Reopen the calibrated project or fit the edited fluid before treating its results as calibrated.'};
 if(isExample)return {title:'Demonstration fluid · no laboratory fit',description:'You are viewing the supplied example, not your calibrated project. Open a saved project or import your calibrated project JSON to use its fitted properties.'};
 return {title:'Current fluid · no matching calibration record',description:'Import this fluid’s calibrated project JSON, or enter its measurements in Laboratory & tuning and apply a fit.'};
}
export const activeProjectKey='PetroMind Active Project v1';
export function storeActiveProject(storage,project,id){storage.setItem(activeProjectKey,JSON.stringify({project,id}));}
export function readActiveProject(storage){const value=storage.getItem(activeProjectKey);return value?JSON.parse(value):null;}
