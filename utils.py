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
def clean_gemini_json(text): 
    # Limpia bloques de código json ```json ... ```
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
# LÓGICA DE CITAS V6 (CORRECCIÓN "FUGA DE CONTEXTO")
# =========================================================
def process_text_with_tooltips(text):
    if not text: return ""

    try:
        source_map = {}
        
        # 1. LIMPIEZA INICIAL
        text = text.replace('“', '"').replace('”', '"')
        
        # 2. COSECHA DE METADATA (Harvest)
        # Buscamos la sección final donde están las definiciones: [N] Archivo ||| Contexto
        def harvest_metadata(match):
            cid = match.group(1)
            fname = match.group(2).strip()
            raw_context = match.group(3).strip()
            
            # Limpiamos prefijos comunes que la IA agrega
            clean_context = re.sub(r'^(?:Cita:|Contexto:|Quote:)\s*', '', raw_context, flags=re.IGNORECASE).strip('"').strip("'")
            
            source_map[cid] = {
                "file": html.escape(fname),
                "context": html.escape(clean_context[:400]) + ("..." if len(clean_context)>400 else "")
            }
            return "" # Borramos la definición del texto visible

        # Esta regex busca el bloque de definiciones al final o entre párrafos
        # Patrón: [Digito] Algo ||| Algo (hasta nueva línea con corchete o fin de string)
        pattern_metadata = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)

        # 3. TRITURADORA DE FUGAS (LA CORRECCIÓN PARA TU CAPTURA)
        # Tu captura muestra texto como: "... [1] (Contexto: ...)"
        # Esto elimina cualquier paréntesis que contenga "Contexto:", "Cita:", etc.
        text = re.sub(r'\(\s*(?:Contexto|Cita|Quote|Evidencia)\s*:.*?\)', '', text, flags=re.IGNORECASE | re.DOTALL)
        
        # También eliminamos si la IA puso el texto crudo entre comillas justo después de la referencia
        # Ej: [1] "el texto de la cita"
        # (Esto es opcional, pero ayuda a limpiar si se ve repetitivo)
        # text = re.sub(r'\[\d+\]\s*".{10,100}?"', '', text) 

        # 4. LIMPIEZA DE BASURA RESTANTE
        # Borrar título "Fuentes Verificadas" si quedó flotando
        text = re.sub(r'(?:\n|^)\s*(?:\*\*|##)?\s*Fuentes(?: Verificadas| Consultadas)?\s*:?\s*(?:\*\*|##)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        # Borrar líneas vacías extra
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 5. RENDERIZADO DE TOOLTIPS (HTML)
        # Normalizar referencias: [1][2] -> [1, 2]
        text = re.sub(r'(?<=\d)\]\s*\[(?=\d)', ', ', text)
        
        def replace_citation_group(match):
            content = match.group(1)
            # Extraemos solo los números, ignorando comas o espacios
            ids = [x.strip() for x in re.findall(r'\d+', content)]
            
            html_out = []
            for cid in ids:
                data = source_map.get(cid)
                if data:
                    # Tooltip interactivo
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
                    # Si no hay metadata, solo mostramos el número estático
                    html_out.append(f'<span class="citation-number" style="cursor:default; border:none;">[{cid}]</span>')
            
            return f" {''.join(html_out)} " # Espacio antes para separar de la palabra

        # Reemplazar [1, 2] o [1] por el HTML
        enriched_body = re.sub(r"\[\s*([\d,\s]+)\s*\]", replace_citation_group, text)
        
        # 6. FOOTER (Lista de fuentes al final)
        footer = ""
        if source_map:
            # Obtenemos lista única de archivos
            files = sorted(list(set(v['file'] for v in source_map.values())))
            if files:
                footer = "\n\n<div style='margin-top:20px; padding-top:10px; border-top:1px solid #eee;'>"
                footer += "<p style='font-size:0.85em; color:#666; font-weight:bold; margin-bottom:5px;'>📚 Fuentes Consultadas:</p>"
                footer += "<ul style='font-size:0.8em; color:#666; margin-top:0; padding-left:20px;'>"
                for f in files: 
                    footer += f"<li style='margin-bottom:2px;'>{f}</li>"
                footer += "</ul></div>"

        return enriched_body + footer

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

# Dummies para evitar errores de importación circular o faltantes
def reset_report_workflow(): pass
def reset_chat_workflow(): pass
def reset_transcript_chat_workflow(): pass
def reset_etnochat_chat_workflow(): pass
