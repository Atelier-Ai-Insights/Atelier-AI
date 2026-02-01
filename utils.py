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
    
    for pres in db:
        if pres.get('nombre_archivo') in selected_set:
            try:
                doc_name = pres.get('nombre_archivo')
                for i, g in enumerate(pres.get("grupos", [])):
                    txt = str(g.get('contenido_texto', ''))
                    if txt and len(txt) > 20:
                        chunk_meta = f"--- DOC: {doc_name} | SECCIÓN: {i+1} ---\n" 
                        full_chunk = f"{chunk_meta}{txt}\n\n"
                        candidate_chunks.append({"text": full_chunk})
            except: pass

    return "".join([c["text"] for c in candidate_chunks])[:max_chars]

def validate_session_integrity(): pass 

# =========================================================
# LÓGICA DE CITAS V10 (SOPORTE VIDEO + PDFS DIRECTOS)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        text = text.replace('“', '"').replace('”', '"')
        
        # 1. COSECHA DE METADATA (Captura el bloque feo del final y lo oculta)
        # Adaptado para capturar tanto [1] archivo como [archivo.pdf] directo
        def harvest_metadata(match):
            try:
                # Intentamos capturar ID o Nombre de archivo
                ref_id = match.group(1).strip()
                raw_context = match.group(2).strip()
                
                # Limpiar el contexto
                clean_context = re.sub(r'^(?:Cita:|Contexto:|Quote:|SECCIÓN:\s*\d+:)\s*', '', raw_context, flags=re.IGNORECASE).strip('"').strip("'")
                
                # Guardamos en el mapa. Si no es un número, usamos el nombre como clave
                source_map[ref_id] = {
                    "file": html.escape(ref_id) if not ref_id.isdigit() else "Fuente",
                    "context": html.escape(clean_context[:300]) + "..."
                }
            except: pass
            return "" # Esto ELIMINA el texto crudo del final

        # Regex agresiva para atrapar el bloque de fuentes del final
        # Busca: [CualquierCosa] ||| CualquierCosa hasta nueva linea o fin
        pattern_metadata = r'\[([^\]]+?)\]\s*\|\|\|\s*(.+?)(?=\n\[|$)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)

        # 2. LIMPIEZA Y FORMATO DE VIDEO [Video: 0:00-0:10]
        # Convierte timestamps en badges rojos
        text = re.sub(
            r'\[Video:\s*([0-9:-]+)\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#ffebee; color:#c62828; border:1px solid #ffcdd2; font-size:0.85em;">🎬 \1</span>', 
            text, 
            flags=re.IGNORECASE
        )

        # 3. LIMPIEZA DE IMAGEN [Imagen]
        text = re.sub(
            r'\[Imagen\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#e0f7fa; color:#006064; border:1px solid #b2ebf2; font-size:0.85em;">🖼️ Ref. Visual</span>', 
            text, 
            flags=re.IGNORECASE
        )

        # 4. LIMPIEZA DE CITAS PDF DIRECTAS (La que sale en tu captura)
        # Patrón: [NombreArchivo.pdf, SECCIÓN: 5]
        def clean_pdf_direct_ref(match):
            try:
                fname = match.group(1).strip()
                section = match.group(2).strip()
                return (
                    f'&nbsp;<span class="tooltip-container">'
                    f'<span class="citation-number" style="background-color:#f0f2f6; color:#444;">📂</span>'
                    f'<span class="tooltip-text">'
                    f'<strong>Fuente:</strong> {html.escape(fname)}<br/>'
                    f'<span style="font-size:0.9em; opacity:0.9;">Sección: {section}</span>'
                    f'</span></span>'
                )
            except: return ""

        text = re.sub(r'\[([^\]]+\.pdf),\s*SECCIÓN:\s*([^\]]+)\]', clean_pdf_direct_ref, text, flags=re.IGNORECASE)

        # 5. LIMPIEZA DE CITAS NUMÉRICAS [1] (Si quedara alguna)
        def replace_numeric_citation(match):
            cid = match.group(1)
            # Intentamos buscar en el mapa, si no existe, mostramos genérico
            return f'<span class="citation-number" style="cursor:default; border:1px solid #eee; color:#aaa;">[{cid}]</span>'

        text = re.sub(r"\[(\d+)\]", replace_numeric_citation, text)

        # 6. LIMPIEZA FINAL DE BASURA
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        return text

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
