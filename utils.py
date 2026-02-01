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
# LÓGICA DE CITAS V11 (FIX FINAL PARA TOOLTIPS VACÍOS)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        text = text.replace('“', '"').replace('”', '"')
        
        # 1. COSECHA DE METADATA (REGEX MEJORADA)
        # Ahora detecta citas seguidas aunque no tengan salto de línea: [Doc] ||| ... [Doc] ||| ...
        def harvest_metadata(match):
            try:
                ref_id = match.group(1).strip() # Nombre del archivo
                raw_context = match.group(2).strip()
                
                clean_context = re.sub(r'^(?:Cita:|Contexto:|Quote:|SECCIÓN:\s*\d+:)\s*', '', raw_context, flags=re.IGNORECASE).strip('"').strip("'")
                
                # ACUMULACIÓN: Si el archivo ya existe, agregamos la nueva cita en lugar de sobrescribir
                if ref_id in source_map:
                    source_map[ref_id]["context"] += f"<br/><br/>• {html.escape(clean_context[:200])}..."
                else:
                    source_map[ref_id] = {
                        "file": html.escape(ref_id),
                        "context": f"• {html.escape(clean_context[:200])}..."
                    }
            except: pass
            return "" # Borra el bloque del texto visible

        # Busca: [CualquierCosa] ||| (Contenido) ... hasta encontrar el siguiente [CualquierCosa] ||| o el final
        pattern_metadata = r'\[([^\]]+?)\]\s*\|\|\|\s*(.+?)(?=\s*\[[^\]]+?\]\s*\|\|\||$)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)

        # 2. FORMATO VIDEO [Video: 0:00-0:10] -> Badge Rojo
        text = re.sub(
            r'\[Video:\s*([0-9:-]+)\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#ffebee; color:#c62828; border:1px solid #ffcdd2; font-size:0.85em;">🎬 \1</span>', 
            text, flags=re.IGNORECASE
        )

        # 3. FORMATO IMAGEN [Imagen] -> Badge Azul
        text = re.sub(
            r'\[Imagen\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#e0f7fa; color:#006064; border:1px solid #b2ebf2; font-size:0.85em;">🖼️ Ref. Visual</span>', 
            text, flags=re.IGNORECASE
        )

        # 4. FORMATO PDF DIRECTO (Tooltip con datos cosechados)
        # [NombreArchivo.pdf, SECCIÓN: 5]
        def clean_pdf_direct_ref(match):
            try:
                fname = match.group(1).strip()
                section_info = match.group(2).strip()
                
                # Buscamos si tenemos citas cosechadas para este archivo
                context_html = ""
                if fname in source_map:
                    context_html = f'<div style="margin-top:5px; padding-top:5px; border-top:1px dashed #ddd; font-size:0.9em;"><em>{source_map[fname]["context"]}</em></div>'
                else:
                    context_html = '<div style="margin-top:5px; color:#999; font-style:italic;">(Cita contextual no disponible)</div>'

                return (
                    f'&nbsp;<span class="tooltip-container">'
                    f'<span class="citation-number" style="background-color:#f0f2f6; color:#444; border:1px solid #ddd;">📂</span>'
                    f'<span class="tooltip-text" style="width:300px;">' # Tooltip más ancho
                    f'<strong>Fuente:</strong> {html.escape(fname)}<br/>'
                    f'<span style="opacity:0.8;">Sección: {section_info}</span>'
                    f'{context_html}' # Aquí insertamos el texto recuperado
                    f'</span></span>'
                )
            except: return ""

        text = re.sub(r'\[([^\]]+\.pdf)(?:,\s*SECCIÓN:\s*([^\]]+))?\]', clean_pdf_direct_ref, text, flags=re.IGNORECASE)

        # 5. LIMPIEZA FINAL
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        return text

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
