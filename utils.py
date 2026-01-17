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
# LÓGICA DE CITAS V5 (DEDUPLICACIÓN Y LIMPIEZA PROFUNDA)
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        
        # 1. PRE-LIMPIEZA DE FORMATO
        text = text.replace('“', '"').replace('”', '"')
        text = re.sub(r'\*\*\[(\d+)\]\*\*', r'[\1]', text) # Quitar negritas de [1]
        
        # 2. COSECHA DE METADATA (Harvest)
        # Buscamos [N] Archivo ||| Contexto
        # Guardamos la info y ELIMINAMOS ese bloque técnico del texto.
        def harvest_metadata(match):
            cid = match.group(1)
            fname = match.group(2).strip()
            raw_context = match.group(3).strip()
            
            # Limpiamos el contexto para el tooltip
            clean_context = re.sub(r'^(?:Cita:|Contexto:|Quote:)\s*', '', raw_context, flags=re.IGNORECASE).strip('"').strip("'")
            
            # Guardamos en el mapa
            source_map[cid] = {
                "file": html.escape(fname),
                "context": html.escape(clean_context),
                "raw_snippet": raw_context # Guardamos el crudo para buscar duplicados
            }
            return "" # Borramos la definición del texto visible

        # Regex Multilínea para capturar definiciones
        text = re.sub(r'\[(\d+)\]\s*([^\[\]\|]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$)', harvest_metadata, text, flags=re.DOTALL)

        # 3. DEDUPLICACIÓN DE CONTEXTO (LA SOLUCIÓN A CAPTURA 6)
        # Si la IA puso el contexto en la metadata Y TAMBIÉN en el texto, lo borramos del texto.
        for cid, data in source_map.items():
            snippet = data["raw_snippet"]
            if len(snippet) > 15: # Solo si es un texto considerable
                # Buscamos si este snippet aparece flotando en el texto y lo borramos
                # Usamos replace simple para ser rápidos y seguros
                text = text.replace(snippet, "")
                
                # A veces la IA pone el snippet entre comillas o paréntesis en el texto
                text = text.replace(f'"{snippet}"', "")
                text = text.replace(f'({snippet})', "")

        # 4. TRITURADORA DE BASURA Y LISTAS (SOLUCIÓN A CAPTURA 7)
        # Borrar bloques de "Cita: ..." que hayan quedado
        text = re.sub(r'(?:Cita:|Contexto:|Quote:)\s*["“].*?["”]', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'\(Contexto:.*?\)', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Borrar la lista masiva de archivos al final: [File.pdf] ||| [File.pdf]
        # Esta regex busca secuencias repetidas de corchetes y pipes
        text = re.sub(r'(?:\[[^\]]+\.pdf\]\s*(?:\|\|\|)?\s*){2,}', '', text, flags=re.IGNORECASE)
        
        # Borrar pipes huérfanos que hayan sobrevivido
        text = text.replace('|||', '')
        
        # Borrar título "Fuentes Verificadas" si quedó vacío
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas)?\s*:?\s*(?:\*\*|##)?\s*(?=\n|$)', '', text, flags=re.IGNORECASE)

        # 5. RENDERIZADO DE TOOLTIPS
        # Normalizar referencias numéricas: [1][2] -> [1, 2]
        text = re.sub(r'(?<=\d)\]\s*\[(?=\d)', ', ', text)
        text = re.sub(r'\]\s*[,;]\s*\[', ', ', text)

        def replace_citation_group(match):
            content = match.group(1)
            ids = [x.strip() for x in content.split(',') if x.strip().isdigit()]
            html_out = []
            
            for cid in ids:
                data = source_map.get(cid)
                if data:
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
                    html_out.append(f'<span class="citation-simple">[{cid}]</span>')
            
            if not html_out: return match.group(0)
            return f" {' '.join(html_out)} "

        enriched_body = re.sub(r"\[\s*([\d,\s]+)\s*\]", replace_citation_group, text)
        
        # 6. FOOTER
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

# Dummies
def reset_report_workflow(): pass
def reset_chat_workflow(): pass
def reset_transcript_chat_workflow(): pass
def reset_etnochat_chat_workflow(): pass
