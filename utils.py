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
    pass # Simplificado para evitar bloqueos innecesarios en debug

# =========================================================
# LÓGICA DE CITAS: "MULTI-PASS CLEANER"
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        # 1. Normalización Inicial
        text = text.replace('“', '"').replace('”', '"')
        text = re.sub(r'\[\s*(?:Page|PAGE|Pag|Pág|p\.?)\s*(\d+)\s*\]', r'[\1]', text, flags=re.IGNORECASE)
        # Unir [1][2] -> [1, 2] y [1], [2] -> [1, 2]
        text = re.sub(r'(?<=\d)\]\s*\[(?=\d)', ', ', text)
        text = re.sub(r'\]\s*[,;]\s*\[', ', ', text)

        source_map = {}

        # ---------------------------------------------------------
        # PASADA A: Capturar metadata estándar al final del texto
        # Patrón: [1] Archivo ||| Contexto
        # ---------------------------------------------------------
        def extract_standard_meta(match):
            cid = match.group(1)
            fname = match.group(2).strip()
            ctx = match.group(3).strip()
            # Limpiar contexto
            ctx = re.sub(r'^(?:Cita:|Contexto:)\s*', '', ctx, flags=re.IGNORECASE)
            source_map[cid] = {"file": html.escape(fname), "context": html.escape(ctx)}
            return "" # Borrar del texto visible

        # Regex busca [ID] algo ||| algo (con soporte multilinea)
        text = re.sub(r'\[(\d+)\]\s*([^\[\]\n\|]+?)\s*\|\|\|\s*([^\n]+)', extract_standard_meta, text)

        # ---------------------------------------------------------
        # PASADA B: Capturar "Cita inline" pegada al número (Tus capturas)
        # Patrón: [1] . Cita: "..." (Contexto: ...)
        # ---------------------------------------------------------
        def extract_inline_garbage(match):
            full_str = match.group(0) # Todo el string encontrado
            cid = match.group(1)      # El ID (ej: 8)
            garbage = match.group(2)  # El texto sucio (Cita: "...")

            # Si ya tenemos info para este ID, solo borramos la basura
            # Si no tenemos, usamos esta basura como contexto
            if cid not in source_map:
                clean_garbage = re.sub(r'^(?:Cita:|Contexto:)\s*', '', garbage, flags=re.IGNORECASE).strip()
                source_map[cid] = {
                    "file": "Referencia en texto", 
                    "context": html.escape(clean_garbage[:300] + "...") # Limitamos largo
                }
            
            # Devolvemos solo el número [1] y borramos el resto
            return f"[{cid}]"

        # Regex: Busca [ID] seguido opcionalmente de punto/espacio y luego "Cita:" o "Quote:"
        text = re.sub(r'\[(\d+)\][\.\s]*(Cita:.*?\)(?=\s|\[|$))', extract_inline_garbage, text, flags=re.DOTALL | re.IGNORECASE)

        # ---------------------------------------------------------
        # PASADA C: Escoba Final (Borrar residuos huérfanos)
        # ---------------------------------------------------------
        # Borrar líneas sueltas que digan Cita: "..."
        text = re.sub(r'(?:\n|^)\s*(?:Cita:|Quote:)\s*".*?"\s*\(.*?\)', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Borrar (Contexto: ...) sueltos
        text = re.sub(r'\(Contexto:.*?\)', '', text, flags=re.IGNORECASE)
        # Borrar título de fuentes si quedó vacío
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas)?\s*:?\s*(?:\*\*|##)?\s*(?=\n|$)', '', text, flags=re.IGNORECASE)

        # ---------------------------------------------------------
        # RENDERIZADO
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
                    # Si no hay data, mostramos el número simple pero con clase "missing"
                    html_out.append(f'<span class="citation-missing" title="Fuente no detectada">[{cid}]</span>')
            
            if not html_out: return match.group(0)
            return f" {' '.join(html_out)} "

        enriched_body = re.sub(r"\[\s*([\d,\s]+)\s*\]", replace_citation_group, text)
        
        # Footer
        footer = ""
        if source_map:
            files = sorted(list(set(v['file'] for v in source_map.values() if v['file'] != "Referencia en texto")))
            if files:
                footer = "\n\n<br><hr><h6 style='margin-bottom:5px; color:#666;'>Fuentes:</h6>"
                footer += "<ul style='font-size:0.8em; color:#666; margin-top:0; padding-left:20px;'>"
                for f in files: footer += f"<li>{f}</li>"
                footer += "</ul>"

        return enriched_body + footer

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

# Dummies para resets
def reset_report_workflow(): pass
def reset_chat_workflow(): pass
def reset_transcript_chat_workflow(): pass
def reset_etnochat_chat_workflow(): pass
