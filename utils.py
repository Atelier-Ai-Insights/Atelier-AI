import streamlit as st
import re
import json
import unicodedata
from datetime import datetime
import fitz  # PyMuPDF (Requerido para extract_text_from_pdfs)

# ==============================================================================
# 1. FUNCIÓN DE RAG OPTIMIZADA (CACHEADA + TOPE DE TOKENS)
# ==============================================================================
@st.cache_data(show_spinner=False, ttl=3600)
def get_relevant_info(db, query, selected_files, max_chars=150000):
    """
    Busca y concatena la información de los archivos seleccionados.
    """
    if not db or not selected_files:
        return ""

    context_text = ""
    relevant_docs = [doc for doc in db if doc.get("nombre_archivo") in selected_files]
    
    for doc in relevant_docs:
        meta = f"\n\n--- INICIO DOCUMENTO: {doc.get('nombre_archivo')} ---\n"
        context_text += meta
        
        for grupo in doc.get("grupos", []):
            texto = str(grupo.get('contenido_texto', ''))
            context_text += texto + "\n"
            
            if len(context_text) > max_chars:
                context_text += f"\n\n[...Texto truncado automáticamente (Límite: {max_chars})...]"
                return context_text

    return context_text

# ==============================================================================
# 2. PROCESAMIENTO DE ARCHIVOS Y CONTEXTO
# ==============================================================================
def build_rag_context(user_query, docs_list, max_chars=30000):
    """Auxiliar para Tendencias con límite estricto."""
    context = ""
    for item in docs_list:
        source = item.get('source', 'Fuente Desconocida')
        content = item.get('content', '')
        chunk = f"\n--- FUENTE: {source} ---\n{content}\n"
        context += chunk
        if len(context) > max_chars:
            return context[:max_chars] + "\n...(truncado)..."
    return context

def extract_text_from_pdfs(uploaded_files):
    """
    Extrae texto de PDFs subidos en memoria.
    Requerido por: modes/onepager_mode.py
    """
    text_content = ""
    for uploaded_file in uploaded_files:
        try:
            with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
                for page in doc:
                    text_content += page.get_text() + "\n"
        except Exception as e:
            print(f"Error leyendo PDF {uploaded_file.name}: {e}")
    return text_content

# ==============================================================================
# 3. LIMPIEZA Y UTILIDADES DE TEXTO
# ==============================================================================
def clean_gemini_json(raw_text):
    """Limpia el formato Markdown (```json ... ```) de Gemini."""
    if not raw_text: return "{}"
    cleaned = raw_text.strip()
    if "```" in cleaned:
        cleaned = re.sub(r"```json", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned)
    cleaned = cleaned.strip()
    
    start_obj, start_arr = cleaned.find("{"), cleaned.find("[")
    if start_obj == -1 and start_arr == -1: return "{}"
    
    if start_obj != -1 and (start_arr == -1 or start_obj < start_arr):
        start, end_char = start_obj, "}"
    else:
        start, end_char = start_arr, "]"
        
    end = cleaned.rfind(end_char)
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    return cleaned

def normalize_text(text):
    """
    Normaliza texto: minúsculas, sin acentos.
    Requerido por: services/storage.py
    """
    if not text: return ""
    text = str(text).lower().strip()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text

def extract_brand(filename):
    """Extrae la marca del nombre del archivo."""
    if not filename: return "General"
    parts = filename.split('_')
    return parts[0].strip() if len(parts) > 1 else "General"

# ==============================================================================
# 4. GESTIÓN DE SESIÓN Y TIEMPO
# ==============================================================================
def validate_session_integrity():
    if 'user' not in st.session_state or not st.session_state.user:
        st.session_state.clear()
        st.rerun()

def get_current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ==============================================================================
# 5. WORKFLOWS DE LIMPIEZA (RESETS) - TODAS LAS VARIANTES
# ==============================================================================

def reset_report_workflow():
    """Requerido por: modes/report_mode.py"""
    keys = ["report_result", "report_query"]
    if "mode_state" in st.session_state:
        for k in keys: st.session_state.mode_state.pop(k, None)

def reset_chat_workflow():
    """Requerido por: modes/chat_mode.py"""
    if "chat_history" in st.session_state:
        st.session_state.chat_history = []
    if "mode_state" in st.session_state and "chat_history" in st.session_state.mode_state:
        st.session_state.mode_state["chat_history"] = []

def reset_transcript_chat_workflow():
    """Requerido por: modes/text_analysis_mode.py"""
    if "mode_state" in st.session_state:
        st.session_state.mode_state.pop("transcript_chat_history", None)
        st.session_state.mode_state.pop("transcript_analysis_done", None)
        
