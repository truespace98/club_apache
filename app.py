"""
Club Apache · Archivo maestro (Streamlit)
-----------------------------------------
Los datos viven en la planilla de Google y las capturas en Google Drive.
Esta app habla con el Apps Script de esa planilla (función doPost).

Secrets necesarios (en Streamlit Cloud: Settings > Secrets):
    APPS_SCRIPT_URL = "https://script.google.com/macros/s/....../exec"
    APPS_SCRIPT_KEY = "la misma API_KEY que está en Codigo.gs"
"""
from __future__ import annotations

import base64
import io
import time
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageOps

st.set_page_config(page_title="Club Apache", page_icon="🏀", layout="wide")

ZONA = ZoneInfo("America/Santiago")
ADMIN_NAMES = {"andriu", "sebastian", "daniel", "carlos"}
VACIO = "—"
MARCAS = [VACIO, "✓", "NO", "N/A"]
ID_COL = "_id"
CAP_COL = "📎 Capturas"
TOTAL_COL = "Total ✓"

# --------------------------------------------------------------------------
# Estilo
# --------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Saira+Condensed:wght@700;800&display=swap');
.block-container{padding-top:1.2rem;max-width:1200px}
.apache-bar{display:flex;align-items:center;gap:12px;background:#14213a;color:#f3f5f8;
  border-radius:14px;padding:14px 18px;margin-bottom:14px}
.apache-bar h1{font-family:'Saira Condensed','Arial Narrow',sans-serif;font-weight:800;font-size:30px;
  letter-spacing:.06em;text-transform:uppercase;margin:0;line-height:1;color:#f3f5f8;padding:0}
.apache-bar p{margin:2px 0 0;font-size:12px;letter-spacing:.12em;text-transform:uppercase;opacity:.7}
.apache-bar .who{margin-left:auto;font-size:13px;border:1px solid rgba(243,245,248,.3);border-radius:999px;padding:4px 12px}
h2.sec{font-family:'Saira Condensed','Arial Narrow',sans-serif;font-weight:800;text-transform:uppercase;
  letter-spacing:.03em;font-size:34px;margin:.2rem 0 0;padding:0}
.notes{color:#5d6b82;white-space:pre-line;margin:.2rem 0 .6rem}
.log-line{padding:8px 0;border-bottom:1px solid #dbe1ea;font-size:14px}
.log-line time{color:#5d6b82;font-size:12px;margin-right:8px;font-variant-numeric:tabular-nums}
.chip{border-radius:6px;padding:1px 7px;border:1px solid #dbe1ea;background:#f3f5f8;font-size:13px}
.chip.old{text-decoration:line-through;color:#5d6b82}
.chip.new{border-color:#d9581c;background:#fbe7dc}
</style>
""",
    unsafe_allow_html=True,
)

BALL = """<svg width="38" height="38" viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="18" fill="#d9581c"/>
<g fill="none" stroke="#14213a" stroke-width="1.8"><circle cx="20" cy="20" r="18"/>
<path d="M2 20h36M20 2v36M7 7c6 6 6 20 0 26M33 7c-6 6-6 20 0 26"/></g></svg>"""


def esc(s) -> str:
    return (str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return " ".join("".join(c for c in s if unicodedata.category(c) != "Mn").split()).lower()


def header(me: dict | None):
    who = ""
    if me:
        who = f'<span class="who"><b>{esc(me["nombre"])}</b>{" · Admin" if me["admin"] else " · Solo lectura"}</span>'
    st.markdown(
        f'<div class="apache-bar">{BALL}<div><h1>Club Apache</h1><p>Archivo maestro · Básquetbol 2026</p></div>{who}</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Conexión con el Apps Script
# --------------------------------------------------------------------------
class ApiError(Exception):
    pass


def _secret(name: str) -> str:
    try:
        return str(st.secrets[name])
    except Exception:
        return ""


def api(fn: str, *args, ses: dict | None = None):
    url, key = _secret("APPS_SCRIPT_URL"), _secret("APPS_SCRIPT_KEY")
    if not url or not key:
        raise ApiError("Falta configurar APPS_SCRIPT_URL y APPS_SCRIPT_KEY en los Secrets de Streamlit.")
    body = {"key": key, "fn": fn, "ses": ses if ses is not None else st.session_state.get("ses"), "args": list(args)}
    last = None
    for intento in range(2):
        try:
            r = requests.post(url, json=body, timeout=60)
            if r.status_code != 200:
                raise ApiError(f"El servidor de Google respondió con un error ({r.status_code}).")
            try:
                res = r.json()
            except ValueError:
                raise ApiError("La URL del Apps Script no respondió como se esperaba. Revisa que sea el link /exec "
                               "y que la implementación tenga acceso para 'Cualquiera'.")
            if not res.get("ok"):
                raise ApiError(str(res.get("error") or "Error desconocido"))
            return res.get("data")
        except requests.RequestException as e:
            last = e
            time.sleep(1.2)
    raise ApiError(f"No se pudo conectar con Google. Inténtalo de nuevo. ({last})")


def es_error_de_sesion(msg: str) -> bool:
    return "CLAVE_ADMIN" in msg or "SIN_NOMBRE" in msg


def mostrar_error(e: Exception):
    msg = str(e)
    if es_error_de_sesion(msg):
        salir("Tu sesión ya no es válida. Vuelve a entrar.")
    if "API_KEY_INCORRECTA" in msg:
        msg = "La clave APPS_SCRIPT_KEY de Streamlit no coincide con API_KEY de Codigo.gs."
    st.error(msg)


@st.cache_data(ttl=20, show_spinner=False)
def datos_cache(admin: bool, _ses: dict, version: int):
    return api("obtenerDatos", ses=_ses)


@st.cache_data(ttl=30, show_spinner=False)
def historial_cache(_ses: dict, version: int):
    return api("obtenerHistorial", ses=_ses)


def refrescar():
    st.session_state["ver"] = st.session_state.get("ver", 0) + 1
    st.cache_data.clear()


def salir(msg: str = ""):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    if msg:
        st.session_state["login_msg"] = msg
    st.rerun()


# --------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------
def pantalla_entrada():
    header(None)
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.subheader("Entrar")
        st.write("Escribe tu nombre y apellido para entrar. Los administradores también escriben su clave para poder editar.")
        if st.session_state.get("login_msg"):
            st.warning(st.session_state.pop("login_msg"))
        with st.form("login"):
            nombre = st.text_input("Tu nombre", max_chars=40, placeholder="Ej.: Sebastián Araya")
            clave = st.text_input("Clave (solo administradores)", type="password")
            ok = st.form_submit_button("Entrar", type="primary", use_container_width=True)
        st.caption("Si te llamas igual que un administrador (Sebastián, Daniel o Carlos), escribe también tu apellido.")
        if ok:
            nombre = " ".join(nombre.split())
            if not nombre:
                st.error("Escribe tu nombre.")
                return
            ses = {"nombre": nombre, "clave": clave if norm(nombre) in ADMIN_NAMES else ""}
            try:
                with st.spinner("Entrando…"):
                    me = api("entrar", ses=ses)
            except ApiError as e:
                m = str(e)
                if "CLAVE_ADMIN" in m:
                    st.error("Clave incorrecta. Si no eres administrador, escribe tu nombre con apellido.")
                else:
                    mostrar_error(e)
                return
            st.session_state["ses"] = ses
            st.session_state["me"] = me
            st.rerun()


# --------------------------------------------------------------------------
# Utilidades de tabla
# --------------------------------------------------------------------------
def a_marca(v: str) -> str:
    m = str(v or "").strip().upper()
    if m in ("X", "✓", "★"):
        return "✓"
    if m == "NO":
        return "NO"
    if m == "N/A":
        return "N/A"
    return VACIO


def de_marca(v: str) -> str:
    return {"✓": "X", "NO": "NO", "N/A": "N/A"}.get(str(v or "").strip(), "")


def limpio(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v).strip()


def etiqueta(fila: dict, cols: list[dict]) -> str:
    partes = []
    for c in cols:
        if c["marca"] or norm(c["nombre"]) in ("n°", "no", "#", "nº"):
            continue
        v = fila.get(c["nombre"], "")
        if v:
            partes.append(v)
        if len(partes) == 2:
            break
    return " ".join(partes) or "(fila sin nombre)"


def tabla(sec: dict) -> tuple[pd.DataFrame, list[dict], list[str]]:
    cols = sec["columnas"]
    marcas = [c["nombre"] for c in cols if c["marca"]]
    comps = sec.get("comprobantes") or {}
    filas = []
    for f in sec["filas"]:
        celdas = f["celdas"]
        d = {ID_COL: f["id"]}
        for c in cols:
            v = celdas[c["i"]] if c["i"] < len(celdas) else ""
            d[c["nombre"]] = a_marca(v) if c["marca"] else v
        if marcas:
            aplica = [m for m in marcas if d[m] != "N/A"]
            d[TOTAL_COL] = f"{sum(1 for m in marcas if d[m] == '✓')}/{len(aplica)}"
        cp = comps.get(f["id"]) or []
        d[CAP_COL] = ", ".join(c for c in marcas if c in cp)
        filas.append(d)
    df = pd.DataFrame(filas, columns=[ID_COL] + [c["nombre"] for c in cols] + ([TOTAL_COL] if marcas else []) + [CAP_COL])
    return df, cols, marcas


# --------------------------------------------------------------------------
# Vista de sección
# --------------------------------------------------------------------------
def vista_seccion(sec: dict, me: dict):
    admin = me["admin"]
    st.markdown(f'<h2 class="sec">{esc(sec["nombre"])}</h2>', unsafe_allow_html=True)
    if sec.get("notas"):
        st.markdown(f'<p class="notes">{esc(sec["notas"])}</p>', unsafe_allow_html=True)
    if not admin:
        st.info("Estás en modo solo lectura. Para hacer cambios, entra con un nombre de administrador y su clave.")

    df, cols, marcas = tabla(sec)
    if not cols:
        st.warning("Esta sección no tiene columnas." + (" Agrégalas en “Ajustes de la sección”." if admin else ""))
        if admin:
            ajustes_seccion(sec)
        return

    q = st.text_input("Buscar", key=f"q_{sec['nombre']}", placeholder=f"Buscar en {sec['nombre']}…", label_visibility="collapsed")
    if q:
        nq = norm(q)
        mask = df.apply(lambda r: any(nq in norm(v) for k, v in r.items() if k != ID_COL), axis=1)
        vista = df[mask].reset_index(drop=True)
    else:
        vista = df

    if marcas:
        st.caption("✓ = sí / pagado · NO = no · N/A = no aplica · — = sin marcar"
                   + (" · 📎 = casillas con captura de transferencia" if admin else ""))

    orden = [c["nombre"] for c in cols] + ([TOTAL_COL] if marcas else []) + ([CAP_COL] if admin and marcas else [])
    alto = min(38 * (len(vista) + 2) + 3, 720)

    if not admin:
        st.dataframe(vista, column_order=orden, hide_index=True, use_container_width=True, height=alto)
        return

    config = {ID_COL: None, TOTAL_COL: st.column_config.TextColumn(TOTAL_COL, disabled=True, width="small"),
              CAP_COL: st.column_config.TextColumn(CAP_COL, disabled=True)}
    for c in cols:
        if c["marca"]:
            config[c["nombre"]] = st.column_config.SelectboxColumn(c["nombre"], options=MARCAS, width="small", required=False)
        else:
            config[c["nombre"]] = st.column_config.TextColumn(c["nombre"], max_chars=5000)

    ver = st.session_state.get("ver", 0)
    editado = st.data_editor(
        vista, column_order=orden, column_config=config, hide_index=True, use_container_width=True,
        num_rows="dynamic", height=alto + 38, key=f"ed_{sec['nombre']}_{ver}_{norm(q)}",
    )

    cambios = calcular_cambios(vista, editado, cols)
    n = len(cambios["editadas"]) + len(cambios["nuevas"]) + len(cambios["eliminadas"])
    c1, c2 = st.columns([1, 3])
    with c1:
        guardar = st.button(f"Guardar cambios ({n})" if n else "Sin cambios", type="primary", disabled=not n,
                            use_container_width=True, key=f"save_{sec['nombre']}")
    with c2:
        if n:
            partes = []
            if cambios["editadas"]:
                partes.append(f"{len(cambios['editadas'])} celda(s) editada(s)")
            if cambios["nuevas"]:
                partes.append(f"{len(cambios['nuevas'])} fila(s) nueva(s)")
            if cambios["eliminadas"]:
                partes.append(f"{len(cambios['eliminadas'])} fila(s) para eliminar")
            st.caption("Pendiente: " + ", ".join(partes) + ". No se guarda hasta que toques el botón.")
        else:
            st.caption("Edita la tabla como una planilla. Para agregar una fila usa la última fila vacía; para eliminar, "
                       "selecciona la fila (casilla a la izquierda) y toca el ícono de basura.")
    if guardar:
        try:
            with st.spinner("Guardando…"):
                r = api("guardarCambios", sec["nombre"], cambios)
            refrescar()
            st.session_state["flash"] = f"Guardado: {r.get('hechos', 0)} cambio(s)." + (
                " " + " ".join(r.get("avisos") or []) if r.get("avisos") else "")
            st.rerun()
        except ApiError as e:
            mostrar_error(e)

    if marcas:
        capturas(sec, df, cols, marcas)
    ajustes_seccion(sec)


def calcular_cambios(orig: pd.DataFrame, edit: pd.DataFrame, cols: list[dict]) -> dict:
    por_id = {r[ID_COL]: r for r in orig.to_dict("records")}
    editadas, nuevas, vistos = [], [], set()
    for r in edit.to_dict("records"):
        rid = limpio(r.get(ID_COL))
        if not rid or rid not in por_id:
            vals = {}
            for c in cols:
                v = limpio(r.get(c["nombre"]))
                v = de_marca(v) if c["marca"] else v
                if v:
                    vals[c["nombre"]] = v
            if vals:
                nuevas.append(vals)
            continue
        vistos.add(rid)
        o = por_id[rid]
        for c in cols:
            nv, ov = limpio(r.get(c["nombre"])), limpio(o.get(c["nombre"]))
            if nv != ov:
                editadas.append({"id": rid, "columna": c["nombre"], "valor": de_marca(nv) if c["marca"] else nv})
    eliminadas = [rid for rid in por_id if rid not in vistos]
    return {"editadas": editadas, "nuevas": nuevas, "eliminadas": eliminadas}


# --------------------------------------------------------------------------
# Capturas de transferencia
# --------------------------------------------------------------------------
def comprimir(archivo) -> str:
    img = Image.open(archivo)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        fondo.paste(img, mask=img.split()[-1])
        img = fondo
    else:
        img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def capturas(sec: dict, df: pd.DataFrame, cols: list[dict], marcas: list[str]):
    with st.expander("📎 Capturas de transferencia"):
        if df.empty:
            st.write("No hay filas en esta sección.")
            return
        registros = df.to_dict("records")
        etiquetas = {r[ID_COL]: etiqueta(r, cols) for r in registros}
        ids = list(etiquetas.keys())
        c1, c2 = st.columns(2)
        rid = c1.selectbox("Fila", ids, format_func=lambda i: etiquetas[i], key=f"cap_f_{sec['nombre']}")
        col = c2.selectbox("Casilla", marcas, key=f"cap_c_{sec['nombre']}")
        fila = next(r for r in registros if r[ID_COL] == rid)
        tiene = col in [x.strip() for x in str(fila.get(CAP_COL, "")).split(",") if x.strip()]
        st.write(f"**{etiquetas[rid]} · {col}** — estado: **{fila.get(col) if fila.get(col) not in (VACIO, '') else 'sin marcar'}** · "
                 + ("tiene captura" if tiene else "sin captura"))

        clave = f"img_{sec['nombre']}_{rid}_{col}"
        if tiene:
            if st.button("Ver captura", key=f"ver_{clave}"):
                try:
                    with st.spinner("Cargando imagen…"):
                        r = api("verComprobante", sec["nombre"], rid, col)
                    st.session_state[clave] = r
                except ApiError as e:
                    mostrar_error(e)
            r = st.session_state.get(clave)
            if r and r.get("data"):
                datos = base64.b64decode(r["data"].split(",", 1)[1])
                st.image(datos, caption=f"Subida por {r.get('usuario', '')} el {r.get('fecha', '')}", width=420)

        arch = st.file_uploader("Subir captura" if not tiene else "Reemplazar captura", type=["jpg", "jpeg", "png", "webp"],
                                key=f"up_{clave}")
        b1, b2, b3 = st.columns(3)
        if arch is not None and b1.button("Guardar captura", type="primary", key=f"save_{clave}"):
            try:
                data = comprimir(arch)
                with st.spinner("Subiendo…"):
                    api("subirComprobante", sec["nombre"], rid, col, data)
                st.session_state.pop(clave, None)
                refrescar()
                st.session_state["flash"] = "Captura guardada."
                st.rerun()
            except ApiError as e:
                mostrar_error(e)
            except Exception:
                st.error("No se pudo leer esa imagen. Prueba con una captura en JPG o PNG.")
        if fila.get(col) != "✓" and b2.button("Marcar ✓ pagado", key=f"paid_{clave}"):
            try:
                api("guardarCelda", sec["nombre"], rid, col, "X")
                refrescar()
                st.session_state["flash"] = "Casilla marcada como pagada."
                st.rerun()
            except ApiError as e:
                mostrar_error(e)
        if tiene:
            seguro = b3.checkbox("Confirmo quitarla", key=f"conf_{clave}")
            if b3.button("Quitar captura", disabled=not seguro, key=f"del_{clave}"):
                try:
                    api("quitarComprobante", sec["nombre"], rid, col)
                    st.session_state.pop(clave, None)
                    refrescar()
                    st.session_state["flash"] = "Captura quitada."
                    st.rerun()
                except ApiError as e:
                    mostrar_error(e)


# --------------------------------------------------------------------------
# Ajustes de la sección
# --------------------------------------------------------------------------
def accion(fn: str, *args, ok: str = "Listo.", nueva_seccion: str | None = None):
    try:
        with st.spinner("Guardando…"):
            r = api(fn, *args)
        refrescar()
        if nueva_seccion is not None:
            st.session_state["seccion"] = r if isinstance(r, str) else nueva_seccion
        st.session_state["flash"] = ok
        st.rerun()
    except ApiError as e:
        mostrar_error(e)


def ajustes_seccion(sec: dict):
    nombre = sec["nombre"]
    with st.expander("⚙️ Ajustes de la sección"):
        with st.form(f"aj_{nombre}"):
            nuevo = st.text_input("Nombre de la sección", value=nombre, max_chars=90)
            notas = st.text_area("Notas (aparecen bajo el título)", value=sec.get("notas", ""))
            if st.form_submit_button("Guardar nombre y notas"):
                if notas.strip() != (sec.get("notas") or "").strip():
                    try:
                        api("guardarNotas", nombre, notas.strip())
                    except ApiError as e:
                        mostrar_error(e)
                        return
                if nuevo.strip() and nuevo.strip() != nombre:
                    accion("renombrarSeccion", nombre, nuevo.strip(), ok="Sección actualizada.", nueva_seccion=nuevo.strip())
                else:
                    refrescar()
                    st.session_state["flash"] = "Sección actualizada."
                    st.rerun()

        st.markdown("**Columnas**")
        for c in sec["columnas"]:
            a, b, d = st.columns([3, 2, 1])
            nn = a.text_input("Nombre", value=c["nombre"], key=f"cn_{nombre}_{c['nombre']}", label_visibility="collapsed")
            tipo = b.selectbox("Tipo", ["Texto", "Marca (✓ / NO / N/A)"], index=1 if c["marca"] else 0,
                               key=f"ct_{nombre}_{c['nombre']}", label_visibility="collapsed")
            if d.button("Aplicar", key=f"ca_{nombre}_{c['nombre']}"):
                if nn.strip() and nn.strip() != c["nombre"]:
                    try:
                        api("renombrarColumna", nombre, c["nombre"], nn.strip())
                    except ApiError as e:
                        mostrar_error(e)
                        return
                quiere_marca = tipo.startswith("Marca")
                if quiere_marca != c["marca"]:
                    accion("cambiarTipoColumna", nombre, nn.strip() or c["nombre"], quiere_marca, ok="Columna actualizada.")
                else:
                    refrescar()
                    st.session_state["flash"] = "Columna actualizada."
                    st.rerun()

        with st.form(f"nc_{nombre}", clear_on_submit=True):
            a, b = st.columns([3, 2])
            nc = a.text_input("Nueva columna", max_chars=60, placeholder="Nombre de la nueva columna")
            nt = b.selectbox("Tipo", ["Texto", "Marca (✓ / NO / N/A)"])
            if st.form_submit_button("+ Agregar columna"):
                if not nc.strip():
                    st.error("Escribe un nombre para la columna.")
                else:
                    accion("agregarColumna", nombre, nc.strip(), nt.startswith("Marca"), ok="Columna agregada.")

        if sec["columnas"]:
            a, b = st.columns([3, 2])
            borrar = a.selectbox("Eliminar columna", [""] + [c["nombre"] for c in sec["columnas"]],
                                 format_func=lambda x: x or "Elige una columna…", key=f"dc_{nombre}")
            if borrar:
                seguro = a.checkbox(f"Sí, eliminar la columna «{borrar}» y sus datos", key=f"dcc_{nombre}")
                if b.button("Eliminar columna", disabled=not seguro, key=f"dcb_{nombre}"):
                    accion("eliminarColumna", nombre, borrar, ok="Columna eliminada.")

        st.divider()
        seguro = st.checkbox(f"Quiero eliminar la sección «{nombre}» con sus {len(sec['filas'])} filas", key=f"ds_{nombre}")
        if st.button("Eliminar sección", disabled=not seguro, key=f"dsb_{nombre}"):
            accion("eliminarSeccion", nombre, ok="Sección eliminada.", nueva_seccion="")


def nueva_seccion():
    st.markdown('<h2 class="sec">Nueva sección</h2>', unsafe_allow_html=True)
    with st.form("nueva", clear_on_submit=True):
        n = st.text_input("Nombre de la sección", max_chars=90, placeholder="Ej.: Campeonato 2027")
        st.caption("Se crea con una columna “Nombre”. Después agregas más columnas en “Ajustes de la sección”.")
        if st.form_submit_button("Crear sección", type="primary"):
            if not n.strip():
                st.error("Escribe un nombre para la sección.")
            else:
                accion("crearSeccion", n.strip(), ok="Sección creada.", nueva_seccion=n.strip())


# --------------------------------------------------------------------------
# Historial
# --------------------------------------------------------------------------
KIND = {"marca": ("casilla marcada", "casillas marcadas"), "celda": ("dato editado", "datos editados"),
        "fila+": ("fila agregada", "filas agregadas"), "fila-": ("fila eliminada", "filas eliminadas"),
        "comp+": ("captura subida", "capturas subidas"), "comp-": ("captura quitada", "capturas quitadas")}


def plural(n: int, par) -> str:
    return f"{n} {par[0] if n == 1 else par[1]}"


def frase(e: dict) -> str:
    s, c, fi, an, de = (f"<b>{esc(e['s'])}</b>", esc(e["c"]), f"<b>{esc(e['fi'])}</b>", esc(e["an"]), esc(e["de"]))
    a = e["a"]
    return {
        "entrar": "entró a la app",
        "marca": f"marcó «{c}» de {fi} en {s}",
        "celda": f"editó «{c}» de {fi} en {s}",
        "fila+": f"agregó una fila{(' (' + fi + ')') if e['fi'] and e['fi'] != '(fila sin nombre)' else ''} en {s}",
        "fila-": f"eliminó la fila {fi} de {s}",
        "seccion+": f"creó la sección {s}",
        "seccion~": f"cambió el nombre de la sección «{an}» a «{de}»",
        "seccion-": f"eliminó la sección {s} ({an})",
        "notas": f"editó las notas de {s}",
        "col+": f"agregó la columna «{c}» ({de}) en {s}",
        "col~": f"cambió el nombre de la columna «{an}» a «{de}» en {s}",
        "coltipo": f"cambió la columna «{c}» de {an} a {de} en {s}",
        "col-": f"eliminó la columna «{c}» de {s} ({an})",
        "comp+": f"{'reemplazó' if e['an'] else 'subió'} la captura de «{c}» de {fi} en {s}",
        "comp-": f"quitó la captura de «{c}»{(' de ' + fi) if e['fi'] else ''} en {s}",
    }.get(a, esc(a))


def valor_legible(e: dict, v: str) -> str:
    if e["a"] == "marca":
        m = a_marca(v)
        return "vacío" if m == VACIO else m
    return v if v != "" else "vacío"


def vista_historial(ses: dict):
    st.markdown('<h2 class="sec">Historial</h2>', unsafe_allow_html=True)
    st.markdown('<p class="notes">Quién entró, qué cambió y cuándo. Solo lo ven los administradores.</p>', unsafe_allow_html=True)
    try:
        with st.spinner("Cargando historial…"):
            hist = historial_cache(ses, st.session_state.get("ver", 0))
    except ApiError as e:
        mostrar_error(e)
        return
    mas = next((e for e in hist if e.get("a") == "mas"), None)
    hist = [e for e in hist if e.get("a") != "mas"]

    personas = sorted({e["u"] for e in hist if e["u"]}, key=norm)
    secciones = sorted({e["s"] for e in hist if e["s"]}, key=norm)
    a, b, c, d = st.columns(4)
    periodo = a.selectbox("Periodo", ["Hoy", "Últimos 7 días", "Últimos 30 días", "Todo"], index=1)
    persona = b.selectbox("Persona", ["Todas"] + personas)
    seccion = c.selectbox("Sección", ["Todas"] + secciones)
    tipo = d.selectbox("Tipo", ["Cambios y entradas", "Solo cambios", "Solo entradas"])
    q = st.text_input("Buscar en el historial", placeholder="Ej.: Magallanes, Enero…")

    ahora = datetime.now(ZONA)
    if periodo == "Hoy":
        desde = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    elif periodo == "Últimos 7 días":
        desde = ahora - timedelta(days=7)
    elif periodo == "Últimos 30 días":
        desde = ahora - timedelta(days=30)
    else:
        desde = None
    min_ms = int(desde.timestamp() * 1000) if desde else 0
    nq = norm(q)
    F = [e for e in hist if e["t"] >= min_ms
         and (persona == "Todas" or e["u"] == persona)
         and (seccion == "Todas" or e["s"] == seccion)
         and (tipo == "Cambios y entradas" or (tipo == "Solo cambios") == (e["a"] != "entrar"))
         and (not nq or nq in norm(" ".join([e["u"], e["s"], e["fi"], e["c"], e["an"], e["de"]])))]

    cambios = [e for e in F if e["a"] != "entrar"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Cambios", len(cambios))
    m2.metric("Entradas", len(F) - len(cambios))
    m3.metric("Personas", len({e["u"] for e in F}))

    st.subheader("Resumen por persona")
    if not F:
        st.write("No hay actividad en este periodo.")
    resumen = []
    for u in {e["u"] for e in F}:
        es = [e for e in F if e["u"] == u]
        ch = [e for e in es if e["a"] != "entrar"]
        grupos: dict[tuple, int] = {}
        for e in ch:
            k = e["a"] if e["a"] in KIND else "estructura"
            grupos[(k, e["s"])] = grupos.get((k, e["s"]), 0) + 1
        partes = [
            (plural(n, ("cambio de estructura", "cambios de estructura")) if k == "estructura" else plural(n, KIND[k]))
            + f" en {esc(s)}"
            for (k, s), n in sorted(grupos.items(), key=lambda x: -x[1])
        ]
        resumen.append((len(ch), len(es) - len(ch), u, es[0]["f"] if es else "", partes))
    for n_ch, n_op, u, ult, partes in sorted(resumen, key=lambda x: (-x[0], -x[1])):
        with st.container(border=True):
            st.markdown(f"**{esc(u)}** · {plural(n_ch, ('cambio', 'cambios'))} · {plural(n_op, ('entrada', 'entradas'))} "
                        f"· última actividad {esc(ult)}", unsafe_allow_html=True)
            st.markdown(" · ".join(partes) if partes else "Solo entró a mirar, sin cambios.", unsafe_allow_html=True)

    st.subheader("Detalle de cada cambio")
    limite = st.session_state.get("hist_lim", 150)
    lineas = []
    for e in F[:limite]:
        diff = ""
        if e["a"] in ("marca", "celda", "notas"):
            diff = (f' <span class="chip old">{esc(valor_legible(e, e["an"]))}</span> → '
                    f'<span class="chip new">{esc(valor_legible(e, e["de"]))}</span>')
        elif e["a"] == "fila-" and e["an"]:
            diff = f' <span class="chip old">{esc(e["an"])}</span>'
        lineas.append(f'<div class="log-line"><time>{esc(e["f"])}</time><b>{esc(e["u"])}</b> {frase(e)}{diff}</div>')
    st.markdown("".join(lineas) or "Nada que mostrar con estos filtros.", unsafe_allow_html=True)
    if len(F) > limite and st.button(f"Mostrar más ({len(F) - limite} restantes)"):
        st.session_state["hist_lim"] = limite + 300
        st.rerun()
    if mas:
        st.caption(f"Se muestran los últimos 5.000 registros. Los {mas['de']} más antiguos siguen en la pestaña “_historial” de la planilla.")


# --------------------------------------------------------------------------
# Principal
# --------------------------------------------------------------------------
def main():
    if "ses" not in st.session_state:
        pantalla_entrada()
        return
    ses, me = st.session_state["ses"], st.session_state["me"]
    header(me)

    try:
        data = datos_cache(me["admin"], ses, st.session_state.get("ver", 0))
    except ApiError as e:
        mostrar_error(e)
        if st.button("Reintentar"):
            refrescar()
            st.rerun()
        return

    nombres = [s["nombre"] for s in data]
    HIST, NUEVA = "🕘 Historial", "➕ Nueva sección"
    opciones = nombres + ([NUEVA, HIST] if me["admin"] else [])
    actual = st.session_state.get("seccion")
    if actual not in opciones:
        actual = opciones[0] if opciones else None

    top_a, top_b, top_c = st.columns([6, 1, 1])
    with top_a:
        elegido = st.pills("Sección", opciones, default=actual, key=f"nav_{st.session_state.get('ver', 0)}",
                           label_visibility="collapsed")
    if elegido and elegido != actual:
        st.session_state["seccion"] = elegido
        st.rerun()
    if top_b.button("Actualizar", use_container_width=True):
        refrescar()
        st.rerun()
    if top_c.button("Salir", use_container_width=True):
        salir()

    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))

    if actual is None:
        st.info("Todavía no hay secciones.")
        return
    if actual == HIST:
        vista_historial(ses)
    elif actual == NUEVA:
        nueva_seccion()
    else:
        vista_seccion(next(s for s in data if s["nombre"] == actual), me)


main()
