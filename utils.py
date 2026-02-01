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
    return {
        'de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 
        'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta', 'son', 'sobre',
        'the', 'and', 'to', 'of', 'in', 'is', 'that', 'for', 'it', 'as', 'was', 'with', 'on', 'at', 'by'
    }

@contextmanager
def render_process_status(label="Procesando...", expanded=True):
    status = st.status(label, expanded=expanded)
    try:
        yield status
    except Exception as e:
        raise e

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

def clean_gemini_json(text): 
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    return text.strip()

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
    total_len = 0
    
    for pres in db:
        if pres.get('nombre_archivo') in selected_set:
            try:
                doc_name = pres.get('nombre_archivo')
                doc_title = pres.get('titulo_estudio', doc_name)
                for i, g in enumerate(pres.get("grupos", [])):
                    txt = str(g.get('contenido_texto', ''))
                    if txt and len(txt) > 20:
                        chunk_meta = f"--- DOC: {doc_name} | SECCIÓN: {i+1} ---\n" 
                        full_chunk = f"{chunk_meta}{txt}\n\n"
                        candidate_chunks.append({
                            "text": full_chunk,
                            "original_idx": len(candidate_chunks)
                        })
                        total_len += len(full_chunk)
            except: pass

    # Retorno simple (sin búsqueda semántica compleja para no recargar visual mode)
    return "".join([c["text"] for c in candidate_chunks])[:max_chars]


def validate_session_integrity(): pass 

# =========================================================
# LÓGICA DE CITAS V9 (SOPORTE IMAGEN + TOOLTIPS)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        text = text.replace('“', '"').replace('”', '"')
        
        # 1. COSECHA DE METADATA (Estándar [1] File ||| Context)
        def harvest_metadata(match):
            try:
                cid = match.group(1)
                fname = match.group(2).strip()
                raw_context = match.group(3).strip()
                clean_context = re.sub(r'^(?:Cita:|Contexto:|Quote:)\s*', '', raw_context, flags=re.IGNORECASE).strip('"').strip("'")
                
                source_map[cid] = {
                    "file": html.escape(fname),
                    "context": html.escape(clean_context[:300]) + "..."
                }
            except: pass
            return "" # Borrar del texto visible

        pattern_metadata = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)
        
        # 2. LIMPIEZA DE FUGAS [DOC:...]
        def clean_raw_doc_leaks(match):
            try:
                content = match.group(1).replace("DOC:", "").strip()
                return (
                    f'&nbsp;<span class="tooltip-container">'
                    f'<span class="citation-number" style="background-color:#f0f2f6; color:#444;">📂</span>'
                    f'<span class="tooltip-text"><strong>Fuente:</strong> {html.escape(content)}</span></span>'
                )
            except: return ""
        text = re.sub(r'\[(DOC:.+?)\]', clean_raw_doc_leaks, text, flags=re.IGNORECASE)

        # 3. SOPORTE PARA [IMAGEN] (Nuevo para Visual Mode)
        # Convierte [Imagen] en un badge visual
        text = re.sub(
            r'\[Imagen\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#e0f7fa; color:#006064; border:1px solid #b2ebf2; font-size:0.8em;">🖼️ Ref. Visual</span>', 
            text, 
            flags=re.IGNORECASE
        )

        # 4. LIMPIEZA GENERAL
        text = re.sub(r'\(\s*(?:Contexto|Cita|Quote|Evidencia)\s*:.*?\)', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        # 5. RENDERIZADO DE CITAS NUMÉRICAS [1]
        def replace_citation_group(match):
            content = match.group(1)
            ids = [x.strip() for x in re.findall(r'\d+', content)]
            html_out = []
            for cid in ids:
                data = source_map.get(cid)
                if data:
                    tooltip = (
                        f'<span class="tooltip-container">'
                        f'<span class="citation-number">[{cid}]</span>'
                        f'<span class="tooltip-text">'
                        f'<strong>📂 {data["file"]}</strong><br/>'
                        f'<span style="font-size:0.9em; opacity:0.9;">"{data["context"]}"</span>'
                        f'</span></span>'
                    )
                    html_out.append(tooltip)
                else:
                    html_out.append(f'<span class="citation-number" style="cursor:default; border:1px solid #eee; color:#aaa;">[{cid}]</span>')
            return f" {''.join(html_out)} "

        enriched_body = re.sub(r"\[\s*([\d,\s]+)\s*\]", replace_citation_group, text)
        
        # 6. FOOTER DE SEGURIDAD
        footer = ""
        unique_files = sorted(list(set(v['file'] for v in source_map.values())))
        if unique_files:
            footer = "\n\n<div style='margin-top:20px; padding-top:10px; border-top:1px solid #eee;'>"
            footer += "<p style='font-size:0.85em; color:#666; font-weight:bold; margin-bottom:5px;'>📚 Fuentes Consultadas:</p>"
            footer += "<ul style='font-size:0.8em; color:#666; margin-top:0; padding-left:20px;'>"
            for f in unique_files: footer += f"<li style='margin-bottom:2px;'>{f}</li>"
            footer += "</ul></div>"

        return enriched_body + footer

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
