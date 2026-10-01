// Runtime render check without an installed browser binary.
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const elements = new Map();
for (const name of ['#view','#page-title','#today','#toast']) elements.set(name,{innerHTML:'',textContent:'',className:''});
const document = {
  title:'',
  querySelector:s=>elements.get(s)||null,
  querySelectorAll:()=>[],
  addEventListener:()=>{},
};
const area={id:1,name:'Δοκιμαστική Κοινότητα',kind:'Κοινότητα'};
const oldCase={id:1,area_id:1,area,area_name:area.name,case_no:'ΛΕΥ-2026-000001',flow:'legacy',state:'Σε εξέλιξη',lot_count:1,sections:{'8.8':{}},files:[],lots:[]};
const newCase={...oldCase,id:2,case_no:'ΛΕΥ-2026-000002',flow:'new',sections:{'4':{access:'Πρόσβαση από οδό δοκιμής'},'3':{parcels:[]},'1':{interested:[]},'5':{consultations:[]}}};
const lot={id:1,case_id:1,area_id:1,area_name:area.name,flow:'legacy',case_no:oldCase.case_no,lot_no:'Π-1',title_status:'Δεν υπάρχει τίτλος',valuation_value:'80000.00',valuation_ref:'ΤΚΧ-1',disposal_price:'20000.00',status:'available'};
oldCase.lots=[lot];
const notice={id:1,notice_no:'ΓΝ-ΛΕΥ-2026-00001',state:'Δημοσιευμένη',offers:[lot],lot_count:1,area_count:1,files:[]};
const app={id:1,application_no:'ΑΙ-ΛΕΥ-2026-000001',area_id:1,area,notice_id:1,person_id:1,person:{full_name:'Πολίτης Δοκιμής',identity_no:'TEST01'},received_at:'2026-10-01',state:'Καταχωρισμένη',committee_decision:'Εκκρεμεί',criteria:{},criteria_summary:{preliminary:'Εκκρεμεί',failed:[]},sections:{},related:[],files:[]};
const boot={areas:[area],cases:[oldCase,newCase],lots:[lot],notices:[notice],applications:[{...app,area_name:area.name,full_name:app.person.full_name,notice_no:notice.notice_no}]};
const fetch=async url=>({ok:true,json:async()=>url==='/api/bootstrap'?boot:url==='/api/cases/1'?oldCase:url==='/api/cases/2'?newCase:url==='/api/notices/1'?notice:url==='/api/applications/1'?app:[]});
const context=vm.createContext({document,fetch,window:{scrollTo(){}},setTimeout,clearTimeout,FormData,FileReader:class{}});
vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../static/app.js'),'utf8'),context);

(async()=>{
  await new Promise(ok=>setTimeout(ok,0));
  assert.match(elements.get('#view').innerHTML,/Δύο ροές υποθέσεων/);
  async function visit(name,id,tab,needle){await vm.runInContext(`navigate(${JSON.stringify(name)},${id===null?'null':id},${JSON.stringify(tab)})`,context);assert.match(elements.get('#view').innerHTML,needle)}
  await visit('case',1,'8.8',/Π-1/);
  assert.doesNotMatch(elements.get('#view').innerHTML,/data-tab="1"/);
  await visit('case',2,'6',/Πρόσβαση από οδό δοκιμής/);
  await visit('notice',1,'overview',/Δημοσιευμένη/);
  await visit('application',1,'10.2.2',/Δικαιολογητικά/);
  await visit('application',1,'10.4',/Προηγούμενη κρατική στεγαστική ενίσχυση/);
  await visit('application',1,'10.5',/Εισήγηση Γραφείου/);
  await visit('application',1,'10.11',/πρωτότυπης Συμφωνίας/);
  console.log('UI render: eight screens passed');
})().catch(e=>{console.error(e);process.exitCode=1});
