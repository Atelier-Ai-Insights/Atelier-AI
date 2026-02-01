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
# CONFIGURACIÓN BÁSICA
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
# LECTURA DE PDFS
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
# RAG: RECUPERACIÓN DE CONTEXTO
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
# LÓGICA INTEGRAL DE TOOLTIPS (V. FINAL)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        text = text.replace('“', '"').replace('”', '"')
        
        # ---------------------------------------------------------
        # 1. COSECHA DE METADATA (Invisible para el usuario)
        # ---------------------------------------------------------
        # Detecta: [ID] ||| Texto...
        # Esta función "come" el texto del final para que no se vea feo.
        def harvest_metadata(match):
            try:
                ref_key = match.group(1).strip() # Puede ser '1' o 'Archivo.pdf'
                raw_content = match.group(2).strip()

                # Limpiamos prefijos comunes que pone la IA
                clean_content = re.sub(r'^(?:Cita:|Contexto:|Quote:|Evidencia:|SECCIÓN:\s*\d+:?)\s*', '', raw_content, flags=re.IGNORECASE).strip('"').strip("'")
                
                # Inicializamos
                if ref_key not in source_map:
                    source_map[ref_key] = {"file": html.escape(ref_key), "context": ""}
                
                # Acumulamos evidencia (concatena si hay varias citas del mismo doc)
                separator = "<br/><hr style='margin:4px 0; border-top:1px dashed #ccc;'/>" if source_map[ref_key]["context"] else ""
                source_map[ref_key]["context"] += f"{separator}<em>\"{html.escape(clean_content[:300])}...\"</em>"
                
            except: pass
            return "" # BORRA el bloque del texto final

        # Regex Universal: Busca [Corchetes] seguido de ||| y texto, hasta el siguiente [Corchete]
        pattern_metadata = r'\[([^\]]+?)\]\s*\|\|\|\s*(.+?)(?=\s*\[[^\]]+?\]\s*\|\|\||$)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)

        # ---------------------------------------------------------
        # 2. RENDERIZADO DE BADGES (Video e Imagen)
        # ---------------------------------------------------------
        
        # Video: [Video: 0:00-0:15] -> 🎬 0:00-0:15
        text = re.sub(
            r'\[Video:\s*([0-9:-]+)\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#ffebee; color:#c62828; border:1px solid #ffcdd2; font-size:0.85em;">🎬 \1</span>', 
            text, flags=re.IGNORECASE
        )
        
        # Imagen: [Imagen] -> 🖼️ Ref. Visual
        text = re.sub(
            r'\[Imagen\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#e0f7fa; color:#006064; border:1px solid #b2ebf2; font-size:0.85em;">🖼️ Ref. Visual</span>', 
            text, flags=re.IGNORECASE
        )

        # ---------------------------------------------------------
        # 3. RENDERIZADO DE CITAS DE REPOSITORIO (El Tooltip)
        # ---------------------------------------------------------
        
        # Helper para construir el HTML del Tooltip
        def build_tooltip_html(display_icon, filename, context_text, extra_label=""):
            # Si no hay contexto capturado, mensaje genérico
            if not context_text: context_text = "(Ver documento original para detalles)"
            
            return (
                f'&nbsp;<span class="tooltip-container">'
                f'<span class="citation-number" style="background-color:#f0f2f6; color:#444; border:1px solid #ddd; cursor:help;">{display_icon}</span>'
                f'<span class="tooltip-text" style="width:320px;">'
                f'<strong>Fuente:</strong> {html.escape(filename)}<br/>'
                f'{extra_label}'
                f'<div style="margin-top:5px; padding-top:4px; border-top:1px solid #eee; font-size:0.9em; color:#333;">{context_text}</div>'
                f'</span></span>'
            )

        # CASO A: Citas tipo Video/Directas -> [Archivo.pdf, SECCIÓN: 5]
        def replace_direct_ref(match):
            fname = match.group(1).strip()
            section = match.group(2).strip() if match.group(2) else ""
            
            # Buscar contexto en lo que cosechamos
            ctx = source_map.get(fname, {}).get("context", "")
            # Si no está exacto, buscar parcial
            if not ctx:
                for k, v in source_map.items():
                    if fname in k or k in fname:
                        ctx = v["context"]; break
            
            extra = f"<span style='font-size:0.8em; opacity:0.8;'>Sección: {section}</span>" if section else ""
            return build_tooltip_html("📂", fname, ctx, extra)

        text = re.sub(r'\[([^\]]+\.pdf)(?:,\s*SECCIÓN:\s*([^\]]+))?\]', replace_direct_ref, text, flags=re.IGNORECASE)

        # CASO B: Citas Numéricas -> [1]
        def replace_numeric_ref(match):
            cid = match.group(1)
            if cid in source_map:
                data = source_map[cid]
                # Si el archivo termina en .pdf, usamos icono carpeta, si no, número
                is_pdf = ".pdf" in data["file"].lower()
                icon = "📂" if is_pdf else f"[{cid}]"
                return build_tooltip_html(icon, data["file"], data["context"])
            else:
                return f'<span class="citation-number" style="color:#aaa;">[{cid}]</span>'

        text = re.sub(r'\[(\d+)\]', replace_numeric_ref, text)

        # ---------------------------------------------------------
        # 4. LIMPIEZA FINAL
        # ---------------------------------------------------------
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
