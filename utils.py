import streamlit as st
import unicodedata
import re
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

def clean_text(text): return str(text) if text else ""

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
# PROCESADOR DE CITAS V. ETIQUETAS (TAG PARSER)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        # Normalizar
        text = text.replace('“', '"').replace('”', '"')
        
        # ---------------------------------------------------------
        # 1. PARSEO DE ETIQUETAS [[REF:ID|FILE|QUOTE]]
        # ---------------------------------------------------------
        # Esta regex es robusta: busca [[REF: ... | ... | ... ]]
        # Funciona incluso si hay saltos de línea dentro de la cita.
        def harvest_tags(match):
            try:
                ref_id = match.group(1).strip()
                filename = match.group(2).strip()
                content = match.group(3).strip()
                
                # Limpieza interna
                content = re.sub(r'^(?:Cita:|Quote:|Evidencia:)\s*', '', content, flags=re.IGNORECASE).strip('"')
                
                source_map[ref_id] = {
                    "file": html.escape(filename),
                    "quote": html.escape(content[:500])
                }
            except: pass
            return "" # BORRA LA ETIQUETA DEL TEXTO VISIBLE

        # Regex: \[\[REF: (\d+) \| (.*?) \| (.*?) \]\]
        # Usamos re.DOTALL para que el punto (.) capture saltos de línea dentro de la etiqueta
        tag_pattern = r'\[\[REF:(\d+)\|(.*?)\|(.*?)\]\]'
        text = re.sub(tag_pattern, harvest_tags, text, flags=re.DOTALL)

        # ---------------------------------------------------------
        # 2. LIMPIEZA DE BASURA RESIDUAL
        # ---------------------------------------------------------
        # A veces la IA deja el título "Referencias:" colgado al final
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Referencias\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)

        # ---------------------------------------------------------
        # 3. RENDERIZADO VISUAL
        # ---------------------------------------------------------
        
        # Helper HTML Tooltip
        def create_tooltip(label, title, body, color="background-color:#f0f2f6; color:#444; border:1px solid #ccc;"):
            if not body: body = "<em>(Referencia contextual)</em>"
            # Diseño compacto y limpio
            return (
                f'&nbsp;<span class="tooltip-container">'
                f'<span class="citation-number" style="{color} font-weight:bold; cursor:help;">{label}</span>'
                f'<span class="tooltip-text" style="width:320px; text-align:left; z-index:999;">'
                f'<div style="color:#FFD700; font-weight:bold; font-size:0.95em; margin-bottom:4px; border-bottom:1px solid #555; padding-bottom:2px;">📂 {title}</div>'
                f'<div style="max-height:150px; overflow-y:auto; font-size:0.9em; line-height:1.3; color:#eee;">'
                f'"{body}"'
                f'</div>'
                f'</span></span>'
            )

        # A. Numéricas [N]
        def replace_numeric(match):
            cid = match.group(1)
            if cid in source_map:
                data = source_map[cid]
                # Nombre de archivo corto si es muy largo
                fname = data["file"]
                if len(fname) > 35: fname = fname[:15] + "..." + fname[-15:]
                
                return create_tooltip(f"[{cid}]", fname, data["quote"])
            else:
                # Fallback visual si la IA olvidó crear la etiqueta
                return create_tooltip(f"[{cid}]", "Fuente del Documento", "")

        text = re.sub(r'\[(\d+)\]', replace_numeric, text)

        # B. Video
        text = re.sub(
            r'\[Video:\s*([0-9:-]+)\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#ffebee; color:#c62828; border:1px solid #ffcdd2; font-size:0.85em; font-weight:bold;">🎬 \1</span>', 
            text, flags=re.IGNORECASE
        )

        # C. Imagen
        text = re.sub(
            r'\[Imagen\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#e0f7fa; color:#006064; border:1px solid #b2ebf2; font-size:0.85em; font-weight:bold;">🖼️ Visual</span>', 
            text, flags=re.IGNORECASE
        )

        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def extract_brand(filename): return "" # Stub
def clean_gemini_json(text): return text # Stub
def reset_report_workflow(): pass
def reset_chat_workflow(): pass
