import streamlit as st
import unicodedata
import json
import fitz  # PyMuPDF
import re

# ==============================
# GESTIÓN DE STOPWORDS (OPTIMIZADA)
# ==============================
# Eliminamos la dependencia de NLTK download para mayor velocidad y estabilidad
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
    if not filename or "In-ATL_" not in str(filename): return ""
    try: 
        base = str(filename).replace("\\", "/").split("/")[-1]
        if "In-ATL_" in base: return base.split("In-ATL_")[1].rsplit(".", 1)[0]
    except: pass
    return ""

def clean_text(text):
    return str(text) if text is not None else ""

def clean_gemini_json(text):
    """Limpia respuestas JSON de Gemini eliminando bloques Markdown."""
    if not text: return ""
    text = str(text).strip()
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    return text.strip()

# ==============================
# RAG (Recuperación de Información)
# ==============================
def get_relevant_info(db, question, selected_files):
    if not db or not question: return ""
    
    selected_set = set(selected_files) if selected_files else set()
    question_norm = normalize_text(question)
    keywords = [w for w in question_norm.split() if w not in get_stopwords() and len(w) > 3]
    
    relevant_chunks = []
    
    for pres in db:
        doc_name = pres.get('nombre_archivo')
        if doc_name and (not selected_set or doc_name in selected_set):
            score = 0
            matches = []
            
            # Búsqueda simple por palabras clave
            for grupo in pres.get("grupos", []):
                txt = str(grupo.get('contenido_texto', ''))
                txt_norm = normalize_text(txt)
                if any(kw in txt_norm for kw in keywords):
                    matches.append(f"- {txt}")
                    score += 1
            
            if score > 0:
                header = f"Documento: {pres.get('titulo_estudio', doc_name)} ({pres.get('marca', '')})"
                full_block = f"{header}\n" + "\n".join(matches)
                relevant_chunks.append((score, full_block))

    # Ordenar por relevancia y limitar contexto (Top 15 fragmentos)
    relevant_chunks.sort(key=lambda x: x[0], reverse=True)
    final_text = "\n\n".join([chunk[1] for chunk in relevant_chunks[:15]])
    
    return final_text if final_text else "No se encontró información específica en los documentos seleccionados."

def extract_text_from_pdfs(uploaded_files):
    text = ""
    if not uploaded_files: return text
    for file in uploaded_files:
        try:
            with fitz.open(stream=file.getvalue(), filetype="pdf") as doc:
                text += f"\n--- INICIO PDF: {file.name} ---\n"
                for page in doc: text += page.get_text()
                text += f"\n--- FIN PDF: {file.name} ---\n"
        except Exception as e: print(f"Error PDF {file.name}: {e}")
    return text

# ==============================
# GESTIÓN DE ESTADO (RESET)
# ==============================
def reset_report_workflow():
    for k in ["report", "last_question"]: st.session_state.mode_state.pop(k, None)

def reset_chat_workflow():
    st.session_state.mode_state.pop("chat_history", None)

def reset_transcript_chat_workflow():
    st.session_state.mode_state.pop("transcript_chat_history", None)

def reset_etnochat_chat_workflow():
    st.session_state.mode_state.pop("etno_chat_history", None)

# ==============================
# VALIDACIÓN DE SESIÓN
# ==============================
from services.supabase_db import supabase
import time

def validate_session_integrity():
    if not st.session_state.get("logged_in"): return
    # Validación optimizada: Solo verificar cada 5 minutos, no en cada click
    current_time = time.time()
    if 'last_session_check' not in st.session_state or (current_time - st.session_state.last_session_check > 300):
        try:
            uid = st.session_state.user_id
            res = supabase.table("users").select("active_session_id").eq("id", uid).single().execute()
            if res.data and res.data.get('active_session_id') != st.session_state.session_id:
                st.error("⚠️ Tu sesión ha sido cerrada desde otro dispositivo.")
                time.sleep(2); st.session_state.clear(); st.rerun()
            st.session_state.last_session_check = current_time
        except: pass
