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
    try:
        status = st.status(label, expanded=expanded)
        yield status
    except:
        yield st.empty()

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
# RAG SIMPLIFICADO
# ==============================
def get_relevant_info(db, question, selected_files, max_chars=150000):
    all_text = ""
    if not selected_files: return ""
    selected_set = set(selected_files)
    
    for pres in db:
        if len(all_text) > max_chars: break
        if pres.get('nombre_archivo') in selected_set:
            try:
                doc_name = pres.get('nombre_archivo')
                header = f"{pres.get('titulo_estudio', doc_name)} - {pres.get('marca', '')}"
                doc_content = f"--- DOC: {doc_name} ---\nMETA: {header}\n"
                for g in pres.get("grupos", []):
                    txt = str(g.get('contenido_texto', ''))
                    if txt: doc_content += f" - {txt}\n"
                
                if len(all_text) + len(doc_content) <= max_chars: all_text += doc_content + "\n\n"
                else: break
            except: pass
    return all_text

def validate_session_integrity():
    pass 

# =========================================================
# LÓGICA DE CITAS V3 (EXTRACCIÓN PROFUNDA)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        # 1. LIMPIEZA PREVIA (Markdown y Caracteres)
        text = text.replace('“', '"').replace('”', '"')
        # Eliminar negritas alrededor de citas: **[1]** -> [1]
        text = re.sub(r'\*\*\[(\d+)\]\*\*', r'[\1]', text)
        # Normalizar Page: [PAGE 8] -> [8]
        text = re.sub(r'\[\s*(?:Page|PAGE|Pag|Pág|p\.?)\s*(\d+)\s*\]', r'[\1]', text, flags=re.IGNORECASE)
        # Fusionar: [1][2] -> [1, 2] y [1], [2] -> [1, 2]
        text = re.sub(r'(?<=\d)\]\s*\[(?=\d)', ', ', text)
        text = re.sub(r'\]\s*[,;]\s*\[', ', ', text)

        source_map = {}

        # ---------------------------------------------------------
        # FASE 1: COSECHA (HARVEST)
        # Buscamos cualquier bloque que parezca una definición de fuente:
        # [ID] ... ||| ... (hasta el siguiente [ID] o fin de texto)
        # ---------------------------------------------------------
        
        # Regex explicada:
        # \[(\d+)\]      -> Captura el ID [1]
        # \s* -> Espacios
        # ([^\[\]\|]+?)  -> Captura el nombre del archivo (todo lo que no sea corchetes o pipe)
        # \s*\|\|\|\s* -> El separador |||
        # (.+?)          -> El contexto/cita (multilínea gracias a re.DOTALL)
        # (?=\n\[\d+\]|$) -> Lookahead: Detente antes del siguiente [N] o el fin del texto
        definitions_pattern = r'\[(\d+)\]\s*([^\[\]\|]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$)'
        
        matches = re.findall(definitions_pattern, text, flags=re.DOTALL)
        
        for cid, fname, ctx in matches:
            # Limpiamos prefijos basura del contexto
            clean_ctx = re.sub(r'^(?:Cita:|Contexto:|Quote:)\s*', '', ctx.strip(), flags=re.IGNORECASE)
            # Quitamos comillas externas si existen
            clean_ctx = clean_ctx.strip('"').strip("'")
            
            source_map[cid] = {
                "file": html.escape(fname.strip()),
                "context": html.escape(clean_ctx)
            }

        # ---------------------------------------------------------
        # FASE 2: BORRADO (PURGE)
        # Eliminamos del texto visible las definiciones que ya capturamos
        # ---------------------------------------------------------
        text = re.sub(definitions_pattern, '', text, flags=re.DOTALL)

        # ---------------------------------------------------------
        # FASE 3: ESCOBA INDUSTRIAL (SWEEP)
        # Borramos residuos que la IA haya dejado "inline" (pegados al párrafo)
        # ---------------------------------------------------------
        
        # A. Borrar frases tipo: Cita: "..." (Contexto: ...)
        # Usamos re.DOTALL para que se coma saltos de línea dentro de la cita
        garbage_a = r'(?:Cita:|Quote:)\s*["“].*?["”]\s*(?:\(Contexto:.*?\))?'
        text = re.sub(garbage_a, '', text, flags=re.DOTALL | re.IGNORECASE)

        # B. Borrar bloques sueltos (Contexto: ...)
        garbage_b = r'\(Contexto:.*?\)'
        text = re.sub(garbage_b, '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # C. Borrar títulos de sección de fuentes vacíos
        garbage_c = r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas)?\s*:?\s*(?:\*\*|##)?\s*(?=\n|$)'
        text = re.sub(garbage_c, '', text, flags=re.IGNORECASE)

        # ---------------------------------------------------------
        # FASE 4: INYECCIÓN DE HTML (RENDER)
        # ---------------------------------------------------------
        def replace_citation_group(match):
            content = match.group(1)
            ids = [x.strip() for x in content.split(',') if x.strip().isdigit()]
            html_out = []
            
            for cid in ids:
                data = source_map.get(cid)
                if data:
                    # Tooltip completo
                    tooltip = (
                        f'<span class="tooltip-container" style="position: relative; display: inline-block;">'
                        f'<span class="citation-number">[{cid}]</span>'
                        f'<span class="tooltip-text">'
                        f'<strong>📂 {data["file"]}</strong><br/>'
                        f'<div style="margin-top:4px; font-size:0.9em;">{data["context"]}</div>'
                        f'</span></span>'
                    )
                    html_out.append(tooltip)
                else:
                    # Si el ID existe en el texto pero la IA no generó definición (source_map),
                    # mostramos solo el número para no romper el texto, pero sin tooltip.
                    html_out.append(f'<span class="citation-simple">[{cid}]</span>')
            
            if not html_out: return match.group(0)
            return f" {' '.join(html_out)} "

        # Buscamos [1], [1, 2], etc.
        enriched_body = re.sub(r"\[\s*([\d,\s]+)\s*\]", replace_citation_group, text)
        
        # ---------------------------------------------------------
        # FASE 5: FOOTER (OPCIONAL)
        # Lista simple de archivos usados al final
        # ---------------------------------------------------------
        footer = ""
        if source_map:
            files = sorted(list(set(v['file'] for v in source_map.values())))
            if files:
                footer = "\n\n<br><hr><h6 style='margin-bottom:5px; color:#666;'>Fuentes:</h6>"
                footer += "<ul style='font-size:0.8em; color:#666; margin-top:0; padding-left:20px;'>"
                for f in files: footer += f"<li>{f}</li>"
                footer += "</ul>"

        return enriched_body + footer

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

# Dummies para resets (para evitar errores de import)
def reset_report_workflow(): pass
def reset_chat_workflow(): pass
def reset_transcript_chat_workflow(): pass
def reset_etnochat_chat_workflow(): pass
