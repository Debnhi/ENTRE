"use strict";

const $ = (s, r = document) => r.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ESTADO = { VIGENTE: "Vigente", POR_VENCER: "Por vencer", VENCIDA: "Vencida", SIN_REGISTRO: "Sin registro", PENDIENTE: "Pendiente", RESUELTA: "Resuelta" };
const ROL_LABEL = { instructor: "Instructor", supervisor: "Supervisor", medico: "Servicio médico", admin: "Administrador" };
const badge = (e) => `<span class="badge b-${esc(e)}">${esc(ESTADO[e] || e)}</span>`;
const fmt = (d) => (d ? d.split("-").reverse().join("/") : "—");
const initials = (s) => (s || "?").replace(/\.demo$/i, "").split(/[.\s_-]/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("") || "?";

// ---------------------------------------------------------------- iconos (SVG propios, sin dependencias externas)
const ICON = {
  resumen: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="12" width="4" height="8"/><rect x="10" y="7" width="4" height="13"/><rect x="16" y="3" width="4" height="17"/></svg>',
  licencias: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"/><path d="M9 12l2 2 4-4"/></svg>',
  personas: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><circle cx="17" cy="8" r="2.4"/><path d="M15.5 14.5c2.6.3 4.5 2.3 4.5 5.5"/></svg>',
  captura: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v3H9z"/><path d="M8.5 13l2 2 4-4.5"/></svg>',
  medico: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/></svg>',
  usuarios: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="3.4"/><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6"/><path d="M19 3l1.3 1.3M20.3 3L19 4.3"/></svg>',
  bitacora: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 4h14v16H5z"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>',
};

const NAV = [
  { v: "resumen", t: "Resumen", icon: ICON.resumen, roles: null },
  { v: "licencias", t: "Licencias", icon: ICON.licencias, roles: null },
  { v: "personas", t: "Personas", icon: ICON.personas, roles: null },
  { v: "captura", t: "Captura de calificaciones", icon: ICON.captura, roles: ["instructor"] },
  { v: "medico", t: "Validación médica", icon: ICON.medico, roles: ["supervisor", "instructor", "medico"] },
  { v: "usuarios", t: "Usuarios", icon: ICON.usuarios, roles: ["admin"] },
  { v: "bitacora", t: "Bitácora", icon: ICON.bitacora, roles: null },
];

let session = JSON.parse(localStorage.getItem("gps_session") || "null");
let view = "resumen";
let cache = { habilidades: [], config: null };

// ---------------------------------------------------------------- API
async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${session?.token}` },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) { logout("Tu sesión expiró. Vuelve a iniciar sesión."); throw new Error("Sesión no válida"); }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : (j.detail || []).map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
    } catch (_) { /* sin cuerpo */ }
    throw new Error(msg);
  }
  return opts.raw ? res : res.json();
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 4500);
}
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };
function can(...roles) { return session.rol === "admin" || roles.includes(session.rol); }

// ------------------------------------------------------------ sesión / login
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#lg-submit");
  const err = $("#lg-error");
  err.classList.add("hidden");
  btn.disabled = true; btn.textContent = "Entrando…";
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gmin: $("#lg-gmin").value.trim() }),
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || "No se pudo iniciar sesión");
    session = j; // {token, gmin, nombre, rol, expira} -- el rol viene del servidor
    localStorage.setItem("gps_session", JSON.stringify(session));
    showApp();
  } catch (e2) {
    err.textContent = e2.message;
    err.classList.remove("hidden");
  } finally {
    btn.disabled = false; btn.textContent = "Iniciar sesión";
  }
});

function renderNav() {
  $("#nav").innerHTML = NAV.filter((n) => !n.roles || can(...n.roles))
    .map((n) => `<button data-view="${n.v}">${n.icon}<span>${esc(n.t)}</span></button>`).join("");
  $("#nav").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => go(b.dataset.view)));
}

function expiryTicker() {
  clearInterval(expiryTicker._t);
  expiryTicker._t = setInterval(() => {
    if (!session) return;
    const ms = new Date(session.expira) - new Date();
    if (ms <= 0) { logout("Tu sesión expiró."); return; }
    const mins = Math.round(ms / 60000);
    $("#session-exp").textContent = mins > 1 ? `Sesión activa · expira en ${mins} min` : "Sesión por expirar";
  }, 15000);
}

function showApp() {
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  $("#who-name").textContent = session.nombre;
  $("#who-rol").textContent = ROL_LABEL[session.rol] || session.rol;
  $("#avatar").textContent = initials(session.nombre || session.gmin);
  renderNav();
  expiryTicker();
  go(NAV.find((n) => !n.roles || can(...n.roles))?.v || "resumen");
}

function logout(msg) {
  if (session) api("/auth/logout", { method: "POST" }).catch(() => {});
  localStorage.removeItem("gps_session");
  session = null;
  clearInterval(expiryTicker._t);
  $("#app").classList.add("hidden");
  $("#login").classList.remove("hidden");
  if (msg) toast(msg, true);
}
$("#logout").addEventListener("click", () => logout());

async function go(v) {
  view = v;
  $("#crumb").textContent = NAV.find((n) => n.v === v)?.t || "";
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  try {
    if (!cache.config) cache.config = await (await fetch("/api/config")).json();
    cache.habilidades = await api("/habilidades");
    await VIEWS[v]();
  } catch (e) { if (session) toast(e.message, true); }
}

// ------------------------------------------------------------ diálogo
function openDialog(html) {
  $("#dlg-body").innerHTML = html;
  const d = $("#dlg");
  if (!d.open) d.showModal();
}
const closeDialog = () => $("#dlg").close();
window.closeDialog = closeDialog;

function bar(v, p, x) {
  const t = v + p + x || 1;
  return `<div class="bar" title="Vigentes ${v} · Por vencer ${p} · Vencidas ${x}"><span class="v" style="width:${(v / t) * 100}%"></span><span class="p" style="width:${(p / t) * 100}%"></span><span class="x" style="width:${(x / t) * 100}%"></span></div>`;
}
function donut(v, p, x) {
  const total = v + p + x;
  const pct = total ? [v, p, x].map((n) => (n / total) * 100) : [0, 0, 100];
  const c1 = pct[0], c2 = pct[0] + pct[1];
  const style = total
    ? `background:conic-gradient(var(--ok) 0% ${c1}%, var(--warn) ${c1}% ${c2}%, var(--bad) ${c2}% 100%)`
    : `background:var(--grey)`;
  return `<div class="donut" style="${style}"><div class="donut-center"><span class="n">${total}</span><span class="l">licencias</span></div></div>`;
}
const habOptions = (sel = "") => cache.habilidades.map((h) => `<option value="${h.id}" ${String(h.id) === String(sel) ? "selected" : ""}>${esc(h.nombre)}</option>`).join("");

// ------------------------------------------------------------ vistas
const VIEWS = {
  async resumen() {
    const r = await api("/resumen");
    const rot = r.rotacion;
    $("#main").innerHTML = `
      <h2>Resumen al ${fmt(r.fecha)}</h2>
      <div class="grid g4">
        <div class="card kpi"><div class="n">${r.personas_activas}</div><div class="l">Personas activas</div></div>
        <div class="card kpi ok"><div class="n">${r.licencias.VIGENTE}</div><div class="l">Licencias vigentes</div></div>
        <div class="card kpi warn"><div class="n">${r.licencias.POR_VENCER}</div><div class="l">Por vencer (≤ ${cache.config.umbral_por_vencer_dias} días)</div></div>
        <div class="card kpi bad"><div class="n">${r.licencias.VENCIDA}</div><div class="l">Vencidas</div></div>
      </div>
      <div class="grid g2" style="margin-top:14px">
        <div class="card">
          <h3>Estado de licencias</h3>
          <div class="donut-wrap">
            ${donut(r.licencias.VIGENTE, r.licencias.POR_VENCER, r.licencias.VENCIDA)}
            <div class="legend">
              <div class="row"><span class="dot ok"></span>Vigentes <strong style="margin-left:auto">${r.licencias.VIGENTE}</strong></div>
              <div class="row"><span class="dot warn"></span>Por vencer <strong style="margin-left:auto">${r.licencias.POR_VENCER}</strong></div>
              <div class="row"><span class="dot bad"></span>Vencidas <strong style="margin-left:auto">${r.licencias.VENCIDA}</strong></div>
            </div>
          </div>
          <p class="small muted" style="margin-top:10px">Estado calculado por fecha en cada consulta; nunca se copia un estatus capturado a mano.</p>
        </div>
        <div class="card">
          <h3>Licencias por habilidad</h3>
          <table><tbody>${r.por_habilidad.map((h) => `<tr><td>${esc(h.habilidad)}</td><td style="width:40%">${bar(h.VIGENTE, h.POR_VENCER, h.VENCIDA)}</td><td class="small muted">${h.VIGENTE}/${h.POR_VENCER}/${h.VENCIDA}</td></tr>`).join("") || `<tr><td class="empty">Sin licencias registradas</td></tr>`}</tbody></table>
        </div>
      </div>
      <div class="grid g2" style="margin-top:14px">
        <div class="card"><h3>Códigos médicos</h3>
          <table><tbody>${Object.entries(r.codigos_medicos).map(([k, v]) => `<tr><td>Código ${esc(k)}</td><td><strong>${v}</strong></td></tr>`).join("")}</tbody></table>
          ${r.codigo3_por_vencer.length ? `<div class="note" style="margin-top:10px"><strong>Código 3 por vencer:</strong> ${r.codigo3_por_vencer.map((c) => `${esc(c.gmin)} (${fmt(c.vigencia)})`).join(", ")}</div>` : ""}
          <p class="small muted" style="margin-top:8px">Solicitudes médicas pendientes: <strong>${r.solicitudes_pendientes}</strong></p>
        </div>
        <div class="card"><h3>Rotación de grupos</h3>
          <p>Turno 1: <strong>${rot.asignacion.turno_1}</strong> · Turno 2: <strong>${rot.asignacion.turno_2}</strong> · Turno 3: <strong>${rot.asignacion.turno_3}</strong><br>
          Grupo D (jue–dom) ${rot.grupo_d_trabaja ? "<strong>trabaja hoy</strong>" : "descansa hoy"}.<br>
          <span class="muted">Próxima rotación: ${fmt(rot.siguiente_rotacion)}</span></p>
        </div>
      </div>`;
  },

  async licencias() {
    const m = $("#main");
    m.innerHTML = `<h2>Licencias</h2>
      <div class="toolbar">
        <input id="f-q" placeholder="Buscar GMIN, nombre, habilidad…" size="30">
        <select id="f-estado"><option value="">Todos los estados</option><option value="VENCIDA">Vencidas</option><option value="POR_VENCER">Por vencer</option><option value="VIGENTE">Vigentes</option></select>
        <select id="f-hab"><option value="">Todas las habilidades</option>${habOptions()}</select>
        <button class="btn" id="f-csv">Exportar CSV</button>
      </div><div id="lic-t"></div>`;
    const load = guard(async () => {
      const p = new URLSearchParams({ q: $("#f-q").value, estado: $("#f-estado").value });
      if ($("#f-hab").value) p.set("habilidad_id", $("#f-hab").value);
      const rows = await api("/licencias?" + p);
      $("#lic-t").innerHTML = rows.length ? `<div class="tablewrap"><table><thead><tr><th>GMIN</th><th>Nombre</th><th>C. costos</th><th>Habilidad</th><th>Último curso</th><th>Vigencia</th><th>Días</th><th>Estado</th><th>Cód. médico</th></tr></thead><tbody>
        ${rows.map((l) => `<tr class="click" data-g="${esc(l.gmin)}"><td>${esc(l.gmin)}</td><td>${esc(l.nombre)}</td><td>${esc(l.centro_costos)}</td><td>${esc(l.habilidad)}</td><td>${fmt(l.fecha_curso)} <span class="muted small">${esc(l.tipo)}</span></td><td>${fmt(l.vigencia)}</td><td>${l.dias_restantes}</td><td>${badge(l.estado)}</td><td>${l.medico.codigo}${l.medico.origen === "MPS_AUTO" ? ' <span class="badge b-warn" title="Aplicado automáticamente por código 3 en MPS">MPS</span>' : ""}</td></tr>`).join("")}</tbody></table></div>` : `<div class="card empty">Sin resultados</div>`;
      document.querySelectorAll("#lic-t tr.click").forEach((tr) => tr.addEventListener("click", () => personaDetalle(tr.dataset.g)));
    });
    ["f-q", "f-estado", "f-hab"].forEach((id) => $("#" + id).addEventListener("input", load));
    $("#f-csv").addEventListener("click", guard(async () => {
      const res = await api("/licencias.csv", { raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await res.blob());
      a.download = "licencias.csv";
      a.click();
    }));
    load();
  },

  async personas() {
    const m = $("#main");
    m.innerHTML = `<h2>Personas</h2>
      <div class="toolbar">
        <input id="p-q" placeholder="Buscar GMIN, nombre, centro de costos…" size="30">
        <select id="p-g"><option value="">Todos los grupos</option>${["A", "B", "C", "D"].map((g) => `<option>${g}</option>`).join("")}</select>
        ${can("supervisor") ? '<button class="btn primary" id="p-new">Nueva persona</button>' : ""}
      </div><div id="per-t"></div>`;
    const load = guard(async () => {
      const rows = await api("/personas?" + new URLSearchParams({ q: $("#p-q").value, grupo: $("#p-g").value }));
      $("#per-t").innerHTML = `<div class="tablewrap"><table><thead><tr><th>GMIN</th><th>Nombre</th><th>C. costos</th><th>Grupo</th><th>Código médico</th><th>Vigencia cód.</th></tr></thead><tbody>
        ${rows.map((p) => `<tr class="click" data-g="${esc(p.gmin)}"><td>${esc(p.gmin)}</td><td>${esc(p.nombre)}</td><td>${esc(p.centro_costos)}</td><td>${esc(p.grupo)}</td><td>${p.codigo_medico_efectivo}</td><td>${fmt(p.vigencia_codigo_medico)}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Sin resultados</td></tr>`}</tbody></table></div>`;
      document.querySelectorAll("#per-t tr.click").forEach((tr) => tr.addEventListener("click", () => personaDetalle(tr.dataset.g)));
    });
    ["p-q", "p-g"].forEach((id) => $("#" + id).addEventListener("input", load));
    if ($("#p-new")) $("#p-new").addEventListener("click", nuevaPersona);
    load();
  },

  async captura() {
    if (!can("instructor")) {
      $("#main").innerHTML = `<h2>Captura de calificaciones</h2><div class="card empty">Solo el rol Instructor puede capturar calificaciones.</div>`;
      return;
    }
    const hoy = new Date().toISOString().slice(0, 10);
    $("#main").innerHTML = `<h2>Captura de calificaciones</h2>
      <div class="card" style="max-width:560px"><form id="cap-f">
        <label>GMIN<input name="gmin" required pattern="\\d{6,10}" placeholder="900000001"></label>
        <div class="row"><label>Habilidad<select name="habilidad_id">${habOptions()}</select></label>
        <label>Tipo<select name="tipo"><option value="CURSO">Curso</option><option value="REFRESH">Refresh</option></select></label></div>
        <div class="row"><label>Fecha del curso<input type="date" name="fecha" required value="${hoy}" max="${hoy}"></label>
        <label>Calificación (0–100)<input type="number" name="calificacion" required min="0" max="100" step="0.1"></label></div>
        <p class="small muted">Mínimo aprobatorio: ${cache.config.calificacion_minima}. Solo un curso aprobado genera/renueva la licencia (vigencia ${cache.config.vigencia_licencia_meses} meses calendario).</p>
        <button class="btn primary" type="submit">Guardar</button></form></div>`;
    $("#cap-f").addEventListener("submit", guard(async (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      const r = await api("/cursos", { method: "POST", body: { ...f, habilidad_id: +f.habilidad_id, calificacion: +f.calificacion } });
      toast(r.aprobado ? `Aprobado. Licencia vigente hasta ${fmt(r.vigencia)}` : `Reprobado (mínimo ${r.minimo}). No se renueva la licencia.`, !r.aprobado);
      e.target.reset();
    }));
  },

  async medico() {
    const rows = await api("/solicitudes-medicas");
    $("#main").innerHTML = `<h2>Validación médica</h2>
      ${can("supervisor", "instructor") ? '<div class="toolbar"><button class="btn primary" id="sol-new">Nueva solicitud</button></div>' : ""}
      <div class="tablewrap"><table><thead><tr><th>#</th><th>Fecha</th><th>GMIN</th><th>Persona</th><th>Habilidad</th><th>Motivo</th><th>Solicitante</th><th>Estado</th><th></th></tr></thead><tbody>
      ${rows.map((s) => `<tr><td>${s.id}</td><td>${fmt(s.fecha_solicitud)}</td><td>${esc(s.gmin)}</td><td>${esc(s.nombre)}</td><td>${esc(s.habilidad || "—")}</td><td>${esc(s.motivo)}</td><td>${esc(s.solicitante)}</td>
        <td>${badge(s.estado)}${s.codigo_asignado ? ` <span class="muted small">cód. ${s.codigo_asignado}</span>` : ""}</td>
        <td>${s.estado === "PENDIENTE" && can("medico") ? `<button class="btn small" data-r="${s.id}">Resolver</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="9" class="empty">Sin solicitudes</td></tr>`}</tbody></table></div>
      <p class="small muted">Reglas: código 3 vence a los ${cache.config.vigencia_codigo3_meses} meses y pasa a 2; códigos 1 y 4 solo los cambia el médico. Código 3 asignado en MPS se aplica a Bloqueo de energías peligrosas y Bloqueo de Celdas.</p>`;
    if ($("#sol-new")) $("#sol-new").addEventListener("click", nuevaSolicitud);
    document.querySelectorAll("[data-r]").forEach((b) => b.addEventListener("click", () => resolverSolicitud(rows.find((s) => s.id === +b.dataset.r))));
  },

  async usuarios() {
    if (!can("admin")) {
      $("#main").innerHTML = `<h2>Usuarios</h2><div class="card empty">Solo un administrador puede gestionar cuentas y roles.</div>`;
      return;
    }
    const rows = await api("/usuarios");
    $("#main").innerHTML = `<h2>Usuarios y roles</h2>
      <p class="note">El rol de cada cuenta se define aquí, en la base de datos. Nadie puede elegir su propio rol desde la pantalla de inicio de sesión.</p>
      <div class="toolbar"><button class="btn primary" id="u-new">Nueva cuenta</button></div>
      <div class="tablewrap"><table><thead><tr><th>GMIN</th><th>Nombre</th><th>Rol</th><th>Estado</th><th>Creado</th><th></th></tr></thead><tbody>
      ${rows.map((u) => `<tr><td>${esc(u.gmin)}</td><td>${esc(u.nombre)}</td><td><span class="badge b-grey">${esc(ROL_LABEL[u.rol] || u.rol)}</span></td>
        <td>${u.activo ? badge("VIGENTE").replace("Vigente", "Activo") : badge("VENCIDA").replace("Vencida", "Inactivo")}</td>
        <td>${esc((u.creado || "").slice(0, 10))}</td>
        <td><button class="btn small" data-e="${esc(u.gmin)}">Editar</button></td></tr>`).join("")}</tbody></table></div>`;
    $("#u-new").addEventListener("click", nuevoUsuario);
    document.querySelectorAll("[data-e]").forEach((b) => b.addEventListener("click", () => editarUsuario(rows.find((u) => u.gmin === b.dataset.e))));
  },

  async bitacora() {
    const rows = await api("/bitacora?limit=300");
    $("#main").innerHTML = `<h2>Bitácora de cambios</h2>
      <div class="tablewrap"><table><thead><tr><th>Fecha/hora</th><th>GMIN</th><th>Rol</th><th>Acción</th><th>Referencia</th><th>Detalle</th></tr></thead><tbody>
      ${rows.map((b) => `<tr><td>${esc(b.ts.replace("T", " "))}</td><td>${esc(b.gmin)}</td><td>${esc(b.rol)}</td><td>${esc(b.accion)}</td><td>${esc(b.referencia)}</td><td>${esc(b.detalle)}</td></tr>`).join("")}</tbody></table></div>`;
  },
};

// ------------------------------------------------------------ diálogos de acción
const personaDetalle = guard(async (gmin) => {
  const d = await api("/personas/" + encodeURIComponent(gmin));
  const p = d.persona;
  openDialog(`<div class="dlgh"><div><h3 style="font-size:18px">${esc(p.nombre)}</h3><span class="muted">GMIN ${esc(p.gmin)} · ${esc(p.centro_costos)} · Grupo ${esc(p.grupo)}</span></div><button class="btn small" onclick="closeDialog()">Cerrar</button></div>
    <p>Código médico: <strong>${p.codigo_medico_efectivo}</strong> ${p.vigencia_codigo_medico ? `(vence ${fmt(p.vigencia_codigo_medico)})` : "(no vence automáticamente)"}</p>
    <h3>Habilidades</h3>
    <div class="tablewrap" style="max-height:260px"><table><thead><tr><th>Habilidad</th><th>Último curso</th><th>Vigencia</th><th>Estado</th><th>Cód.</th></tr></thead><tbody>
    ${d.licencias.map((l) => `<tr><td>${esc(l.habilidad)}</td><td>${fmt(l.fecha_curso)}</td><td>${fmt(l.vigencia)}</td><td>${badge(l.estado)}</td><td>${l.medico.codigo}</td></tr>`).join("")}</tbody></table></div>
    <h3 style="margin-top:14px">Historial de cursos</h3>
    <div class="tablewrap" style="max-height:180px"><table><thead><tr><th>Fecha</th><th>Habilidad</th><th>Tipo</th><th>Cal.</th><th>Resultado</th><th>Instructor</th></tr></thead><tbody>
    ${d.cursos.map((c) => `<tr><td>${fmt(c.fecha)}</td><td>${esc(c.habilidad)}</td><td>${esc(c.tipo)}</td><td>${c.calificacion}</td><td>${c.aprobado ? badge("VIGENTE").replace("Vigente", "Aprobado") : badge("VENCIDA").replace("Vencida", "Reprobado")}</td><td>${esc(c.instructor)}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Sin cursos</td></tr>`}</tbody></table></div>
    <div class="toolbar" style="margin-top:14px">
      ${can("supervisor") ? '<button class="btn" id="d-area">Cambiar de área</button>' : ""}
      ${can("medico") ? '<button class="btn" id="d-cod">Asignar código médico</button>' : ""}
    </div>`);
  if ($("#d-area")) $("#d-area").addEventListener("click", () => cambiarArea(p));
  if ($("#d-cod")) $("#d-cod").addEventListener("click", () => asignarCodigo(p));
});

function nuevaPersona() {
  openDialog(`<h3>Nueva persona</h3><form id="np-f">
    <label>GMIN<input name="gmin" required pattern="\\d{6,10}"></label>
    <label>Nombre<input name="nombre" required minlength="2"></label>
    <div class="row"><label>Centro de costos<input name="centro_costos" required></label>
    <label>Grupo<select name="grupo">${["A", "B", "C", "D"].map((g) => `<option>${g}</option>`).join("")}</select></label></div>
    <div class="row"><button class="btn primary" type="submit">Guardar</button><button class="btn" type="button" onclick="closeDialog()">Cancelar</button></div></form>`);
  $("#np-f").addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    await api("/personas", { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
    closeDialog(); toast("Persona creada"); go("personas");
  }));
}

function cambiarArea(p) {
  openDialog(`<h3>Cambio de área · ${esc(p.nombre)}</h3>
    <p class="note">La validación médica sigue a la persona: solo cambian centro de costos y grupo. Código actual: ${p.codigo_medico_efectivo}.</p>
    <form id="ca-f"><div class="row"><label>Centro de costos<input name="centro_costos" required value="${esc(p.centro_costos)}"></label>
    <label>Grupo<select name="grupo">${["A", "B", "C", "D"].map((g) => `<option ${g === p.grupo ? "selected" : ""}>${g}</option>`).join("")}</select></label></div>
    <div class="row"><button class="btn primary" type="submit">Guardar</button><button class="btn" type="button" onclick="closeDialog()">Cancelar</button></div></form>`);
  $("#ca-f").addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    await api(`/personas/${encodeURIComponent(p.gmin)}/area`, { method: "PATCH", body: Object.fromEntries(new FormData(e.target)) });
    closeDialog(); toast("Área actualizada"); go(view);
  }));
}

function codigoForm(extra = "") {
  return `<div class="row"><label>Código médico<select name="codigo">${[1, 2, 3, 4].map((c) => `<option>${c}</option>`).join("")}</select></label>
    <label>Ámbito<select name="ambito"><option value="GENERAL">General</option><option value="MPS">MPS</option></select></label></div>${extra}`;
}

function asignarCodigo(p) {
  openDialog(`<h3>Asignar código médico · ${esc(p.nombre)}</h3><form id="ac-f">${codigoForm()}
    <p class="small muted">Código 3 en ámbito MPS se aplica automáticamente a Bloqueo de energías peligrosas y Bloqueo de Celdas.</p>
    <div class="row"><button class="btn primary" type="submit">Guardar</button><button class="btn" type="button" onclick="closeDialog()">Cancelar</button></div></form>`);
  $("#ac-f").addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    await api(`/personas/${encodeURIComponent(p.gmin)}/codigo-medico`, { method: "POST", body: { codigo: +f.codigo, ambito: f.ambito } });
    closeDialog(); toast("Código actualizado"); go(view);
  }));
}

function nuevaSolicitud() {
  openDialog(`<h3>Nueva solicitud de validación médica</h3><form id="ns-f">
    <label>GMIN<input name="gmin" required pattern="\\d{6,10}"></label>
    <label>Habilidad (opcional)<select name="habilidad_id"><option value="">—</option>${habOptions()}</select></label>
    <label>Motivo<textarea name="motivo" required minlength="3" rows="3"></textarea></label>
    <div class="row"><button class="btn primary" type="submit">Enviar</button><button class="btn" type="button" onclick="closeDialog()">Cancelar</button></div></form>`);
  $("#ns-f").addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    await api("/solicitudes-medicas", { method: "POST", body: { gmin: f.gmin, motivo: f.motivo, habilidad_id: f.habilidad_id ? +f.habilidad_id : null } });
    closeDialog(); toast("Solicitud enviada"); go("medico");
  }));
}

function resolverSolicitud(s) {
  openDialog(`<h3>Resolver solicitud #${s.id}</h3><p>${esc(s.nombre)} (${esc(s.gmin)}): ${esc(s.motivo)}</p>
    <form id="rs-f">${codigoForm('<label>Comentario<textarea name="comentario" rows="2"></textarea></label>')}
    <div class="row"><button class="btn primary" type="submit">Resolver</button><button class="btn" type="button" onclick="closeDialog()">Cancelar</button></div></form>`);
  $("#rs-f").addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    await api(`/solicitudes-medicas/${s.id}/resolver`, { method: "POST", body: { codigo: +f.codigo, ambito: f.ambito, comentario: f.comentario || null } });
    closeDialog(); toast("Solicitud resuelta"); go("medico");
  }));
}

function rolOptions(sel = "") {
  return Object.entries(ROL_LABEL).map(([k, v]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${v}</option>`).join("");
}

function nuevoUsuario() {
  openDialog(`<h3>Nueva cuenta de usuario</h3>
    <p class="note">La cuenta se vincula a una persona que ya exista en "Personas" (se busca por GMIN). El rol se define aquí; la persona no lo elige al iniciar sesión.</p>
    <form id="nu-f">
    <label>GMIN<input name="gmin" required pattern="\\d{6,10}" placeholder="p. ej. 900000014"></label>
    <label>Rol<select name="rol">${rolOptions()}</select></label>
    <div class="row"><button class="btn primary" type="submit">Crear cuenta</button><button class="btn" type="button" onclick="closeDialog()">Cancelar</button></div></form>`);
  $("#nu-f").addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    await api("/usuarios", { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
    closeDialog(); toast("Cuenta creada"); go("usuarios");
  }));
}

function editarUsuario(u) {
  const esUnoMismo = u.gmin === session.gmin;
  openDialog(`<h3>Editar cuenta · ${esc(u.gmin)}</h3>
    <form id="eu-f">
    <div class="row"><label>Rol<select name="rol">${rolOptions(u.rol)}</select></label>
    <label>Estado<select name="activo" ${esUnoMismo ? "disabled" : ""}><option value="true" ${u.activo ? "selected" : ""}>Activo</option><option value="false" ${!u.activo ? "selected" : ""}>Inactivo</option></select></label></div>
    ${esUnoMismo ? '<p class="small muted">No puedes desactivar tu propia cuenta.</p>' : ""}
    <div class="row"><button class="btn primary" type="submit">Guardar</button><button class="btn" type="button" onclick="closeDialog()">Cancelar</button></div></form>`);
  $("#eu-f").addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    await api(`/usuarios/${encodeURIComponent(u.gmin)}`, { method: "PATCH", body: { rol: f.rol, activo: f.activo === "true" } });
    closeDialog(); toast("Cuenta actualizada"); go("usuarios");
  }));
}

// ------------------------------------------------------------ inicio
if (session) {
  if (new Date(session.expira) <= new Date()) logout();
  else showApp();
}
