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
# LÓGICA DE CITAS: CORREGIDA PARA EVITAR SALTOS DE LÍNEA
# =========================================================
def process_text_with_tooltips(text):
    """
    Versión INLINE: Genera HTML 'aplanado' (sin saltos de línea internos)
    para que las citas no rompan el párrafo.
    """
    if not text: return ""

    try:
        # 1. Normalización: [1] [2] -> [1, 2]
        text = re.sub(r'(?<=\d)\]\s*\[(?=\d)', ', ', text)
        
        # 2. Separar Fuentes
        split_patterns = [r"\n\*\*Fuentes:?\*\*", r"\n## Fuentes", r"\n### Fuentes", r"\nFuentes:", r"\n\*\*Fuentes Verificadas:\*\*"]
        body = text
        sources_raw = ""
        
        for pattern in split_patterns:
            parts = re.split(pattern, text, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) > 1:
                body = parts[0]
                sources_raw = parts[1]
                break
        
        if not sources_raw: return body

        # 3. Mapear IDs
        source_map = {}
        # Regex mejorada para capturar líneas aunque no tengan ||| perfecto
        matches = re.findall(r"\[(\d+)\]\s*(.*?)(?:\s*\|\|\|\s*(.*))?$", sources_raw, re.MULTILINE)
        
        for num, filename, context in matches:
            clean_fname = filename.strip()
            clean_ctx = context.strip() if context else "Fuente del documento."
            source_map[num] = {
                "file": html.escape(clean_fname), 
                "context": html.escape(clean_ctx)
            }

        # 4. Reemplazo en el cuerpo (CONSTRUCCIÓN DE HTML PLANO)
        def replace_citation_group(match):
            content_inside = match.group(1)
            ids = [x.strip() for x in content_inside.split(',') if x.strip().isdigit()]
            
            html_parts = []
            for citation_num in ids:
                data = source_map.get(citation_num)
                
                if data:
                    # AQUÍ ESTABA EL ERROR: Usar f-string multilinea ('''...''') metía \n
                    # CORRECCIÓN: Todo en una sola línea de string
                    tooltip = (
                        f'<span class="tooltip-container">'
                        f'<span class="citation-number">[{citation_num}]</span>'
                        f'<span class="tooltip-text">'
                        f'<strong>📂 {data["file"]}</strong><br/>'
                        f'💬 {data["context"]}'
                        f'</span></span>'
                    )
                    html_parts.append(tooltip)
                else:
                    # Si no hay fuente, dejamos el texto plano
                    html_parts.append(f'<span class="citation-missing">[{citation_num}]</span>')
            
            if not html_parts: return match.group(0)
            return f" {' '.join(html_parts)} " # Unimos con espacio simple
        
        enriched_body = re.sub(r"\[([\d,\s]+)\]", replace_citation_group, body)
        
        # 5. Pie de página
        clean_footer = "\n\n<br><hr><h6>Fuentes Consultadas:</h6>"
        unique_files = set()
        for info in source_map.values():
            fname = info['file'].replace('"', '').replace("Documento:", "").strip()
            unique_files.add(fname)
            
        if unique_files:
            clean_footer += "<ul style='font-size: 0.8em; color: gray; margin-bottom: 0;'>"
            for fname in sorted(list(unique_files)):
                clean_footer += f"<li> {fname}</li>"
            clean_footer += "</ul>"
        else:
            clean_footer = ""

        return enriched_body + clean_footer

    except Exception as e:
        print(f"Error renderizando tooltips: {e}")
        return text

# Funciones de Reset Workflow (Las mantenemos igual)
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
