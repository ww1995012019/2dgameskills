/* Visible-pixel review only. No inference, hidden pixels, or binding approval. */
(function(root){
'use strict';
class OwnershipReview {
 constructor(masks,report){
  if(!masks.length||masks.some(m=>m.length!==masks[0].length))throw Error('Matching nonempty mask canvases required');
  this.masks=masks;this.report=report;this.assignments=masks.map(()=>null);this.claims=[];this.undoStack=[];this.events=[];
 }
 snapshot(){return {assignments:this.assignments.map(a=>a&&({...a})),claims:[...this.claims]};}
 change(action,fn){this.undoStack.push(this.snapshot());fn();this.events.push({action,state:this.snapshot()});}
 assign(i,kind,name){
  if(!Number.isInteger(i)||i<0||i>=this.masks.length)throw Error('Unknown candidate');
  if(!['unassigned','anatomy','garment','accessory'].includes(kind))throw Error('Unknown layer kind');
  name=String(name).trim();if(kind!=='unassigned'&&!name)throw Error('Name the visible layer first');
  this.change('assign',()=>{this.assignments[i]=kind==='unassigned'?null:{kind,name};this.claims=this.claims.filter(j=>j!==i);});
 }
 claim(i){if(!this.assignments[i])throw Error('Assign this candidate before claiming overlaps');this.change('claim_overlap',()=>{this.claims=this.claims.filter(j=>j!==i);this.claims.push(i);});}
 release(i){this.change('release_overlap',()=>{this.claims=this.claims.filter(j=>j!==i);});}
 reset(){this.change('reset',()=>{this.assignments.fill(null);this.claims=[];});}
 undo(){const s=this.undoStack.pop();if(!s)return false;this.assignments=s.assignments;this.claims=s.claims;this.events.push({action:'undo',state:this.snapshot()});return true;}
 resolve(){
  const owner=new Int32Array(this.masks[0].length).fill(-1),counts={resolved_pixels:0,unassigned_pixels:0,unresolved_overlap_pixels:0,explicit_claim_pixels:0};
  const layerPixels={};
  for(let p=0;p<owner.length;p++){
   const candidates=[];for(let i=0;i<this.masks.length;i++)if(this.masks[i][p])candidates.push(i);
   if(!candidates.length)continue;
   let chosen=-1;
   if(candidates.length>1){for(let k=this.claims.length-1;k>=0;k--)if(candidates.includes(this.claims[k])){chosen=this.claims[k];counts.explicit_claim_pixels++;break;}}
   if(chosen<0){const first=this.assignments[candidates[0]];if(first&&candidates.every(i=>{const a=this.assignments[i];return a&&a.kind===first.kind&&a.name===first.name;}))chosen=candidates[0];}
   if(chosen<0){owner[p]=candidates.length>1?-2:-1;counts[candidates.length>1?'unresolved_overlap_pixels':'unassigned_pixels']++;continue;}
   owner[p]=chosen;counts.resolved_pixels++;const a=this.assignments[chosen],key=JSON.stringify([a.kind,a.name]);layerPixels[key]=(layerPixels[key]||0)+1;
  }
  return {owner,counts,layerPixels};
 }
 export(){const r=this.resolve();return {schema:'visible-ownership-review-v1',source_sha256:this.report.source_sha256,canvas:this.report.canvas,status:'user_annotations_not_semantic_validation',binding_gate:{allowed:false,reasons:['Assignments describe visible pixels only.','Merged candidates may contain several anatomical or garment regions.','Complete parts, hidden surfaces, joints and motion remain unverified.']},completeness:'visible_fragment_only',hidden_surface_pixels:0,overlap_policy:'Explicit claims only; most recent claim wins. Otherwise differing or unassigned targets remain unresolved.',assignments:this.assignments.map((a,i)=>({candidate_index:i,candidate_name:this.report.layers[i].name,mask_sha256:this.report.layers[i].mask_sha256,target:a,completeness:'visible_fragment_only'})),claim_order:[...this.claims],counts:r.counts,visible_layer_pixels:r.layerPixels,history:this.events};}
}
if(typeof module!=='undefined'&&module.exports)module.exports=OwnershipReview;else root.OwnershipReview=OwnershipReview;
})(typeof globalThis!=='undefined'?globalThis:this);
