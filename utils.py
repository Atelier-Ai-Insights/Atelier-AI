import streamlit as st
import re
import json
from datetime import datetime

# ==============================================================================
# 1. FUNCIÓN DE RAG OPTIMIZADA (CACHEADA + TOPE DE TOKENS)
# ==============================================================================
@st.cache_data(show_spinner=False, ttl=3600)
def get_relevant_info(db, query, selected_files, max_chars=150000):
    """
    Busca y concatena la información de los archivos seleccionados.
    
    OPTIMIZACIONES CRÍTICAS:
    1. @st.cache_data: Memoriza el resultado por 1 hora. Si el usuario no cambia 
       la selección, no se recalcula nada.
    2. max_chars: Límite duro de caracteres. Esto previene que envíes 
       contextos de 1 millón de tokens por error, protegiendo la facturación.
    """
    if not db or not selected_files:
        return ""

    context_text = ""
    
    # 1. Filtrar solo los documentos que el usuario seleccionó en el sidebar
    # Esto evita procesar toda la base de datos innecesariamente.
    relevant_docs = [doc for doc in db if doc.get("nombre_archivo") in selected_files]
    
    # 2. Concatenación de contenido
    for doc in relevant_docs:
        # Añadimos un encabezado para que la IA sepa de qué archivo viene el texto
        meta = f"\n\n--- INICIO DOCUMENTO: {doc.get('nombre_archivo')} ---\n"
        context_text += meta
        
        # Extraer contenido de los grupos (chunks) almacenados en Supabase/JSON
        for grupo in doc.get("grupos", []):
            texto = str(grupo.get('contenido_texto', ''))
            
            # (Opcional) Filtro simple: Si la query no está vacía, podríamos filtrar párrafos.
            # Por ahora concatenamos todo el documento seleccionado para dar contexto completo.
            context_text += texto + "\n"
            
            # --- FRENO DE EMERGENCIA DE COSTOS ---
            # Si el texto acumulado supera el límite, paramos de leer.
            if len(context_text) > max_chars:
                context_text += f"\n\n[...Texto truncado automátiamente para optimizar costos (Límite: {max_chars} caracteres)...]"
                return context_text

    return context_text

# ==============================================================================
# 2. CONSTRUCCIÓN DE CONTEXTO PARA TENDENCIAS (WRAPPER)
# ==============================================================================
def build_rag_context(user_query, docs_list, max_chars=30000):
    """
    Función auxiliar específica para el modo de Tendencias, que a veces maneja
    listas de diccionarios diferentes (PDFs externos + Repo).
    Mantiene un límite más estricto (30k chars) para agilidad.
    """
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
    """
    Limpia el formato Markdown (```json ... ```) que Gemini suele añadir.
    Es robusto para detectar tanto objetos {} como listas [].
    """
    if not raw_text: return "{}"
    
    cleaned = raw_text.strip()
    
    # 1. Eliminar bloques de código Markdown
    if "```" in cleaned:
        cleaned = re.sub(r"```json", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned)
    
    cleaned = cleaned.strip()

    # 2. Buscar el inicio y fin real del JSON
    start_obj = cleaned.find("{")
    start_arr = cleaned.find("[")
    
    # Si no hay ni { ni [, no es JSON válido
    if start_obj == -1 and start_arr == -1: 
        return "{}"
    
    # Determinar si empieza con { o [
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

def extract_brand(filename):
    """
    Extrae la marca o proyecto del nombre del archivo.
    Asume formato 'MARCA_NombreArchivo.pdf' o simplemente devuelve el nombre.
    """
    if not filename: return "General"
    
    # Intenta dividir por guion bajo
    parts = filename.split('_')
    if len(parts) > 1:
        # Devuelve la primera parte como marca (ej: 'BOCATTO' de 'BOCATTO_Estudio.pdf')
        return parts[0].strip()
    
    # Si no tiene guion bajo, devuelve una categoría general o el nombre truncado
    return "General"

def validate_session_integrity():
    """
    Verifica que la sesión de Streamlit tenga un usuario activo.
    Si se pierde la sesión, fuerza un recargo.
    """
    if 'user' not in st.session_state or not st.session_state.user:
        st.session_state.clear()
        st.rerun()

def get_current_time_str():
    """Devuelve la hora actual formateada."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
