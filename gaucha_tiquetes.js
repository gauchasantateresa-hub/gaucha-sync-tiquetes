
(function(){
if(document.getElementById('gaucha-fe-btn')){
  var p=document.getElementById('gaucha-fe-panel');
  p.style.display=p.style.display==='none'?'flex':'none';
  return;
}
var btn=document.createElement('div');
btn.id='gaucha-fe-btn';
btn.innerHTML='🧾 Tiquetes FE';
btn.style.cssText='position:fixed;bottom:24px;right:24px;z-index:99999;background:#1D9E75;color:white;padding:12px 20px;border-radius:50px;font-weight:600;font-size:14px;cursor:pointer;box-shadow:0 4px 16px rgba(29,158,117,0.4);display:flex;align-items:center;gap:8px;font-family:-apple-system,sans-serif;user-select:none;transition:all 0.2s;';
btn.onmouseover=function(){btn.style.transform='scale(1.05)';};
btn.onmouseout=function(){btn.style.transform='scale(1)';};
var panel=document.createElement('div');
panel.id='gaucha-fe-panel';
panel.style.cssText='position:fixed;bottom:80px;right:24px;z-index:99998;width:700px;max-height:80vh;background:white;border-radius:16px;box-shadow:0 8px 40px rgba(0,0,0,0.18);display:none;flex-direction:column;overflow:hidden;font-family:-apple-system,sans-serif;';
panel.innerHTML='<div style="background:#1D9E75;color:white;padding:14px 20px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;"><div style="display:flex;align-items:center;gap:10px;"><span style="font-size:20px;">🧾</span><div><div style="font-weight:600;font-size:15px;">Tiquetes Electrónicos</div><div style="font-size:11px;opacity:0.8;">Gaucha Sur → Alegra → Hacienda CR</div></div></div><div style="display:flex;gap:10px;align-items:center;"><button id="gfe-cargar" style="background:rgba(255,255,255,0.2);border:none;color:white;padding:7px 14px;border-radius:20px;cursor:pointer;font-size:13px;font-weight:500;">🔄 Cargar hoy</button><button id="gfe-emitir-todo" style="background:rgba(255,255,255,0.2);border:none;color:white;padding:7px 14px;border-radius:20px;cursor:pointer;font-size:13px;font-weight:500;display:none;">▶ Emitir todos</button><span id="gfe-close" style="cursor:pointer;font-size:20px;opacity:0.8;padding:0 4px;">✕</span></div></div><div style="padding:12px 16px;background:#f0faf6;border-bottom:1px solid #e0f5ee;display:flex;gap:20px;flex-shrink:0;"><div style="text-align:center;"><div id="gfe-stat-total" style="font-size:22px;font-weight:700;color:#1D9E75;">0</div><div style="font-size:11px;color:#666;">Con tarjeta</div></div><div style="text-align:center;"><div id="gfe-stat-ok" style="font-size:22px;font-weight:700;color:#27ae60;">0</div><div style="font-size:11px;color:#666;">Emitidos</div></div><div style="text-align:center;"><div id="gfe-stat-pend" style="font-size:22px;font-weight:700;color:#e67e22;">0</div><div style="font-size:11px;color:#666;">Pendientes</div></div><div style="margin-left:auto;display:flex;align-items:center;"><span id="gfe-status-txt" style="font-size:12px;color:#888;">Listo</span></div></div><div id="gfe-tabla" style="overflow-y:auto;flex:1;"><div style="text-align:center;padding:40px;color:#aaa;"><div style="font-size:32px;margin-bottom:8px;">📋</div><div>Tocá Cargar hoy para ver las órdenes</div></div></div><div id="gfe-progress" style="height:3px;background:#1D9E75;width:0%;transition:width 0.3s;display:none;flex-shrink:0;"></div>';
document.body.appendChild(btn);
document.body.appendChild(panel);
var ordenes=[],corriendo=false;
var WEBHOOK='https://gaucha-sync-tiquetes.onrender.com/webhook',SECRET='gaucha2026',TARJETA_ID=2;
btn.onclick=function(){panel.style.display=panel.style.display==='none'?'flex':'none';};
document.getElementById('gfe-close').onclick=function(){panel.style.display='none';};
function fmt(m){return '\u20a1'+parseFloat(m).toLocaleString('es-CR',{maximumFractionDigits:0});}
function setStatus(t){document.getElementById('gfe-status-txt').textContent=t;}
function actualizarStats(){
  document.getElementById('gfe-stat-total').textContent=ordenes.length;
  document.getElementById('gfe-stat-ok').textContent=ordenes.filter(function(o){return o.estado==='ok';}).length;
  document.getElementById('gfe-stat-pend').textContent=ordenes.filter(function(o){return o.estado==='pendiente'||o.estado==='error';}).length;
}
function renderTabla(){
  var el=document.getElementById('gfe-tabla');
  if(!ordenes.length){el.innerHTML='<div style="text-align:center;padding:30px;color:#aaa;"><div style="font-size:28px;">✅</div><div>No hay órdenes con tarjeta hoy</div></div>';return;}
  var html='<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:#f9f9f9;"><th style="padding:8px 12px;text-align:left;color:#888;font-weight:500;border-bottom:1px solid #eee;">Orden</th><th style="padding:8px 12px;text-align:left;color:#888;font-weight:500;border-bottom:1px solid #eee;">Hora</th><th style="padding:8px 12px;text-align:right;color:#888;font-weight:500;border-bottom:1px solid #eee;">Monto</th><th style="padding:8px 12px;text-align:center;color:#888;font-weight:500;border-bottom:1px solid #eee;">Estado</th><th style="padding:8px 12px;border-bottom:1px solid #eee;"></th></tr></thead><tbody>';
  ordenes.forEach(function(o,i){
    var hora=o.fecha?new Date(o.fecha.replace(' ','T')+'Z').toLocaleTimeString('es-CR',{hour:'2-digit',minute:'2-digit',timeZone:'America/Costa_Rica'}):'';
    var badge=o.estado==='ok'?'<span style="background:#d1f2eb;color:#0e6655;padding:3px 8px;border-radius:12px;font-size:11px;font-weight:600;">✅ Emitido</span>':o.estado==='loading'?'<span style="background:#d6eaf8;color:#1a5276;padding:3px 8px;border-radius:12px;font-size:11px;">⏳ Enviando...</span>':o.estado==='error'?'<span style="background:#fde8e8;color:#a93226;padding:3px 8px;border-radius:12px;font-size:11px;">❌ Error</span>':'<span style="background:#fff3cd;color:#856404;padding:3px 8px;border-radius:12px;font-size:11px;">⏳ Pendiente</span>';
    var btnE=(o.estado==='pendiente'||o.estado==='error')?'<button onclick="gfeEmitirUno('+i+')" style="background:#1D9E75;color:white;border:none;padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:500;">Emitir</button>':'';
    var det=o.consecutivo?'<div style="font-size:10px;color:#888;margin-top:2px;">'+o.consecutivo+'</div>':'';
    html+='<tr style="border-bottom:1px solid #f5f5f5;"><td style="padding:10px 12px;font-weight:500;color:#333;">'+o.nombre+'</td><td style="padding:10px 12px;color:#777;">'+hora+'</td><td style="padding:10px 12px;text-align:right;font-weight:600;color:#1a1a2e;">'+fmt(o.monto)+'</td><td style="padding:10px 12px;text-align:center;">'+badge+det+'</td><td style="padding:10px 12px;text-align:right;">'+btnE+'</td></tr>';
  });
  html+='</tbody></table>';el.innerHTML=html;
}
window.gfeCargar=async function(){
  var btnC=document.getElementById('gfe-cargar');btnC.textContent='⏳ Cargando...';btnC.disabled=true;setStatus('Leyendo Odoo...');
  try{
    var ahora=new Date(),hace24h=new Date(ahora-24*60*60*1000);
    function fmt2(d){return d.toISOString().replace('T',' ').split('.')[0];}
    var rO=await fetch('/web/dataset/call_kw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',method:'call',id:1,params:{model:'pos.order',method:'search_read',args:[[['state','=','done'],['date_order','>=',fmt2(hace24h)],['date_order','<=',fmt2(ahora)]]],kwargs:{fields:['name','amount_total','date_order','payment_ids'],limit:500,order:'date_order asc'}}})});
    var todas=(await rO.json()).result||[];
    if(!todas.length){setStatus('Sin órdenes hoy');btnC.textContent='🔄 Cargar hoy';btnC.disabled=false;return;}
    var payIds=[];todas.forEach(function(o){payIds=payIds.concat(o.payment_ids);});
    var rP=await fetch('/web/dataset/call_kw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',method:'call',id:2,params:{model:'pos.payment',method:'read',args:[payIds],kwargs:{fields:['payment_method_id','pos_order_id']}}})});
    var pagos=(await rP.json()).result||[];
    var tarjetaIds=new Set(pagos.filter(function(p){return p.payment_method_id[0]===TARJETA_ID;}).map(function(p){return p.pos_order_id[0];}));
    var prev={};ordenes.forEach(function(o){prev[o.id]={estado:o.estado,consecutivo:o.consecutivo};});
    ordenes=todas.filter(function(o){return tarjetaIds.has(o.id);}).map(function(o){return {id:o.id,nombre:o.name,monto:o.amount_total,fecha:o.date_order,estado:(prev[o.id]&&prev[o.id].estado)||'pendiente',consecutivo:(prev[o.id]&&prev[o.id].consecutivo)||''};});
    var pend=ordenes.filter(function(o){return o.estado==='pendiente';}).length;
    setStatus(ordenes.length+' con tarjeta · '+pend+' pendientes');
    document.getElementById('gfe-emitir-todo').style.display=pend?'inline-block':'none';
    renderTabla();actualizarStats();
  }catch(e){setStatus('Error: '+e.message);}
  btnC.textContent='🔄 Cargar hoy';btnC.disabled=false;
};
window.gfeEmitirUno=async function(idx){
  var o=ordenes[idx];if(!o||o.estado==='ok')return;
  ordenes[idx].estado='loading';renderTabla();actualizarStats();
  try{
    var resp=await fetch(WEBHOOK,{method:'POST',headers:{'Content-Type':'application/json','X-Webhook-Secret':SECRET},body:JSON.stringify({name:o.nombre,amount_total:o.monto,date_order:o.fecha,state:'done',payment_method_name:'tarjeta'})});
    var data=await resp.json();
    if(resp.ok&&data.status==='ok'){ordenes[idx].estado='ok';ordenes[idx].consecutivo=data.consecutivo||('Alegra #'+data.numero_alegra);}
    else{ordenes[idx].estado='error';}
  }catch(e){ordenes[idx].estado='error';}
  renderTabla();actualizarStats();
};
window.gfeEmitirTodos=async function(){
  if(corriendo){corriendo=false;document.getElementById('gfe-emitir-todo').textContent='▶ Emitir todos';return;}
  corriendo=true;document.getElementById('gfe-emitir-todo').textContent='⏹ Detener';
  var prog=document.getElementById('gfe-progress');prog.style.display='block';
  var pend=[];ordenes.forEach(function(o,i){if(o.estado==='pendiente'||o.estado==='error')pend.push({idx:i});});
  for(var i=0;i<pend.length;i++){
    if(!corriendo)break;
    prog.style.width=Math.round((i/pend.length)*100)+'%';
    setStatus('Emitiendo '+(i+1)+' de '+pend.length+'...');
    await window.gfeEmitirUno(pend[i].idx);
    await new Promise(function(r){setTimeout(r,700);});
  }
  prog.style.width='100%';
  setTimeout(function(){prog.style.display='none';prog.style.width='0%';},1500);
  corriendo=false;document.getElementById('gfe-emitir-todo').textContent='▶ Emitir todos';setStatus('Completado ✅');
};
document.getElementById('gfe-cargar').onclick=window.gfeCargar;
document.getElementById('gfe-emitir-todo').onclick=window.gfeEmitirTodos;
panel.style.display='flex';
window.gfeCargar();
})();
