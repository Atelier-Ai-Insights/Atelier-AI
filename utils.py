import streamlit as st
import unicodedata
import json
import re
import time
import html
from contextlib import contextmanager

try:
    import fitz
except ImportError:
    fitz = None

# ==============================
# CONFIGURACIÓN
# ==============================
@st.cache_resource
def get_stopwords():
    return {'de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta', 'son', 'sobre'}

@contextmanager
def render_process_status(label="Procesando...", expanded=True):
    status = st.status(label, expanded=expanded)
    try: yield status
    except Exception as e: raise e

def normalize_text(text):
    if not text: return ""
    try: 
        text = str(text).lower()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    except: return str(text).lower()

def extract_brand(filename):
    if not filename: return ""
    if "In-ATL_" in str(filename):
        try: return str(filename).split("In-ATL_")[1].rsplit(".", 1)[0]
        except: pass
    return str(filename)

def clean_text(text): return str(text) if text else ""
def clean_gemini_json(text): return re.sub(r'^```json\s*', '', re.sub(r'^```\s*', '', text, flags=re.MULTILINE), flags=re.MULTILINE).strip()

# ==============================
# LECTURA PDF
# ==============================
def extract_text_from_pdfs(uploaded_files):
    combined_text = ""
    if not uploaded_files or fitz is None: return combined_text
    for file in uploaded_files:
        try:
            with fitz.open(stream=file.getvalue(), filetype="pdf") as doc:
                combined_text += f"\n\n--- DOC: {file.name} ---\n"
                for page in doc: combined_text += page.get_text() + "\n"
        except: pass
    return combined_text

# ==============================
# RAG CONTEXT
# ==============================
def get_relevant_info(db, question, selected_files, max_chars=150000):
    if not selected_files: return ""
    selected_set = set(selected_files)
    candidate_chunks = []
    for pres in db:
        if pres.get('nombre_archivo') in selected_set:
            try:
                doc_name = pres.get('nombre_archivo')
                for i, g in enumerate(pres.get("grupos", [])):
                    txt = str(g.get('contenido_texto', ''))
                    if txt and len(txt) > 20:
                        chunk_meta = f"--- DOC: {doc_name} | SECCIÓN: {i+1} ---\n" 
                        candidate_chunks.append(f"{chunk_meta}{txt}\n\n")
            except: pass
    return "".join(candidate_chunks)[:max_chars]

def validate_session_integrity(): pass 

# =========================================================
# LÓGICA DE CITAS FINAL (Con soporte de limpieza profunda)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        text = text.replace('“', '"').replace('”', '"')
        
        # ---------------------------------------------------------
        # 1. COSECHA DE METADATA (REGEX UNIVERSAL)
        # ---------------------------------------------------------
        # Busca bloques tipo: [ID] ||| Texto...
        # Esta función "absorbe" esa información y la borra del texto visible.
        def harvest_metadata(match):
            try:
                ref_key = match.group(1).strip() # Ej: Archivo.pdf
                raw_content = match.group(2).strip() # Ej: "El texto citado..."

                # Limpieza interna
                clean_content = re.sub(r'^(?:Cita:|Contexto:|Quote:|Evidencia:|SECCIÓN:?\s*\d*:?)\s*', '', raw_content, flags=re.IGNORECASE).strip('"').strip("'")
                
                if ref_key not in source_map:
                    source_map[ref_key] = {"file": html.escape(ref_key), "context": ""}
                
                # Acumular citas (Append)
                separator = "<br/><hr style='margin:4px 0; border-top:1px dashed #ccc;'/>" if source_map[ref_key]["context"] else ""
                source_map[ref_key]["context"] += f"{separator}<em>\"{html.escape(clean_content[:350])}...\"</em>"
                
            except: pass
            return "" # <--- ESTO ES LO QUE BORRA EL TEXTO DEL FINAL

        # Patrón: [LoQueSea] ...espacio... ||| ...espacio... Texto ... (hasta el siguiente [ o fin)
        pattern_metadata = r'\[([^\]]+?)\]\s*\|\|\|\s*(.+?)(?=\s*\[[^\]]+?\]\s*\|\|\||$)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)

        # ---------------------------------------------------------
        # 2. RENDERIZADO DE ICONOS (INYECCIÓN DE TOOLTIPS)
        # ---------------------------------------------------------
        
        # Helper para el HTML
        def tooltip_html(icon, label, content):
            # Si no se encontró verbatim, poner mensaje default
            if not content: content = "<span style='color:#999; font-style:italic;'>(Ver documento completo)</span>"
            
            return (
                f'&nbsp;<span class="tooltip-container">'
                f'<span class="citation-number" style="background-color:#f0f2f6; color:#444; border:1px solid #ddd; cursor:help;">{icon}</span>'
                f'<span class="tooltip-text" style="width:350px;">'
                f'<strong>Fuente:</strong> {html.escape(label)}<br/>'
                f'<div style="margin-top:5px; padding-top:4px; border-top:1px solid #eee; font-size:0.85em; color:#333; max-height:200px; overflow-y:auto;">{content}</div>'
                f'</span></span>'
            )

        # A. Referencias Directas: [Archivo.pdf] o [Archivo.pdf, SECCIÓN 1]
        def replace_direct(match):
            fname = match.group(1).strip()
            
            # Buscar el verbatim capturado
            ctx = source_map.get(fname, {}).get("context", "")
            # Búsqueda difusa si no coincide exacto
            if not ctx:
                for k, v in source_map.items():
                    if fname in k or k in fname:
                        ctx = v["context"]; break
            
            return tooltip_html("📂", fname, ctx)

        text = re.sub(r'\[([^\]]+\.pdf)(?:,\s*SECCIÓN:\s*[^\]]+)?\]', replace_direct, text, flags=re.IGNORECASE)

        # B. Referencias Numéricas: [1]
        def replace_numeric(match):
            cid = match.group(1)
            if cid in source_map:
                data = source_map[cid]
                is_pdf = ".pdf" in data["file"].lower()
                icon = "📂" if is_pdf else f"[{cid}]"
                return tooltip_html(icon, data["file"], data["context"])
            return f'<span class="citation-number" style="color:#aaa;">[{cid}]</span>'

        text = re.sub(r'\[(\d+)\]', replace_numeric, text)

        # C. Videos: [Video: 0:00-0:10]
        text = re.sub(
            r'\[Video:\s*([0-9:-]+)\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#ffebee; color:#c62828; border:1px solid #ffcdd2; font-size:0.85em;">🎬 \1</span>', 
            text, flags=re.IGNORECASE
        )

        # D. Imágenes: [Imagen]
        text = re.sub(
            r'\[Imagen\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#e0f7fa; color:#006064; border:1px solid #b2ebf2; font-size:0.85em;">🖼️ Ref. Visual</span>', 
            text, flags=re.IGNORECASE
        )

        # ---------------------------------------------------------
        # 3. LIMPIEZA FINAL (Basura residual)
        # ---------------------------------------------------------
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas| Bibliografía)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
