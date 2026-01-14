import streamlit as st
import unicodedata
import json
import re
import fitz  # PyMuPDF
import time
import html  # Para seguridad HTML
from contextlib import contextmanager

# ==============================
# GESTIÓN DE STOPWORDS
# ==============================
@st.cache_resource
def get_stopwords():
    base_stopwords = {
        'de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 
        'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta', 'son', 'sobre',
        'the', 'and', 'to', 'of', 'in', 'is', 'that', 'for', 'it', 'as', 'was', 'with', 'on', 'at', 'by'
    }
    custom_list = {
        '...', 'p', 'r', 'rta', 'respuesta', 'respuestas', 'si', 'no', 'na', 'ninguno', 'ninguna', 'nan',
        'document', 'presentation', 'python', 'warning', 'created', 'page', 'objetivo', 'tecnica', 
        'investigacion', 'participante', 'sesiones', 'proyecto', 'análisis', 'hola', 'buenos', 'dias',
        'video', 'audio', 'imagen', 'transcripcion'
    }
    return base_stopwords | custom_list

# ==============================
# UI COMPONENTS
# ==============================
@contextmanager
def render_process_status(label="Procesando solicitud...", expanded=True):
    status_container = st.status(label, expanded=expanded)
    try:
        yield status_container
    except Exception as e:
        status_container.update(label="❌ Error en el proceso", state="error", expanded=True)
        st.error(f"Ocurrió un error inesperado: {str(e)}")

# ==============================
# FUNCIONES AUXILIARES
# ==============================
def normalize_text(text):
    if not text: return ""
    try: 
        text = str(text).lower()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    except Exception: return str(text).lower()

def extract_brand(filename):
    if not filename: return ""
    if "In-ATL_" in str(filename):
        try: 
            base = str(filename).replace("\\", "/").split("/")[-1]
            return base.split("In-ATL_")[1].rsplit(".", 1)[0]
        except: pass
    return str(filename)

def clean_text(text):
    return str(text) if text is not None else ""

def clean_gemini_json(text):
    if not text: return ""
    text = str(text).strip()
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    return text.strip()

# ==============================
# PROCESAMIENTO DE PDFS
# ==============================
def extract_text_from_pdfs(uploaded_files):
    combined_text = ""
    if not uploaded_files: return combined_text
    
    for file in uploaded_files:
        try:
            file_bytes = file.getvalue()
            with fitz.open(stream=file_bytes, filetype="pdf") as pdf_document:
                combined_text += f"\n\n--- INICIO DOCUMENTO: {file.name} ---\n\n"
                for page_num, page in enumerate(pdf_document):
                    text = page.get_text()
                    combined_text += text + "\n"
                combined_text += f"\n--- FIN DOCUMENTO: {file.name} ---\n"
        except Exception as e:
            print(f"Error al procesar PDF '{file.name}': {e}")
            combined_text += f"\n\n--- ERROR AL PROCESAR: {file.name} ---\n"
            
    return combined_text

# ==============================
# RAG: MODO BASE DE DATOS
# ==============================
def get_relevant_info(db, question, selected_files, max_chars=150000):
    all_text = ""
    selected_files_set = set(selected_files) if isinstance(selected_files, (list, set)) else set()
    
    if not selected_files_set:
        return ""

    for pres in db:
        if len(all_text) > max_chars:
            all_text += f"\n\n[ALERTA: Contexto truncado por límite ({max_chars} chars)...]"
            break 

        doc_name = pres.get('nombre_archivo')
        if doc_name and doc_name in selected_files_set:
            try:
                titulo = pres.get('titulo_estudio', doc_name)
                ano = pres.get('marca')
                citation_header = f"{titulo} - {ano}" if ano else titulo

                doc_content = f"--- DOCUMENTO: {doc_name} ---\n"
                doc_content += f"Metadatos: {citation_header}\n"
                
                for grupo in pres.get("grupos", []):
                    contenido = str(grupo.get('contenido_texto', ''))
                    metadatos_slide = ""
                    if grupo.get('metadatos'):
                        metadatos_slide = f" (Contexto visual: {json.dumps(grupo.get('metadatos'), ensure_ascii=False)})"
                    
                    if contenido: 
                        doc_content += f" - {contenido}{metadatos_slide}\n"
                        
                doc_content += "\n\n"
                
                if len(all_text) + len(doc_content) > max_chars:
                    remaining = max_chars - len(all_text)
                    all_text += doc_content[:remaining]
                    break
                else:
                    all_text += doc_content

            except Exception as e: 
                print(f"Error procesando documento '{doc_name}': {e}")
    return all_text

# ==============================
# RAG: MODO PDF/TEXTO
# ==============================
def build_rag_context(query, documents, max_chars=100000):
    if not query or not documents: return ""
    
    query_terms = set(normalize_text(query).split())
    stopwords = get_stopwords()
    keywords = [w for w in query_terms if w not in stopwords and len(w) > 3]
    if not keywords: keywords = list(query_terms)

    scored_chunks = []
    for doc in documents:
        source = doc.get('source', 'Desconocido')
        content = doc.get('content', '')
        paragraphs = content.split('\n\n') 
        
        for i, para in enumerate(paragraphs):
            if len(para) < 30: continue
            para_norm = normalize_text(para)
            score = sum(1 for kw in keywords if kw in para_norm)
            if i == 0: score += 0.5 
            if score > 0:
                scored_chunks.append({'score': score, 'source': source, 'text': para})

    scored_chunks.sort(key=lambda x: x['score'], reverse=True)
    final_context = ""
    current_chars = 0
    if not scored_chunks: return "" 
    
    for chunk in scored_chunks:
        chunk_text = f"\n[Fuente: {chunk['source']}]\n{chunk['text']}\n..."
        if current_chars + len(chunk_text) > max_chars: break
        final_context += chunk_text
        current_chars += len(chunk_text)
    return final_context

# ==============================
# VALIDACIÓN DE SESIÓN
# ==============================
def validate_session_integrity():
    if not st.session_state.get("logged_in"): return
    current_time = time.time()
    if 'last_session_check' not in st.session_state or (current_time - st.session_state.last_session_check > 300):
        try:
            from services.supabase_db import supabase 
            uid = st.session_state.user_id
            res = supabase.table("users").select("active_session_id").eq("id", uid).single().execute()
            if res.data and res.data.get('active_session_id') != st.session_state.session_id:
                st.error("⚠️ Tu sesión ha sido cerrada desde otro dispositivo.")
                time.sleep(2)
                st.session_state.clear()
                st.rerun()
            st.session_state.last_session_check = current_time
        except Exception as e:
            print(f"Error validando sesión: {e}")

# =========================================================
# LÓGICA DE CITAS: TOOLTIPS MEJORADOS (TEXTO RICO)
# =========================================================
def process_text_with_tooltips(text):
    """
    Convierte [Fuente: Archivo; Contexto: "..."] en números [1] con tooltips CSS.
    El tooltip ahora es más ancho para acomodar el texto rico.
    """
    if not text: return ""

    # CSS mejorado: más ancho (400px) y mejor tipografía para lectura
    css_styles = """
<style>
.rag-citation {
    position: relative;
    display: inline-block;
    cursor: pointer;
    color: #0056b3;
    font-weight: bold;
    font-size: 0.8em;
    margin: 0 1px;
    vertical-align: super;
    line-height: 1;
}
.rag-citation .rag-tooltip-text {
    visibility: hidden;
    width: 400px; /* Ancho aumentado para leer párrafos */
    background-color: #262730; /* Color oscuro standard de Streamlit */
    color: #ffffff;
    text-align: left;
    border-radius: 8px;
    padding: 12px 16px;
    position: absolute;
    z-index: 99999;
    bottom: 140%;
    left: 50%;
    transform: translateX(-50%);
    opacity: 0;
    transition: opacity 0.2s;
    font-size: 0.9rem; /* Fuente un poco más grande */
    font-weight: normal;
    box-shadow: 0 6px 16px rgba(0,0,0,0.3);
    line-height: 1.5;
    pointer-events: none;
    white-space: normal; /* Permitir wrap del texto */
    border: 1px solid #444;
}
.rag-citation .rag-tooltip-text::after {
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    margin-left: -6px;
    border-width: 6px;
    border-style: solid;
    border-color: #262730 transparent transparent transparent;
}
.rag-citation:hover .rag-tooltip-text {
    visibility: visible;
    opacity: 1;
}
</style>
"""

    try:
        # Regex actualizada para capturar archivo Y contexto (incluso si tiene saltos de línea)
        pattern = r'\[(?:Fuente|Doc|Archivo):\s*(.*?)(?:;\s*Contexto:\s*"(.*?)")?\]'
        
        # Usamos re.DOTALL para que el punto capture saltos de línea si los hubiera
        matches = re.findall(pattern, text, flags=re.DOTALL)
        unique_sources = {}
        counter = 1
        
        for fname, fcontext in matches:
            fname = fname.strip()
            if fname not in unique_sources:
                unique_sources[fname] = counter
                counter += 1
        
        def replace_match(match):
            fname = match.group(1).strip()
            fcontext = match.group(2)
            
            citation_number = unique_sources.get(fname, "?")
            
            safe_fname = html.escape(fname)
            # Limpiamos el contexto para que se vea bien en HTML
            clean_ctx = fcontext.strip().replace('"', "'") if fcontext else "Ver documento original."
            safe_context = html.escape(clean_ctx)
            
            # HTML del tooltip
            tooltip_html = (
                f"<div style='margin-bottom:6px; font-weight:600; color:#bdc6ff;'>📄 {safe_fname}</div>"
                f"<div style='font-style:italic; color:#e0e0e0;'>“{safe_context}”</div>"
            )
            
            return f'''<span class="rag-citation">[{citation_number}]<span class="rag-tooltip-text">{tooltip_html}</span></span>'''
        
        enriched_text = re.sub(pattern, replace_match, text, flags=re.DOTALL)
        
        if unique_sources:
            footer = "\n\n<div style='font-size: 0.8em; color: #666; margin-top: 20px; border-top: 1px solid #eee; padding-top: 10px;'><strong>Referencias Consultadas:</strong><br>"
            sorted_sources = sorted(unique_sources.items(), key=lambda x: x[1])
            for name, num in sorted_sources:
                footer += f"<b>[{num}]</b> {html.escape(name)}<br>"
            footer += "</div>"
            enriched_text += footer

        return css_styles + enriched_text

    except Exception as e:
        print(f"Error renderizando tooltips: {e}")
        return text

# Funciones de Reset Workflow
def reset_report_workflow():
    for k in ["report", "last_question"]: st.session_state.mode_state.pop(k, None)

def reset_chat_workflow():
    st.session_state.mode_state.pop("chat_history", None)
    if "mode_state" in st.session_state and "chat_suggestions" in st.session_state.mode_state:
        del st.session_state.mode_state["chat_suggestions"]

def reset_transcript_chat_workflow():
    st.session_state.mode_state.pop("transcript_chat_history", None)

def reset_etnochat_chat_workflow():
    st.session_state.mode_state.pop("etno_chat_history", None)
