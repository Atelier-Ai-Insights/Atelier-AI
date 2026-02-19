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
# MOTOR DE BÚSQUEDA INTELIGENTE
# ==============================
def expand_search_query(query):
    """
    Expande la consulta para capturar sinónimos y conceptos relacionales.
   
    """
    if not query or len(query.split()) > 10: return [query]
    try:
        from services.gemini_api import call_gemini_api
        prompt = (
            f"Actúa como un motor de búsqueda experto en investigación de mercados. "
            f"Para el término: '{query}', genera 3 palabras clave alternativas o sinónimos técnicos. "
            f"Devuelve SOLAMENTE las palabras separadas por coma."
        )
        response = call_gemini_api(prompt, generation_config_override={"max_output_tokens": 100})
        if response:
            expanded = [w.strip() for w in response.split(',') if w.strip()]
            return list(dict.fromkeys([query] + expanded))
    except Exception as e:
        print(f"Error expanding query: {e}")
    return [query]

# ==========================================
# RAG: RECUPERACIÓN DE CONTEXTO ROBUSTA
# ==========================================
def get_relevant_info(db, question, selected_files, max_chars=200000):
    """
    Motor RAG de alta capacidad (200k chars).
    Prioriza la densidad informativa para informes extensos.
    """
    if not selected_files: return ""
    selected_set = set(selected_files)
    
    candidate_chunks = []
    total_len = 0
    
    # 1. Recolección de fragmentos del repositorio filtrado
    for pres in db:
        if pres.get('nombre_archivo') in selected_set:
            try:
                doc_name = pres.get('nombre_archivo')
                for i, g in enumerate(pres.get("grupos", [])):
                    txt = str(g.get('contenido_texto', ''))
                    if txt and len(txt) > 20:
                        chunk_meta = f"--- DOC: {doc_name} | SECCIÓN: {i+1} ---\n" 
                        full_chunk = f"{chunk_meta}{txt}\n\n"
                        candidate_chunks.append({
                            "text": full_chunk,
                            "raw_content": txt.lower(),
                            "len": len(full_chunk),
                            "original_idx": len(candidate_chunks)
                        })
                        total_len += len(full_chunk)
            except: pass

    # Si la data total es menor al límite, la enviamos íntegra
    if total_len <= max_chars:
        return "".join([c["text"] for c in candidate_chunks])

    # 2. Puntuación semántica avanzada
    search_terms = expand_search_query(question)
    search_terms = [normalize_text(t) for t in search_terms]
    
    for chunk in candidate_chunks:
        score = 0
        norm_content = normalize_text(chunk["raw_content"])
        for term in search_terms:
            if term in norm_content:
                # Peso 5x para coincidencia exacta con la pregunta
                weight = 5 if term == normalize_text(question) else 2
                score += (norm_content.count(term) * weight)
        chunk["score"] = score

    # 3. Selección de fragmentos hasta agotar el límite de 200k
    scored_chunks = sorted(candidate_chunks, key=lambda x: x["score"], reverse=True)
    
    chunks_to_include = []
    current_chars = 0
    for chunk in scored_chunks:
        if current_chars + chunk["len"] <= max_chars:
            chunks_to_include.append(chunk)
            current_chars += chunk["len"]
        else:
            if current_chars > max_chars * 0.95: break 
    
    chunks_to_include.sort(key=lambda x: x["original_idx"])
    return "".join([c["text"] for c in chunks_to_include])

# =========================================================
# PROCESAMIENTO DE TEXTO (TOOLTIPS E INVISIBILIDAD)
# =========================================================
def process_text_with_tooltips(text):
    """
    Renderiza citas [n] con tooltips y oculta metadatos técnicos.
   
    """
    if not text: return ""

    try:
        source_map = {}
        text = text.replace('“', '"').replace('”', '"')
        
        # 1. Cosecha de metadatos invisible
        def harvest_metadata(match):
            try:
                cid = match.group(1)
                fname = match.group(2).strip()
                
                # Limpieza sistemática de nombres de archivo
                clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
                clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name)
                clean_name = clean_name.replace("In-ATL_", "")
                
                raw_context = match.group(3).strip()
                clean_context = re.sub(r'^(?:Cita:|Contexto:|Quote:)\s*', '', raw_context, flags=re.IGNORECASE).strip('"').strip("'")
                
                source_map[cid] = {
                    "file": html.escape(clean_name),
                    "context": html.escape(clean_context[:350]) + "..."
                }
            except: pass
            return "" 

        # Regex para capturar el bloque de metadatos inyectado por el prompt
        pattern_metadata = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
        text = re.sub(pattern_metadata, harvest_metadata, text, flags=re.DOTALL)
        
        # 2. Renderizado de Tooltips Analíticos
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
        return enriched_body

    except Exception as e:
        print(f"Error Tooltips: {e}")
        return text

def validate_session_integrity(): pass
def reset_report_workflow(): pass
def reset_chat_workflow(): pass
