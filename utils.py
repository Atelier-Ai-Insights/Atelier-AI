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
# LÓGICA DE CITAS V. FINAL (CIRUGÍA DE FUGAS)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        # Normalizar comillas y limpiar Markdown excesivo que ensucia
        text = text.replace('“', '"').replace('”', '"').replace("`", "")
        
        # ---------------------------------------------------------
        # 1. COSECHA DEL BLOQUE FINAL (Metadata Estándar)
        # ---------------------------------------------------------
        # Busca: [1] ||| Archivo ||| Cita
        def harvest_bottom_metadata(match):
            try:
                ref_id = match.group(1).strip()
                filename = match.group(2).strip()
                raw_quote = match.group(3).strip()
                
                clean_quote = re.sub(r'^(?:Cita:|Contexto:|Quote:|Evidencia:|SECCIÓN:?\s*\d*:?)\s*', '', raw_quote, flags=re.IGNORECASE).strip('"').strip("'")
                
                source_map[ref_id] = {
                    "file": html.escape(filename),
                    "quote": html.escape(clean_quote[:500])
                }
            except: pass
            return "" # Borra este bloque del texto visible

        # Regex para el bloque final: [N] ||| ... ||| ...
        pattern_block = r'\[(\d+)\]\s*\|\|\|\s*(.*?)\s*\|\|\|\s*(.+?)(?=\s*\[\d+\]\s*\|\|\||$)'
        text = re.sub(pattern_block, harvest_bottom_metadata, text, flags=re.DOTALL)

        # ---------------------------------------------------------
        # 2. CIRUGÍA DE FUGAS (ESTO ARREGLA TUS CAPTURAS)
        # ---------------------------------------------------------
        # Detecta cuando la IA escribe: ...texto [1] "Esto es una cita que se fugó"...
        # O también: ...texto [1] (Contexto: Esto es otra fuga)...
        
        def harvest_inline_leaks(match):
            ref_id = match.group(1)
            leaked_content = match.group(2).strip()
            
            # Inicializar si no existe
            if ref_id not in source_map:
                source_map[ref_id] = {"file": "Fuente del documento", "quote": ""}
            
            # Agregar la fuga al tooltip
            clean_leak = leaked_content.strip('"').strip("'").strip('()')
            if clean_leak:
                separator = "<br/><br/>" if source_map[ref_id]["quote"] else ""
                source_map[ref_id]["quote"] += f"{separator}<em>Recuperado del texto:</em><br/>\"{html.escape(clean_leak[:300])}...\""
            
            # Retornamos SOLO el número, ELIMINANDO el texto fugado de la pantalla
            return f"[{ref_id}]"

        # Regex A: Busca [N] seguido de comillas "..." (con o sin saltos de línea)
        pattern_leak_quotes = r'\[(\d+)\]\s*[\n\r]*\s*\"([^\"]+?)\"'
        text = re.sub(pattern_leak_quotes, harvest_inline_leaks, text, flags=re.DOTALL)

        # Regex B: Busca [N] seguido de paréntesis (...) (común en tus capturas)
        pattern_leak_parens = r'\[(\d+)\]\s*[\n\r]*\s*\(([^\)]+?)\)'
        text = re.sub(pattern_leak_parens, harvest_inline_leaks, text, flags=re.DOTALL)

        # Regex C: Busca [N] seguido de texto itálico *...* (común en Markdown)
        pattern_leak_italics = r'\[(\d+)\]\s*[\n\r]*\s*\*([^\*]+?)\*'
        text = re.sub(pattern_leak_italics, harvest_inline_leaks, text, flags=re.DOTALL)


        # ---------------------------------------------------------
        # 3. RENDERIZADO FINAL
        # ---------------------------------------------------------
        
        def create_tooltip(label, title, body, color="background-color:#f0f2f6; color:#444; border:1px solid #ccc;"):
            if not body: body = "<em>(Referencia en el documento)</em>"
            # CSS inline para asegurar que se vea bien en fondo oscuro/claro
            return (
                f'&nbsp;<span class="tooltip-container">'
                f'<span class="citation-number" style="{color} font-weight:bold; cursor:help;">{label}</span>'
                f'<span class="tooltip-text" style="width:320px; text-align:left;">'
                f'<div style="color:#FFD700; font-weight:bold; margin-bottom:4px;">📂 {title}</div>'
                f'<div style="max-height:150px; overflow-y:auto; padding-right:5px; font-size:0.9em; line-height:1.3; color:#f0f0f0;">'
                f'{body}'
                f'</div>'
                f'</span></span>'
            )

        # A. Numéricas [N]
        def replace_numeric(match):
            cid = match.group(1)
            if cid in source_map:
                data = source_map[cid]
                display_file = data["file"] if len(data["file"]) < 30 else data["file"][:27]+"..."
                return create_tooltip(f"[{cid}]", display_file, data["quote"])
            else:
                return create_tooltip(f"[{cid}]", "Fuente", "")

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

        # D. Limpieza final de basura
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas| Bibliografía)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
