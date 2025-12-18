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
def get_relevant_info(db, question, selected_files, max_chars=150000):
    """
    Recupera info, pero con un LÍMITE DE SEGURIDAD (max_chars).
    150k caracteres son aprox 30k-40k tokens (Seguro para Gemini Flash/Pro).
    """
    all_text = ""
    selected_files_set = set(selected_files) if isinstance(selected_files, (list, set)) else set()
    
    # Prioridad: ¿Podemos ordenar por relevancia? 
    # Por ahora, simplemente cortamos para no quebrar la banca.
    
    for pres in db:
        # Si ya nos pasamos del límite, paramos de leer archivos.
        if len(all_text) > max_chars:
            all_text += f"\n\n[ALERTA: Contexto truncado por límite de seguridad ({max_chars} chars)...]"
            break 

        doc_name = pres.get('nombre_archivo')
        if doc_name and doc_name in selected_files_set:
            try:
                # Construcción del texto (igual que antes)
                titulo = pres.get('titulo_estudio', doc_name)
                ano = pres.get('marca')
                citation_header = f"{titulo} - {ano}" if ano else titulo

                doc_content = f"Documento: {citation_header}\n"
                
                for grupo in pres.get("grupos", []):
                    contenido = str(grupo.get('contenido_texto', ''))
                    # Solo agregamos metadatos si son breves
                    metadatos = json.dumps(grupo.get('metadatos', {}), ensure_ascii=False) if grupo.get('metadatos') else ""
                    
                    if contenido: doc_content += f"  - {contenido}\n";
                    if metadatos: doc_content += f"  (Contexto: {metadatos})\n"
                        
                doc_content += "\n---\n\n"
                
                # Chequeo antes de agregar para no cortar a mitad de palabra si es posible
                if len(all_text) + len(doc_content) > max_chars:
                    remaining = max_chars - len(all_text)
                    all_text += doc_content[:remaining]
                    break
                else:
                    all_text += doc_content

            except Exception as e: 
                print(f"Error proc doc '{doc_name}': {e}")
                
    return all_text

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
