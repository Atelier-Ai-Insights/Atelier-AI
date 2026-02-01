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
# LÓGICA DE CITAS V13 (LIMPIEZA AGRESIVA)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        # Normalización de comillas
        text = text.replace('“', '"').replace('”', '"')
        
        # ---------------------------------------------------------
        # 1. COSECHA DE METADATA (Nivel Agresivo)
        # ---------------------------------------------------------
        # Esta función busca patrones [ID] ||| TEXTO y los guarda, 
        # BORRÁNDOLOS del texto visible para que no se vean "fugados".
        def harvest_metadata(match):
            try:
                # Group 1: ID (puede ser '1', '2' o 'Archivo.pdf')
                ref_key = match.group(1).strip()
                # Group 2: El contenido de la cita
                raw_content = match.group(2).strip()

                # Limpieza interna del contenido
                clean_content = re.sub(r'^(?:Cita:|Contexto:|Quote:|SECCIÓN:\s*\d+:?)\s*', '', raw_content, flags=re.IGNORECASE).strip('"').strip("'")
                
                # Si la clave es un nombre de archivo largo, la usamos tal cual
                # Si es un número, también.
                if ref_key not in source_map:
                    source_map[ref_key] = {"file": html.escape(ref_key), "context": ""}
                
                # Acumulamos citas si hay varias para el mismo ID
                separator = "<br/><hr style='margin:4px 0; border-top:1px dashed #ccc;'/>" if source_map[ref_key]["context"] else ""
                source_map[ref_key]["context"] += f"{separator}<em>\"{html.escape(clean_content[:250])}...\"</em>"
                
            except Exception as e: 
                print(f"Error harvesting: {e}")
            return "" # <--- IMPORTANTE: Esto borra el texto sucio de la pantalla

        # Expresión regular "Non-Greedy" que soporta múltiples líneas e items pegados
        # Busca [LO QUE SEA] ||| LO QUE SEA hasta que encuentra el siguiente [
        pattern_metadata = r'\[([^\]]+?)\]\s*\|\|\|\s*(.+?)(?=\s*\[[^\]]+?\]\s*\|\|\||$)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)

        # ---------------------------------------------------------
        # 2. RENDERIZADO DE BADGES (Video e Imagen)
        # ---------------------------------------------------------
        # Video: [Video: 0:00-0:15]
        text = re.sub(
            r'\[Video:\s*([0-9:-]+)\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#ffebee; color:#c62828; border:1px solid #ffcdd2; font-size:0.85em;">🎬 \1</span>', 
            text, flags=re.IGNORECASE
        )
        # Imagen: [Imagen]
        text = re.sub(
            r'\[Imagen\]', 
            r'&nbsp;<span class="citation-number" style="background-color:#e0f7fa; color:#006064; border:1px solid #b2ebf2; font-size:0.85em;">🖼️ Ref. Visual</span>', 
            text, flags=re.IGNORECASE
        )

        # ---------------------------------------------------------
        # 3. RENDERIZADO DE CITAS EN EL TEXTO
        # ---------------------------------------------------------
        
        # CASO A: Citas directas tipo [Archivo.pdf, SECCIÓN: 5] (Típico en Video)
        def replace_direct_ref(match):
            fname = match.group(1).strip()
            extra_info = match.group(2).strip() if match.group(2) else ""
            
            # Buscamos si tenemos contexto cosechado para este archivo
            tooltip_content = ""
            if fname in source_map:
                tooltip_content = source_map[fname]["context"]
            else:
                # Si no hay contexto, intentamos buscar por coincidencia parcial
                for key in source_map:
                    if fname in key or key in fname:
                        tooltip_content = source_map[key]["context"]
                        break
            
            if not tooltip_content: tooltip_content = "(Ver documento completo)"

            return (
                f'&nbsp;<span class="tooltip-container">'
                f'<span class="citation-number" style="background-color:#f0f2f6; color:#444; border:1px solid #ddd;">📂</span>'
                f'<span class="tooltip-text" style="width:300px;">'
                f'<strong>Fuente:</strong> {html.escape(fname)}<br/>'
                f'<span style="font-size:0.85em; opacity:0.8;">{extra_info}</span><br/>'
                f'{tooltip_content}'
                f'</span></span>'
            )
        
        text = re.sub(r'\[([^\]]+\.pdf)(?:,\s*SECCIÓN:\s*([^\]]+))?\]', replace_direct_ref, text, flags=re.IGNORECASE)

        # CASO B: Citas numéricas [1] (Típico en Imagen/Reportes)
        def replace_numeric_ref(match):
            cid = match.group(1)
            if cid in source_map:
                data = source_map[cid]
                # Si el "file" parece un nombre de archivo real (termina en pdf), mostramos icono de carpeta
                icon = "📂" if ".pdf" in data["file"].lower() else f"[{cid}]"
                style = "background-color:#f0f2f6; color:#444; border:1px solid #ddd;" if icon == "📂" else ""
                
                return (
                    f'<span class="tooltip-container">'
                    f'<span class="citation-number" style="{style}">{icon}</span>'
                    f'<span class="tooltip-text" style="width:300px;">'
                    f'<strong>Fuente:</strong> {data["file"]}<br/>'
                    f'{data["context"]}'
                    f'</span></span>'
                )
            return f'<span class="citation-number" style="color:#aaa;">[{cid}]</span>'

        text = re.sub(r'\[(\d+)\]', replace_numeric_ref, text)

        # ---------------------------------------------------------
        # 4. LIMPIEZA FINAL DE CADÁVERES
        # ---------------------------------------------------------
        # Borra cualquier rastro de "Fuentes Verificadas:" o bloques residuales
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        # Borra líneas vacías múltiples
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def reset_report_workflow(): pass
def reset_chat_workflow(): pass
