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
# PROCESADOR DE CITAS NUMÉRICAS V.FINAL
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        # Normalizar comillas
        text = text.replace('“', '"').replace('”', '"')
        
        # ---------------------------------------------------------
        # 1. COSECHA DE METADATA (FORMATO: [ID] ||| ARCHIVO ||| CITA)
        # ---------------------------------------------------------
        def harvest_metadata(match):
            try:
                ref_id = match.group(1).strip()     # Ej: 1
                filename = match.group(2).strip()   # Ej: archivo.pdf
                raw_quote = match.group(3).strip()  # Ej: "Texto..."

                # Limpieza de prefijos comunes
                clean_quote = re.sub(r'^(?:Cita:|Contexto:|Quote:|Evidencia:|SECCIÓN:?\s*\d*:?)\s*', '', raw_quote, flags=re.IGNORECASE).strip('"').strip("'")
                
                # Guardamos en el mapa
                source_map[ref_id] = {
                    "file": html.escape(filename),
                    "quote": html.escape(clean_quote[:400]) + ("..." if len(clean_quote) > 400 else "")
                }
            except: pass
            return "" # Borrar el bloque de la pantalla

        # Regex: [N] ||| ... ||| ... (Non-greedy)
        # Captura: 1. ID, 2. Archivo, 3. Cita
        pattern_strict = r'\[(\d+)\]\s*\|\|\|\s*(.*?)\s*\|\|\|\s*(.+?)(?=\s*\[\d+\]\s*\|\|\||$)'
        text = re.sub(pattern_strict, harvest_metadata, text, flags=re.DOTALL)
        
        # Regex Fallback (por si la IA olvida el nombre del archivo en el bloque final): [N] ||| Cita
        pattern_fallback = r'\[(\d+)\]\s*\|\|\|\s*(.+?)(?=\s*\[\d+\]\s*\|\|\||$)'
        # Solo aplicamos si no hemos capturado nada, para no romper
        if not source_map:
             def harvest_fallback(match):
                ref_id = match.group(1).strip()
                raw_quote = match.group(2).strip()
                source_map[ref_id] = {"file": "Fuente del Repositorio", "quote": html.escape(raw_quote[:300])}
                return ""
             text = re.sub(pattern_fallback, harvest_fallback, text, flags=re.DOTALL)

        # ---------------------------------------------------------
        # 2. RENDERIZADO EN EL TEXTO
        # ---------------------------------------------------------

        # A. Citas Numéricas [1], [2] -> Badge Gris con Tooltip
        def replace_numeric(match):
            cid = match.group(1)
            if cid in source_map:
                data = source_map[cid]
                # HTML DEL TOOLTIP
                return (
                    f'&nbsp;<span class="tooltip-container">'
                    f'<span class="citation-number" style="background-color:#f0f2f6; color:#444; border:1px solid #ccc; font-weight:bold; cursor:help;">[{cid}]</span>'
                    f'<span class="tooltip-text" style="width:350px;">'
                    f'<strong style="color:#ffd700;">📂 {data["file"]}</strong><br/>'
                    f'<div style="margin-top:6px; padding-top:6px; border-top:1px solid #555; font-size:0.9em; line-height:1.3; color:#eee;">'
                    f'<em>"{data["quote"]}"</em>'
                    f'</div>'
                    f'</span></span>'
                )
            # Si no hay data, se deja el número en gris sin interacción
            return f'<span class="citation-number" style="color:#aaa;">[{cid}]</span>'

        text = re.sub(r'\[(\d+)\]', replace_numeric, text)

        # B. Video [Video: 0:00-0:10] -> Badge Rojo
        text = re.sub(
            r'\[Video:\s*([0-9:-]+)\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#ffebee; color:#c62828; border:1px solid #ffcdd2; font-size:0.85em; font-weight:bold;">🎬 \1</span>', 
            text, flags=re.IGNORECASE
        )

        # C. Imagen [Imagen] -> Badge Azul
        text = re.sub(
            r'\[Imagen\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#e0f7fa; color:#006064; border:1px solid #b2ebf2; font-size:0.85em; font-weight:bold;">🖼️ Visual</span>', 
            text, flags=re.IGNORECASE
        )
        
        # D. Limpieza de basura residual (Referencias directas viejas [Archivo.pdf])
        # Si la IA falla y pone [Archivo.pdf] en el texto, lo convertimos a icono genérico
        text = re.sub(r'\[([^\]]+\.pdf)\]', r' 📂', text, flags=re.IGNORECASE)

        # ---------------------------------------------------------
        # 3. LIMPIEZA FINAL
        # ---------------------------------------------------------
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas| Bibliografía)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
