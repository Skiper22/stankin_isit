// Helpers
const el  = (sel, root=document)=>root.querySelector(sel);
const els = (sel, root=document)=>[...root.querySelectorAll(sel)];

async function API(url, opts={}){
  const r = await fetch(url, {
    headers: {'Content-Type':'application/json'},
    credentials:"include",
    ...opts
  });
  if(!r.ok){
    let msg = "Ошибка";
    try{ const j = await r.json(); msg = j.detail || JSON.stringify(j); }
    catch(e){ msg = await r.text(); }
    throw new Error(msg);
  }
  return r.headers.get("content-type")?.includes("application/json")
    ? r.json()
    : r.text();
}

function showAppShell(){ el("#appShell").classList.remove("hidden"); }
function hideMarketing(){ el("#marketingHeader")?.classList.add("hidden"); }

function tplTable(cols, rows, opts={}){
  const sortable = opts.sortable || [];
  let thead = cols.map((c,i)=>`<th class="${sortable.includes(i)?'sortable':''}" data-col="${i}">${c}</th>`).join("");
  let body  = rows.map(r=>`<tr>${r.map(c=>`<td>${c ?? ""}</td>`).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table class="table"><thead><tr>${thead}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// сортировка таблиц
document.addEventListener("click", (e)=>{
  const th = e.target.closest("th.sortable"); if(!th) return;
  const col = +th.dataset.col;
  const table = th.closest("table");
  const rows = [...table.querySelectorAll("tbody tr")];
  const asc = !(th.dataset.asc==="true");
  th.dataset.asc = asc ? "true" : "false";
  rows.sort((a,b)=>{
    const ta = a.children[col].innerText;
    const tb = b.children[col].innerText;
    const na = parseFloat(ta.replace(',', '.'));
    const nb = parseFloat(tb.replace(',', '.'));
    if(!Number.isNaN(na) && !Number.isNaN(nb)) return asc ? na-nb : nb-na;
    return asc ? ta.localeCompare(tb) : tb.localeCompare(ta);
  });
  rows.forEach(r=>table.tBodies[0].appendChild(r));
});

// Toasts & confirm
function ensureToastWrap(){
  if(!el(".toast-wrap")){
    const d=document.createElement("div");
    d.className="toast-wrap";
    document.body.appendChild(d);
  }
  return el(".toast-wrap");
}
function toast(msg, ok=true){
  const wrap=ensureToastWrap();
  const div=document.createElement("div");
  div.className="toast "+(ok?"ok":"err");
  div.textContent=msg;
  wrap.appendChild(div);
  setTimeout(()=>div.remove(),3000);
}
function confirmBox(text){
  return new Promise(res=>{
    const m=document.createElement('div'); m.className='confirm-mask';
    m.innerHTML=`<div class="confirm-card"><div class="text-lg font-semibold mb-2">Подтверждение</div>
      <div class="text-slate-200">${text}</div>
      <div class="confirm-actions">
        <button class="btn-ghost" id="c_no">Отмена</button>
        <button class="btn-primary" id="c_yes">Подтвердить</button>
      </div></div>`;
    document.body.appendChild(m);
    m.querySelector('#c_no').onclick=()=>{m.remove(); res(false);};
    m.querySelector('#c_yes').onclick=()=>{m.remove(); res(true);};
  });
}

// Auth/state
let USER = null;
let CURRENT_VIEW = "dashboard";
let inboxTimer = null;

async function openLogin(){ el("#loginModal").classList.remove("hidden"); }

async function doLogin(){
  try{
    await API(`/api/v1/auth/login`, {
      method:"POST",
      body: JSON.stringify({
        login: el("#login").value,
        password: el("#password").value
      })
    });
    el("#loginModal").classList.add("hidden");
    await afterLogin();
  }catch(e){
    toast("Ошибка входа: " + e.message, false);
  }
}

async function afterLogin(){
  const me = await API(`/api/v1/auth/me`);
  USER = me;
  el("#userLogin").textContent = USER.login;
  hideMarketing();
  showAppShell();
  navigate("dashboard");
}

el("#btnLogin").onclick = openLogin;
el("#doLogin").onclick  = doLogin;

// Try auto-login (cookie)
(async ()=>{
  try{ await afterLogin(); }
  catch(e){ /* not logged */ }
})();

// Navigation
els("#nav button").forEach(b=> b.onclick = ()=> navigate(b.dataset.view));

async function navigate(view){
  CURRENT_VIEW = view;

  // если уходим с «Уведомлений» — гасим таймер
  if(view !== "inbox" && inboxTimer){
    clearInterval(inboxTimer);
    inboxTimer = null;
  }

  if(view==="dashboard")  return renderDashboard();
  if(view==="sites")       return renderSites();
  if(view==="equipment")   return renderEquipment();
  if(view==="inventory")   return renderInventory();
  if(view==="workorders")  return renderWorkOrders();
  if(view==="supply")      return renderSupply();
  if(view==="planning")    return renderPlanning();
  if(view==="inbox")       return renderInbox();
  if(view==="reports")     return renderReports();
  if(view==="users")       return renderUsers();
}

// Views helpers
function hero(title, subtitle=""){
  return `<div class="mb-3">
    <div class="text-2xl font-semibold mb-1">${title}</div>
    <div class="text-slate-400">${subtitle}</div>
  </div>`;
}

// --- Dashboard ---
async function renderDashboard(){
  const [wo, inv, top] = await Promise.all([
    API('/api/v1/reports/work_orders_by_status'),
    API('/api/v1/reports/inventory_breakdown'),
    API('/api/v1/reports/top_products')
  ]);
  el("#view").innerHTML = hero("Сводка холдинга", "Ключевые метрики в реальном времени.")
    + `<div class="grid md:grid-cols-3 gap-3">
      <div class="card">
        <div class="text-slate-400 text-sm mb-1">ТОиР: по статусам</div>
        <canvas id="ch_wo"></canvas>
      </div>
      <div class="card">
        <div class="text-slate-400 text-sm mb-1">Запасы: OK vs LOW</div>
        <canvas id="ch_inv"></canvas>
      </div>
      <div class="card">
        <div class="text-slate-400 text-sm mb-1">Топ продуктов в планах</div>
        <canvas id="ch_top"></canvas>
      </div>
    </div>`;

  new Chart(el("#ch_wo"), {
    type:'doughnut',
    data:{labels: wo.results.map(x=>x.status), datasets:[{data: wo.results.map(x=>x.count)}]},
    options:{plugins:{legend:{position:'bottom'}}}
  });

  new Chart(el("#ch_inv"), {
    type:'pie',
    data:{labels:["OK","LOW"], datasets:[{data:[inv.ok, inv.low]}]},
    options:{plugins:{legend:{position:'bottom'}}}
  });

  new Chart(el("#ch_top"), {
    type:'bar',
    data:{labels: top.results.map(x=>x.product_name), datasets:[{data: top.results.map(x=>x.quantity)}]},
    options:{
      plugins:{legend:{display:false}},
      responsive:true,
      scales:{
        x:{title:{display:true, text:'Продукты'}},
        y:{title:{display:true, text:'Кол-во'}}
      }
    }
  });
}

// --- Sites ---
async function renderSites(){
  const list = await API('/api/v1/sites?page=1&page_size=50');
  const rows = list.results.map(s=>[
    s.id,
    s.name,
    s.region,
    `<div class="flex gap-2">
      <button class="btn-ghost" onclick="renderInventory(${s.id})">Склад</button>
      <button class="btn-ghost" onclick="editSite(${s.id}, '${s.name}', '${s.region}')">Изм.</button>
      <button class="btn-ghost" onclick="deleteSite(${s.id}, '${s.name}')">Удалить</button>
    </div>`
  ]);
  const create = `<div class="card">
    <div class="text-lg font-semibold mb-2">Новая площадка</div>
    <div class="grid md:grid-cols-3 gap-3">
      <label class="field"><span>Название</span><input id="site_name" class="input" placeholder="Площадка С"></label>
      <label class="field"><span>Регион</span><input id="site_region" class="input" placeholder="СЗФО"></label>
      <div class="flex items-end"><button class="btn-primary" onclick="createSite()">Создать</button></div>
    </div>
  </div>`;
  el("#view").innerHTML = hero("Площадки","Управление площадками холдинга.")
    + create
    + tplTable(["ID","Площадка","Регион","Действия"], rows, {sortable:[0,1,2]});
}
async function createSite(){
  try{
    await API('/api/v1/sites', {
      method:'POST',
      body: JSON.stringify({
        name: el('#site_name').value,
        region: el('#site_region').value
      })
    });
    toast('Площадка создана');
    renderSites();
  }catch(e){ toast(e.message||'Ошибка',false); }
}
async function editSite(id,name,region){
  const box=document.createElement('div');
  box.className='card';
  box.innerHTML=`<div class="text-lg font-semibold mb-2">Редактировать площадку #${id}</div>
    <div class="grid md:grid-cols-3 gap-3">
      <label class="field"><span>Название</span><input id="e_site_name" class="input" value="${name}"></label>
      <label class="field"><span>Регион</span><input id="e_site_region" class="input" value="${region}"></label>
      <div class="flex items-end"><button class="btn-primary" id="e_save">Сохранить</button></div>
    </div>`;
  el("#view").prepend(box);
  el("#e_save").onclick=async()=>{
    try{
      await API(`/api/v1/sites/${id}`, {
        method:'PUT',
        body: JSON.stringify({
          name: el('#e_site_name').value,
          region: el('#e_site_region').value
        })
      });
      toast('Сохранено');
      renderSites();
    }catch(e){ toast(e.message||'Ошибка',false); }
  };
}
async function deleteSite(id,name){
  const ok=await confirmBox(`Удалить площадку «${name}»?`);
  if(!ok) return;
  try{
    await API(`/api/v1/sites/${id}`, {method:'DELETE'});
    toast('Удалено');
    renderSites();
  }catch(e){ toast(e.message||'Ошибка',false); }
}

// --- Equipment ---
async function renderEquipment(){
  const [types, list] = await Promise.all([
    API('/api/v1/equipment-types'),
    API('/api/v1/equipment?page=1&page_size=100')
  ]);
  const typeMap = Object.fromEntries(types.results.map(t=>[t.id, t.name]));
  const rows = list.results.map(e=>[
    e.id,
    e.code,
    e.name,
    e.status,
    e.site_id,
    e.equipment_type_id + ' / ' + (typeMap[e.equipment_type_id]||''),
    e.commissioning_date,
    `<div class="flex gap-2">
      <button class="btn-ghost" onclick="editEquipment(${e.id}, ${e.site_id}, ${e.equipment_type_id}, '${e.code}', '${e.name}', '${e.status}', '${e.commissioning_date}')">Изм.</button>
      <button class="btn-ghost" onclick="deleteEquipment(${e.id}, '${e.code}')">Удалить</button>
    </div>`
  ]);
  const typeOptions = types.results.map(t=>`<option value="${t.id}">${t.name}</option>`).join("");
  const create = `<div class="card">
    <div class="text-lg font-semibold mb-2">Добавить оборудование</div>
    <div class="grid md:grid-cols-6 gap-3">
      <label class="field"><span>Site ID</span><input id="eq_site" class="input" placeholder="1" value="1"></label>
      <label class="field"><span>Тип</span><select id="eq_type" class="input">${typeOptions}</select></label>
      <label class="field"><span>Код</span><input id="eq_code" class="input" placeholder="EQ-1003"></label>
      <label class="field"><span>Название</span><input id="eq_name" class="input" placeholder="Дробилка-3"></label>
      <label class="field"><span>Статус</span>
        <select id="eq_status" class="input">
          <option>active</option>
          <option>maintenance</option>
          <option>idle</option>
        </select>
      </label>
      <label class="field"><span>Ввод</span><input id="eq_date" type="date" class="input"></label>
    </div>
    <div class="mt-3"><button class="btn-primary" onclick="createEquipment()">Создать</button></div>
  </div>`;
  el("#view").innerHTML = hero("Оборудование","Реестр технологического оборудования.")
    + create
    + tplTable(["ID","Код","Название","Статус","Site","Тип","Ввод","Действия"], rows, {sortable:[0,1,2,3,4,6]});
}
async function createEquipment(){
  const payload={
    site_id:parseInt(el('#eq_site').value),
    equipment_type_id:parseInt(el('#eq_type').value),
    code:el('#eq_code').value,
    name:el('#eq_name').value,
    status:el('#eq_status').value,
    commissioning_date:el('#eq_date').value
  };
  try{
    await API('/api/v1/equipment', {method:'POST', body: JSON.stringify(payload)});
    toast('Добавлено');
    renderEquipment();
  }catch(e){ toast(e.message||'Ошибка',false); }
}
async function editEquipment(id, site_id, type_id, code, name, status, dateStr){
  const box=document.createElement('div');
  box.className='card';
  box.innerHTML=`<div class="text-lg font-semibold mb-2">Редактировать оборудование #${id}</div>
    <div class="grid md:grid-cols-6 gap-3">
      <label class="field"><span>Site ID</span><input id="e_eq_site" class="input" value="${site_id}"></label>
      <label class="field"><span>Тип</span><input id="e_eq_type" class="input" value="${type_id}"></label>
      <label class="field"><span>Код</span><input id="e_eq_code" class="input" value="${code}"></label>
      <label class="field"><span>Название</span><input id="e_eq_name" class="input" value="${name}"></label>
      <label class="field"><span>Статус</span><input id="e_eq_status" class="input" value="${status}"></label>
      <label class="field"><span>Ввод</span><input id="e_eq_date" type="date" class="input" value="${(dateStr||'').slice(0,10)}"></label>
    </div>
    <div class="mt-3"><button class="btn-primary" id="e_save_eq">Сохранить</button></div>`;
  el("#view").prepend(box);
  el("#e_save_eq").onclick=async ()=>{
    const payload={
      site_id:parseInt(el('#e_eq_site').value),
      equipment_type_id:parseInt(el('#e_eq_type').value),
      code:el('#e_eq_code').value,
      name:el('#e_eq_name').value,
      status:el('#e_eq_status').value,
      commissioning_date:el('#e_eq_date').value
    };
    try{
      await API(`/api/v1/equipment/${id}`, {method:'PUT', body: JSON.stringify(payload)});
      toast('Сохранено');
      renderEquipment();
    }catch(e){ toast(e.message||'Ошибка',false); }
  };
}
async function deleteEquipment(id, code){
  const ok=await confirmBox(`Удалить оборудование «${code}»?`);
  if(!ok) return;
  try{
    await API(`/api/v1/equipment/${id}`, {method:'DELETE'});
    toast('Удалено');
    renderEquipment();
  }catch(e){ toast(e.message||'Ошибка',false); }
}

// --- Inventory ---
async function renderInventory(siteId){
  if(!siteId){
    const data = await API('/api/v1/sites?page=1&page_size=50');
    const rows = data.results.map(s=>[
      s.id,
      s.name,
      s.region,
      `<button class="btn-ghost" onclick="renderInventory(${s.id})">Показать склад</button>`
    ]);
    el("#view").innerHTML = hero("Материалы и склад","Остатки по площадкам.")
      + tplTable(["ID","Площадка","Регион",""], rows, {sortable:[0,1,2]});
    return;
  }
  const [inv, mats] = await Promise.all([
    API(`/api/v1/sites/${siteId}/inventory`),
    API('/api/v1/materials?page=1&page_size=200')
  ]);
  const rows = inv.items.map(i=>[
    i.material_id,
    i.material_name,
    i.unit,
    i.qty_on_hand,
    i.reorder_point,
    `<div class="flex gap-2">
      <button class="btn-ghost" onclick="editInv(${siteId}, ${i.material_id}, ${i.qty_on_hand}, ${i.reorder_point}, '${i.material_name}')">Изм. остаток</button>
    </div>`
  ]);
  const createMat = `<div class="card">
    <div class="text-lg font-semibold mb-2">Добавить материал</div>
    <div class="grid md:grid-cols-4 gap-3">
      <label class="field"><span>Название</span><input id="m_name" class="input" placeholder="Подшипник 6206"></label>
      <label class="field"><span>Ед. изм.</span><input id="m_unit" class="input" placeholder="pcs"></label>
      <label class="field"><span>% брака</span><input id="m_reject" class="input" type="number" step="0.1" value="0"></label>
      <div class="flex items-end"><button class="btn-primary" onclick="createMaterial()">Создать</button></div>
    </div>
  </div>`;
  el("#view").innerHTML = hero("Материалы и склад","Остатки по площадке.")
    + createMat
    + `<div class="text-lg font-semibold mb-2">Склад площадки #${inv.site_id}</div>`
    + tplTable(["Материал","Название","Ед.","Остаток","ROP","Действия"], rows, {sortable:[0,1,3,4]});

  const matRows = mats.results.map(m=>[
    m.id,
    m.name,
    m.unit,
    m.reject_percent ?? 0,
    `<div class="flex gap-2">
      <button class="btn-ghost" onclick="editMaterial(${m.id}, '${m.name}', '${m.unit}', ${m.reject_percent||0})">Изм.</button>
      <button class="btn-ghost" onclick="deleteMaterial(${m.id}, '${m.name}')">Удал.</button>
    </div>`
  ]);
  el("#view").insertAdjacentHTML(
    'beforeend',
    `<div class="mt-4 card">
       <div class="text-lg font-semibold mb-2">Все материалы</div>
       ${tplTable(["ID","Название","Ед.","% брака","Действия"], matRows, {sortable:[0,1,2,3]})}
     </div>`
  );
}
async function editInv(site_id, material_id, qty, rop, name){
  const box=document.createElement('div');
  box.className='card';
  box.innerHTML=`<div class="text-lg font-semibold mb-2">Остатки по «${name}» @ site #${site_id}</div>
    <div class="grid md:grid-cols-2 gap-3">
      <label class="field"><span>Остаток</span><input id="i_qty" class="input" type="number" step="0.01" value="${qty}"></label>
      <label class="field"><span>ROP</span><input id="i_rop" class="input" type="number" step="0.01" value="${rop}"></label>
    </div>
    <div class="mt-3"><button class="btn-primary" id="i_save">Сохранить</button></div>`;
  el("#view").prepend(box);
  el("#i_save").onclick=async()=>{
    try{
      await API(`/api/v1/sites/${site_id}/inventory/${material_id}`, {
        method:'PUT',
        body: JSON.stringify({
          qty_on_hand: parseFloat(el('#i_qty').value),
          reorder_point: parseFloat(el('#i_rop').value)
        })
      });
      toast('Остаток обновлён');
      renderInventory(site_id);
    }catch(e){ toast(e.message||'Ошибка',false); }
  };
}
async function createMaterial(){
  try{
    await API('/api/v1/materials', {
      method:'POST',
      body: JSON.stringify({
        name: el('#m_name').value,
        unit: el('#m_unit').value,
        reject_percent: parseFloat(el('#m_reject').value||0)
      })
    });
    toast('Материал создан');
    renderInventory(1);
  }catch(e){ toast(e.message||'Ошибка',false); }
}
async function editMaterial(id, name, unit, reject){
  const box=document.createElement('div');
  box.className='card';
  box.innerHTML=`<div class="text-lg font-semibold mb-2">Редактировать материал #${id}</div>
    <div class="grid md:grid-cols-3 gap-3">
      <label class="field"><span>Название</span><input id="e_m_name" class="input" value="${name}"></label>
      <label class="field"><span>Ед.</span><input id="e_m_unit" class="input" value="${unit}"></label>
      <label class="field"><span>% брака</span><input id="e_m_reject" class="input" type="number" step="0.1" value="${reject}"></label>
    </div>
    <div class="mt-3"><button class="btn-primary" id="e_m_save">Сохранить</button></div>`;
  el("#view").prepend(box);
  el("#e_m_save").onclick=async()=>{
    try{
      await API(`/api/v1/materials/${id}`, {
        method:'PUT',
        body: JSON.stringify({
          name: el('#e_m_name').value,
          unit: el('#e_m_unit').value,
          reject_percent: parseFloat(el('#e_m_reject').value||0)
        })
      });
      toast('Сохранено');
      renderInventory(1);
    }catch(e){ toast(e.message||'Ошибка',false); }
  };
}
async function deleteMaterial(id, name){
  const ok=await confirmBox(`Удалить материал «${name}»?`);
  if(!ok) return;
  try{
    await API(`/api/v1/materials/${id}`, {method:'DELETE'});
    toast('Удалено');
    renderInventory(1);
  }catch(e){ toast(e.message||'Ошибка',false); }
}

// --- Inbox (уведомления) ---
function isRead(id){
  try{
    const m = JSON.parse(localStorage.getItem('read_events')||'[]');
    return m.includes(id);
  }catch(e){ return false; }
}
function markRead(id){
  try{
    const m = new Set(JSON.parse(localStorage.getItem('read_events')||'[]'));
    m.add(id);
    localStorage.setItem('read_events', JSON.stringify([...m]));
  }catch(e){}
}
function clearRead(){
  localStorage.removeItem('read_events');
  drawInbox();
}

async function renderInbox(){
  el("#view").innerHTML = hero("Лента событий", "Планы, заявки ТОиР, закупки, авторизации — обновляется автоматически.");

  const controls = `<div class="card mb-2">
    <div class="grid md:grid-cols-4 gap-3">
      <label class="field"><span>Тип</span>
        <select id="f_type" class="input">
          <option value="">Все</option>
          <option value="plan">Планы</option>
          <option value="work_order">ТОиР</option>
          <option value="po_">Закупки</option>
          <option value="auth">Входы</option>
        </select>
      </label>
      <label class="field"><span>Важность</span>
        <select id="f_sev" class="input">
          <option value="">Все</option>
          <option value="success">success</option>
          <option value="warning">warning</option>
          <option value="danger">danger</option>
          <option value="info">info</option>
        </select>
      </label>
      <div class="flex items-end"><button class="btn-ghost" onclick="drawInbox()">Применить</button></div>
      <div class="flex items-end"><button class="btn-ghost" onclick="clearRead()">Сброс отметок</button></div>
    </div>
  </div>`;

  el("#view").insertAdjacentHTML('beforeend', controls + `<div id="inboxList"></div>`);

  await drawInbox();

  if(inboxTimer) clearInterval(inboxTimer);
  inboxTimer = setInterval(drawInbox, 5000);
}

async function drawInbox(){
  // не рисуем, если пользователь уже ушёл с вкладки
  if(CURRENT_VIEW !== "inbox") return;

  const container = el("#inboxList");
  if(!container) return;

  const data = await API('/api/v1/events?limit=60');
  const t    = el("#f_type")?.value || "";
  const sevF = el("#f_sev")?.value  || "";
  const icon = (t)=> t.includes("plan")?"🗓️":t.includes("work_order")?"🛠️":t.includes("po_")?"🧾":t.includes("auth")?"🔑":"ℹ️";
  const sev  = (s)=> s==="success"?"ok":(s==="warning"?"warn":(s==="danger"?"err":""));

  const html = data.results
    .filter(e=>!t || e.type.includes(t))
    .filter(e=>!sevF || e.severity===sevF)
    .map(e=>{
      const read = isRead(e.id);
      return `<div class="timeline-item ${read?'opacity-60':''}" onclick="markRead(${e.id})">
        <div class="timeline-dot"></div>
        <div class="ev">
          <span>${icon(e.type)}</span>
          <span class="badge ${sev(e.severity)}">${e.severity}</span>
          <span class="text-slate-300">${e.text}</span>
          <span class="text-slate-500 text-sm">• ${new Date(e.created_at).toLocaleString()}</span>
        </div>
      </div>`;
    }).join("");

  container.innerHTML = `<div class="card"><div class="timeline">${html}</div></div>`;
}

// --- Reports ---
async function renderReports(){
  el("#view").innerHTML = hero("Отчёты", "Динамика по ТОиР, запасам и планам.")
    + `<div class="grid md:grid-cols-3 gap-3">
      <div class="card"><div>ТОиР по статусам</div><canvas id="r1"></canvas></div>
      <div class="card"><div>Запасы: OK vs LOW</div><canvas id="r2"></canvas></div>
      <div class="card"><div>Топ продуктов</div><canvas id="r3"></canvas></div>
    </div>`;
  const [wo, inv, top] = await Promise.all([
    API('/api/v1/reports/work_orders_by_status'),
    API('/api/v1/reports/inventory_breakdown'),
    API('/api/v1/reports/top_products')
  ]);
  new Chart(el("#r1"), {
    type:'bar',
    data:{labels: wo.results.map(x=>x.status), datasets:[{data: wo.results.map(x=>x.count)}]},
    options:{
      plugins:{legend:{display:false}},
      scales:{
        x:{title:{display:true, text:'Статус'}},
        y:{title:{display:true, text:'Кол-во'}}
      }
    }
  });
  new Chart(el("#r2"), {
    type:'pie',
    data:{labels:["OK","LOW"], datasets:[{data:[inv.ok, inv.low]}]}
  });
  new Chart(el("#r3"), {
    type:'bar',
    data:{labels: top.results.map(x=>x.product_name), datasets:[{data: top.results.map(x=>x.quantity)}]},
    options:{
      plugins:{legend:{display:false}},
      scales:{
        x:{title:{display:true, text:'Продукт'}},
        y:{title:{display:true, text:'Кол-во'}}
      }
    }
  });
}

// --- Work Orders (ТОиР) ---
async function renderWorkOrders(){
  const [sites, data] = await Promise.all([
    API('/api/v1/sites?page=1&page_size=100'),
    API('/api/v1/workorders')
  ]);
  const siteMap = Object.fromEntries((sites.results||[]).map(s=>[s.id, s.name]));
  const rows = data.results.map(w=>[
    w.id,
    siteMap[w.site_id] || w.site_id,
    w.title,
    w.status,
    w.priority,
    w.assigned_team || '—',
    w.planned_date ? w.planned_date : '—',
    `<div class="flex gap-2">
      <button class="btn-ghost" onclick="woChangeStatus(${w.id}, 'in_progress')">В работу</button>
      <button class="btn-ghost" onclick="woChangeStatus(${w.id}, 'done')">Закрыть</button>
    </div>`
  ]);
  const create = `<div class="card">
    <div class="text-lg font-semibold mb-2">Новая заявка ТОиР</div>
    <div class="grid md:grid-cols-6 gap-3">
      <label class="field"><span>Площадка (ID)</span><input id="wo_site" class="input" placeholder="1" value="1"></label>
      <label class="field"><span>Тип</span>
        <select id="wo_type" class="input">
          <option value="corrective">Аварийная</option>
          <option value="preventive">Плановая</option>
        </select>
      </label>
      <label class="field"><span>Приоритет</span>
        <select id="wo_priority" class="input">
          <option value="normal">normal</option>
          <option value="high">high</option>
          <option value="low">low</option>
        </select>
      </label>
      <label class="field"><span>Заголовок</span><input id="wo_title" class="input" placeholder="Например: Замена ремня"></label>
      <label class="field"><span>Плановая дата</span><input id="wo_planned" type="date" class="input"></label>
      <label class="field"><span>Бригада</span><input id="wo_team" class="input" placeholder="Бригада 1"></label>
    </div>
    <label class="field mt-3"><span>Описание</span>
      <textarea id="wo_desc" class="input" rows="2" placeholder="Кратко опишите проблему"></textarea>
    </label>
    <div class="mt-3"><button class="btn-primary" onclick="createWorkOrder()">Создать</button></div>
  </div>`;
  el("#view").innerHTML = hero("Заявки ТОиР","Создание, статусы и назначение бригад.")
    + create
    + tplTable(
        ["ID","Площадка","Заголовок","Статус","Приоритет","Бригада","Плановая дата","Действия"],
        rows,
        {sortable:[0,1,2,3,4,6]}
      );
}
async function createWorkOrder(){
  const payload = {
    site_id: parseInt(el("#wo_site").value),
    type: el("#wo_type").value,
    status: "new",
    priority: el("#wo_priority").value,
    title: el("#wo_title").value || "Заявка ТОиР",
    description: el("#wo_desc").value || null,
    planned_date: el("#wo_planned").value || null,
    assigned_team: el("#wo_team").value || null
  };
  try{
    await API('/api/v1/workorders', {method:'POST', body: JSON.stringify(payload)});
    toast("Заявка создана");
    renderWorkOrders();
  }catch(e){ toast(e.message||"Ошибка", false); }
}
async function woChangeStatus(id, status){
  try{
    await API(`/api/v1/workorders/${id}/status`, {method:'POST', body: JSON.stringify({status})});
    toast("Статус обновлён");
    renderWorkOrders();
  }catch(e){ toast(e.message||"Ошибка", false); }
}

// --- Supply (Снабжение) ---
async function renderSupply(){
  const [suppliers, pos, sites] = await Promise.all([
    API('/api/v1/suppliers'),
    API('/api/v1/purchase_orders'),
    API('/api/v1/sites?page=1&page_size=100'),
  ]);
  const siteMap = Object.fromEntries((sites.results||[]).map(s=>[s.id, s.name]));
  const poRows = (pos.results||[]).map(p=>[
    p.id,
    p.supplier_name,
    siteMap[p.site_id] || p.site_id,
    p.status,
    p.comment || '—',
    new Date(p.created_at).toLocaleString(),
    `<div class="flex gap-2">
      <button class="btn-ghost" onclick="poSetStatus(${p.id}, 'in_progress')">В работе</button>
      <button class="btn-ghost" onclick="poSetStatus(${p.id}, 'done')">Закрыть</button>
    </div>`
  ]);
  const suppliersRows = (suppliers.results||[]).map(s=>[
    s.id, s.name, s.contact || '—'
  ]);
  const createSup = `<div class="card">
    <div class="text-lg font-semibold mb-2">Новый поставщик</div>
    <div class="grid md:grid-cols-3 gap-3">
      <label class="field"><span>Название</span><input id="sup_name" class="input" placeholder="ООО «МехСнаб»"></label>
      <label class="field"><span>Контакт</span><input id="sup_contact" class="input" placeholder="email / телефон"></label>
      <div class="flex items-end"><button class="btn-primary" onclick="createSupplier()">Создать</button></div>
    </div>
  </div>`;
  const createPO = `<div class="card">
    <div class="text-lg font-semibold mb-2">Новый заказ поставщику</div>
    <div class="grid md:grid-cols-4 gap-3">
      <label class="field"><span>Поставщик (ID)</span><input id="po_sup" class="input" placeholder="1"></label>
      <label class="field"><span>Площадка (ID)</span><input id="po_site" class="input" placeholder="1"></label>
      <label class="field"><span>Комментарий</span><input id="po_comment" class="input" placeholder="Подшипники под ТОиР"></label>
      <div class="flex items-end"><button class="btn-primary" onclick="createPurchaseOrder()">Создать</button></div>
    </div>
  </div>`;
  el("#view").innerHTML = hero("Снабжение","Поставщики и заказы на закупку.")
    + createSup
    + createPO
    + `<div class="card">
         <div class="text-lg font-semibold mb-2">Поставщики</div>
         ${tplTable(["ID","Название","Контакт"], suppliersRows, {sortable:[0,1]})}
       </div>
       <div class="card mt-4">
         <div class="text-lg font-semibold mb-2">Заказы поставщикам</div>
         ${tplTable(["ID","Поставщик","Площадка","Статус","Комментарий","Создан","Действия"], poRows, {sortable:[0,1,2,3,5]})}
       </div>`;
}
async function createSupplier(){
  const payload = {
    name: el("#sup_name").value,
    contact: el("#sup_contact").value || null
  };
  try{
    await API('/api/v1/suppliers', {method:'POST', body: JSON.stringify(payload)});
    toast("Поставщик создан");
    renderSupply();
  }catch(e){ toast(e.message||"Ошибка", false); }
}
async function createPurchaseOrder(){
  const payload = {
    supplier_id: parseInt(el("#po_sup").value),
    site_id: parseInt(el("#po_site").value),
    comment: el("#po_comment").value || null
  };
  try{
    await API('/api/v1/purchase_orders', {method:'POST', body: JSON.stringify(payload)});
    toast("Заказ создан");
    renderSupply();
  }catch(e){ toast(e.message||"Ошибка", false); }
}
async function poSetStatus(id, status){
  try{
    await API(`/api/v1/purchase_orders/${id}`, {
      method:'PUT',
      body: JSON.stringify({status})
    });
    toast("Статус заказа обновлён");
    renderSupply();
  }catch(e){ toast(e.message||"Ошибка", false); }
}

// --- Planning (Планирование) ---
async function renderPlanning(){
  const [plans, sites] = await Promise.all([
    API('/api/v1/plans'),
    API('/api/v1/sites?page=1&page_size=100')
  ]);
  const siteMap = Object.fromEntries((sites.results||[]).map(s=>[s.id, s.name]));
  const planRows = (plans.results||[]).map(p=>[
    p.id,
    siteMap[p.site_id] || p.site_id,
    p.period,
    p.status,
    `<button class="btn-ghost" onclick="openPlan(${p.id})">Открыть</button>`
  ]);
  const create = `<div class="card">
    <div class="text-lg font-semibold mb-2">Новый план</div>
    <div class="grid md:grid-cols-4 gap-3">
      <label class="field"><span>Площадка (ID)</span><input id="pl_site" class="input" value="1"></label>
      <label class="field"><span>Период</span><input id="pl_period" class="input" placeholder="2025-11"></label>
      <label class="field"><span>Статус</span>
        <select id="pl_status" class="input">
          <option value="draft">draft</option>
          <option value="published">published</option>
        </select>
      </label>
      <div class="flex items-end"><button class="btn-primary" onclick="createPlan()">Создать</button></div>
    </div>
  </div>`;
  el("#view").innerHTML = hero("Планирование производства","Годовые / квартальные / месячные планы.")
    + create
    + tplTable(["ID","Площадка","Период","Статус",""], planRows, {sortable:[0,1,2,3]});
}
async function createPlan(){
  const payload = {
    site_id: parseInt(el("#pl_site").value),
    period: el("#pl_period").value,
    status: el("#pl_status").value
  };
  try{
    await API('/api/v1/plans', {method:'POST', body: JSON.stringify(payload)});
    toast("План создан");
    renderPlanning();
  }catch(e){ toast(e.message||"Ошибка", false); }
}
async function openPlan(id){
  const data = await API(`/api/v1/plans/${id}`);
  const rows = (data.items||[]).map(i=>[i.id, i.product_name, i.quantity]);
  const card = `<div class="card mt-3">
    <div class="text-lg font-semibold mb-2">План #${data.id} (${data.period}) @ ${data.site_name}</div>
    <div class="grid md:grid-cols-3 gap-3">
      <label class="field"><span>Продукт</span><input id="pi_name" class="input" placeholder="Редуктор RX"></label>
      <label class="field"><span>Количество</span><input id="pi_qty" type="number" class="input" value="100"></label>
      <div class="flex items-end"><button class="btn-primary" onclick="addPlanItem(${data.id})">Добавить позицию</button></div>
    </div>
    <div class="mt-3">${tplTable(["ID","Продукт","Количество"], rows, {sortable:[0,1,2]})}</div>
  </div>`;
  el("#view").insertAdjacentHTML('beforeend', card);
}
async function addPlanItem(pid){
  const payload = {
    product_name: el("#pi_name").value,
    quantity: parseInt(el("#pi_qty").value)
  };
  try{
    await API(`/api/v1/plans/${pid}/items`, {method:'POST', body: JSON.stringify(payload)});
    toast("Позиция добавлена");
    renderPlanning();
  }catch(e){ toast(e.message||"Ошибка", false); }
}

// --- Users & Roles ---
async function renderUsers(){
  el("#view").innerHTML = hero("Пользователи и роли", "Администрирование доступа.");
  try{
    const [users, roles] = await Promise.all([
      API('/api/v1/users'),
      API('/api/v1/roles')
    ]);
    const userRows = users.results.map(u=>[
      u.id,
      u.login,
      u.email || '—',
      u.blocked ? 'Да' : 'Нет',
      (u.roles||[]).join(', '),
      `<div class="flex gap-2">
        <button class="btn-ghost" onclick="toggleUserBlock(${u.id}, ${u.blocked})">${u.blocked?'Разблок.':'Блок.'}</button>
        <button class="btn-ghost" onclick="editUserRoles(${u.id}, '${(u.roles||[]).join(', ')}')">Роли</button>
      </div>`
    ]);
    const roleRows = roles.results.map(r=>[r.id, r.name]);
    const createUserCard = `<div class="card">
      <div class="text-lg font-semibold mb-2">Новый пользователь</div>
      <div class="grid md:grid-cols-4 gap-3">
        <label class="field"><span>Логин</span><input id="u_login" class="input" placeholder="user1"></label>
        <label class="field"><span>Пароль</span><input id="u_pass" class="input" type="password" value="pass123"></label>
        <label class="field"><span>Email</span><input id="u_email" class="input" placeholder="user@example.com"></label>
        <label class="field"><span>Роли (через запятую)</span><input id="u_roles" class="input" placeholder="planner,maintainer"></label>
      </div>
      <div class="mt-3"><button class="btn-primary" onclick="createUser()">Создать</button></div>
    </div>`;
    const createRoleCard = `<div class="card">
      <div class="text-lg font-semibold mb-2">Новая роль</div>
      <div class="grid md:grid-cols-3 gap-3">
        <label class="field"><span>Название роли</span><input id="r_name" class="input" placeholder="viewer"></label>
        <div class="flex items-end"><button class="btn-primary" onclick="createRole()">Создать</button></div>
      </div>
    </div>`;
    el("#view").insertAdjacentHTML('beforeend',
      createUserCard
      + createRoleCard
      + `<div class="card mt-3">
           <div class="text-lg font-semibold mb-2">Пользователи</div>
           ${tplTable(["ID","Логин","Email","Блокирован","Роли","Действия"], userRows, {sortable:[0,1,2,3]})}
         </div>
         <div class="card mt-3">
           <div class="text-lg font-semibold mb-2">Роли</div>
           ${tplTable(["ID","Роль"], roleRows, {sortable:[0]})}
         </div>`
    );
  }catch(e){
    el("#view").insertAdjacentHTML(
      'beforeend',
      `<div class="card text-sm text-red-300">
         Недостаточно прав для администрирования пользователей: ${e.message}
       </div>`
    );
  }
}
async function createUser(){
  const roles = el("#u_roles").value.split(",").map(x=>x.trim()).filter(Boolean);
  const payload = {
    login: el("#u_login").value,
    password: el("#u_pass").value,
    email: el("#u_email").value || null,
    roles
  };
  try{
    await API('/api/v1/users', {method:'POST', body: JSON.stringify(payload)});
    toast("Пользователь создан");
    renderUsers();
  }catch(e){ toast(e.message||"Ошибка", false); }
}
async function createRole(){
  const payload = {name: el("#r_name").value};
  try{
    await API('/api/v1/roles', {method:'POST', body: JSON.stringify(payload)});
    toast("Роль создана");
    renderUsers();
  }catch(e){ toast(e.message||"Ошибка", false); }
}
async function toggleUserBlock(id, blocked){
  try{
    await API(`/api/v1/users/${id}`, {method:'PUT', body: JSON.stringify({blocked: !blocked})});
    toast("Статус блокировки изменён");
    renderUsers();
  }catch(e){ toast(e.message||"Ошибка", false); }
}
async function editUserRoles(id, rolesStr){
  const now  = rolesStr || "";
  const next = prompt("Роли через запятую:", now);
  if(next===null) return;
  const roles = next.split(",").map(x=>x.trim()).filter(Boolean);
  try{
    await API(`/api/v1/users/${id}`, {method:'PUT', body: JSON.stringify({roles})});
    toast("Роли обновлены");
    renderUsers();
  }catch(e){ toast(e.message||"Ошибка", false); }
}
