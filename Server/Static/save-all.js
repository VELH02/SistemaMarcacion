(() => {
  const excluded = /\/(?:login|logout|eliminar|backup|sync_ntp)(?:\/|$)/;
  const forms = [...document.forms].filter(f => f.method.toLowerCase()==='post' && !excluded.test(new URL(f.action).pathname));
  if (!forms.length) return;
  const baseline = new Map();
  const dirty = new Set();
  let saving = false;
  const signature = form => JSON.stringify([...new FormData(form)].map(([key,value]) => [key,value instanceof File ? [value.name,value.size,value.lastModified] : value]));
  forms.forEach(f => baseline.set(f, signature(f)));
  const bar = document.createElement('div');
  bar.className='alert alert-info sticky-top d-flex align-items-center gap-3 shadow-sm';
  const label=document.createElement('span');
  const save=document.createElement('button');
  save.type='button';save.className='btn btn-custom';save.textContent='Guardar todos los cambios';
  const error=document.createElement('span');error.className='text-danger';error.setAttribute('role','alert');
  bar.append(label,save,error);document.querySelector('.container-fluid.px-4')?.prepend(bar);
  const refresh=()=>{label.textContent=dirty.size+' formularios con cambios pendientes';save.disabled=saving||!dirty.size;};
  const track=form=>{if(!baseline.has(form))return;signature(form)===baseline.get(form)?dirty.delete(form):dirty.add(form);refresh();};
  document.addEventListener('input', e=>track(e.target.form));
  document.addEventListener('change', e=>{
    const field=e.target;
    if(field.matches('[data-fixed-shift]') && field.value){
      for(let i=0;i<7;i++)field.form.elements.namedItem('dia_'+i).value=i===6?'DESCANSO':field.value;
    }
    track(field.form);
  });
  async function persist(selected, submitter){
    const pending=[...dirty];if(selected&&!pending.includes(selected))pending.push(selected);
    if(!pending.length||saving)return;
    error.textContent='';
    for(const form of pending){if(!form.reportValidity()){error.textContent='Completa los campos obligatorios de todos los formularios editados.';return;}}
    saving=true;refresh();
    const body=new FormData(), operations=[];
    pending.forEach((form,index)=>{
      const fields=[],files=[];
      for(const [key,value] of new FormData(form)){
        if(value instanceof File){if(value.name){const id='archivo_'+index+'_'+files.length;body.append(id,value);files.push([key,id]);}}
        else fields.push([key,value]);
      }
      if(form===selected&&submitter?.name)fields.push([submitter.name,submitter.value]);
      operations.push({action:new URL(form.action).pathname,fields,files});
    });
    body.append('operaciones',JSON.stringify(operations));
    try{
      const response=await fetch('/guardar_cambios',{method:'POST',body,headers:{'Accept':'application/json'}});
      const result=await response.json();
      if(!response.ok||!result.ok)throw new Error(result.error||'No se pudieron guardar los cambios.');
      dirty.clear();location.reload();
    }catch(problem){error.textContent=problem.message; saving=false;refresh();}
  }
  document.addEventListener('submit',e=>{
    if(forms.includes(e.target)){e.preventDefault();persist(e.target,e.submitter);}
    else if(e.target.method.toLowerCase()==='get'&&dirty.size){e.preventDefault();error.textContent='Guarda los cambios pendientes antes de cambiar los filtros.';}
  });
  save.addEventListener('click',()=>persist());
  window.addEventListener('beforeunload',e=>{if(dirty.size){e.preventDefault();e.returnValue='';}});
  refresh();
})();
