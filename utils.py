import streamlit as st
import re
import json
import unicodedata
from datetime import datetime

# ==============================================================================
# 1. FUNCIÓN DE RAG OPTIMIZADA (CACHEADA + TOPE DE TOKENS)
# ==============================================================================
@st.cache_data(show_spinner=False, ttl=3600)
def get_relevant_info(db, query, selected_files, max_chars=150000):
    """
    Busca y concatena la información de los archivos seleccionados.
    
    OPTIMIZACIONES CRÍTICAS:
    1. @st.cache_data: Memoriza el resultado por 1 hora.
    2. max_chars: Límite duro de caracteres para proteger la facturación.
    """
    if not db or not selected_files:
        return ""

    context_text = ""
    
    # 1. Filtrar documentos seleccionados
    relevant_docs = [doc for doc in db if doc.get("nombre_archivo") in selected_files]
    
    # 2. Concatenación de contenido
    for doc in relevant_docs:
        meta = f"\n\n--- INICIO DOCUMENTO: {doc.get('nombre_archivo')} ---\n"
        context_text += meta
        
        for grupo in doc.get("grupos", []):
            texto = str(grupo.get('contenido_texto', ''))
            context_text += texto + "\n"
            
            # --- FRENO DE EMERGENCIA DE COSTOS ---
            if len(context_text) > max_chars:
                context_text += f"\n\n[...Texto truncado automátiamente para optimizar costos (Límite: {max_chars} caracteres)...]"
                return context_text

    return context_text

# ==============================================================================
# 2. CONSTRUCCIÓN DE CONTEXTO PARA TENDENCIAS (WRAPPER)
# ==============================================================================
def build_rag_context(user_query, docs_list, max_chars=30000):
    """Auxiliar para Tendencias con límite estricto (30k chars)."""
    context = ""
    for item in docs_list:
        source = item.get('source', 'Fuente Desconocida')
        content = item.get('content', '')
        
        chunk = f"\n--- FUENTE EXTERNA/INTERNA: {source} ---\n{content}\n"
        context += chunk
        
        if len(context) > max_chars:
            return context[:max_chars] + "\n...(truncado por longitud)..."
            
    return context

# ==============================================================================
# 3. LIMPIEZA DE RESPUESTAS JSON (ANTI-ERRORES)
# ==============================================================================
def clean_gemini_json(raw_text):
    """Limpia el formato Markdown (```json ... ```) de Gemini."""
    if not raw_text: return "{}"
    
    cleaned = raw_text.strip()
    
    if "```" in cleaned:
        cleaned = re.sub(r"```json", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned)
    
    cleaned = cleaned.strip()

    start_obj = cleaned.find("{")
    start_arr = cleaned.find("[")
    
    if start_obj == -1 and start_arr == -1: return "{}"
    
    if start_obj != -1 and (start_arr == -1 or start_obj < start_arr):
        start_index = start_obj
        end_char = "}"
    else:
        start_index = start_arr
        end_char = "]"
        
    end_index = cleaned.rfind(end_char)
    
    if start_index != -1 and end_index != -1:
        cleaned = cleaned[start_index : end_index + 1]
            
    return cleaned

# ==============================================================================
# 4. UTILIDADES GENERALES DE LA APP
# ==============================================================================

def normalize_text(text):
    """
    Normaliza texto: minúsculas, sin acentos, sin espacios extra.
    Esta es la función que faltaba y causaba el ImportError.
    """
    if not text: return ""
    text = str(text).lower().strip()
    # Eliminar acentos (Normalize NFD y filtrar caracteres 'Mn' - Mark non-spacing)
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text

def extract_brand(filename):
    """Extrae la marca o proyecto del nombre del archivo."""
    if not filename: return "General"
    parts = filename.split('_')
    if len(parts) > 1:
        return parts[0].strip()
    return "General"

def validate_session_integrity():
    """Verifica la sesión de usuario."""
    if 'user' not in st.session_state or not st.session_state.user:
        st.session_state.clear()
        st.rerun()

def get_current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
