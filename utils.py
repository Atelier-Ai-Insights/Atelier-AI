import streamlit as st
import unicodedata
import json
import io
import fitz  # PyMuPDF
import nltk 
import time
from services.supabase_db import supabase

# ==============================
# Funciones de Reset
# ==============================

def reset_report_workflow():
    for k in ["report", "last_question"]:
        st.session_state.mode_state.pop(k, None) 

def reset_chat_workflow():
    st.session_state.mode_state.pop("chat_history", None) 

def reset_transcript_chat_workflow():
    st.session_state.mode_state.pop("transcript_chat_history", None)

def reset_etnochat_chat_workflow():
    st.session_state.mode_state.pop("etno_chat_history", None)

# ==============================
# FUNCIONES AUXILIARES
# ==============================
def normalize_text(text):
    if not text: return ""
    try: 
        normalized = unicodedata.normalize("NFD", str(text))
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()
    except Exception as e: 
        print(f"Error normalizing: {e}"); return str(text).lower()

def extract_brand(filename):
    if not filename or not isinstance(filename, str) or "In-ATL_" not in filename: return ""
    try: 
        base_filename = filename.replace("\\", "/").split("/")[-1]
        return base_filename.split("In-ATL_")[1].rsplit(".", 1)[0] if "In-ATL_" in base_filename else ""
    except Exception as e: 
        print(f"Error extract brand: {e}"); return ""

def clean_text(text):
    if not isinstance(text, str): text = str(text)
    return text

@st.cache_resource
def get_stopwords():
    try:
        nltk.download('stopwords')
    except Exception as e:
        print(f"Error descargando stopwords de NLTK: {e}")
    
    try: spanish_stopwords = nltk.corpus.stopwords.words('spanish')
    except: spanish_stopwords = ['de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta']
    
    try: english_stopwords = nltk.corpus.stopwords.words('english')
    except: english_stopwords = ['the', 'and', 'to', 'of', 'a', 'in', 'is', 'that', 'for', 'it', 'as', 'was', 'with', 'on', 'at', 'by', 'be', 'this', 'which', 'have', 'from', 'or', 'one', 'had', 'by', 'word', 'but', 'not', 'what', 'all', 'were', 'we', 'when', 'your', 'can', 'said', 'there', 'use', 'an', 'each', 'which', 'she', 'do', 'how', 'their', 'if', 'will', 'up', 'other', 'about', 'out', 'many', 'then', 'them', 'these', 'so', 'some', 'her', 'would', 'make', 'like', 'him', 'into', 'time', 'has', 'look', 'two', 'more', 'write', 'go', 'see', 'number', 'no', 'way', 'could', 'people', 'my', 'than', 'first', 'water', 'been', 'call', 'who', 'oil', 'its', 'now', 'find']

    custom_list = [
        '...', 'p', 'r', 'rta', 'respuesta', 'respuestas', 'si', 'no', 'na', 'ninguno', 'ninguna', 'nan',
        'document', 'presentation', 'python', 'warning', 'created', 'page',
        'objetivo', 'tecnica', 'investigacion', 'investigación', 'participante', 'participantes',
        'sesiones', 'sesión', 'proyecto', 'análisis', 'analisis', 'ficha', 'tecnica', 'slide',
        'bogotá', 'colombia', 'atelier', 'insights', 'cliente', 'consumidor', 'consumidores',
        'evaluación', 'evaluacion', 'entrevistado', 'entrevistados', 'pregunta', 'focus', 'group',
        'hola', 'buenos', 'dias', 'noches', 'tarde', 'nombre', 'llamo', 'presentación', 'presentacion'
    ]
    
    final_stopwords = set(spanish_stopwords) | set(english_stopwords) | set(custom_list)
    return final_stopwords

# ==============================
# RAG (Recuperación de Información S3)
# ==============================
def get_relevant_info(db, question, selected_files):
    all_text = ""
    selected_files_set = set(selected_files) if isinstance(selected_files, (list, set)) else set()
    
    for pres in db:
        doc_name = pres.get('nombre_archivo')
        if doc_name and doc_name in selected_files_set:
            try:
                titulo = pres.get('titulo_estudio', doc_name)
                ano = pres.get('marca')
                citation_header = f"{titulo} - {ano}" if ano else titulo

                all_text += f"Documento: {citation_header}\n"
                
                for grupo in pres.get("grupos", []):
                    contenido = str(grupo.get('contenido_texto', ''))
                    metadatos = json.dumps(grupo.get('metadatos', {}), ensure_ascii=False) if grupo.get('metadatos') else ""
                    hechos = json.dumps(grupo.get('hechos', []), ensure_ascii=False) if grupo.get('hechos') else ""
                    
                    if contenido: all_text += f"  - {contenido}\n";
                    if metadatos: all_text += f"  (Contexto adicional: {metadatos})\n"
                    if hechos: all_text += f"  (Datos clave: {hechos})\n"
                        
                all_text += "\n---\n\n"
            except Exception as e: 
                print(f"Error proc doc '{doc_name}': {e}")
    return all_text

def extract_text_from_pdfs(uploaded_files):
    combined_text = ""
    if not uploaded_files: return combined_text
    for file in uploaded_files:
        try:
            file_bytes = file.getvalue()
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            combined_text += f"\n\n--- INICIO DOCUMENTO: {file.name} ---\n\n"
            for page in pdf_document: combined_text += page.get_text() + "\n"
            pdf_document.close()
            combined_text += f"\n--- FIN DOCUMENTO: {file.name} ---\n"
        except Exception as e:
            print(f"Error al procesar PDF '{file.name}': {e}")
            combined_text += f"\n\n--- ERROR AL PROCESAR: {file.name} ---\n"
    return combined_text

# ==============================
# GESTIÓN DE SESIÓN
# ==============================

def validate_session_integrity():
    if not st.session_state.get("logged_in"): return
    if 'user_id' not in st.session_state or 'session_id' not in st.session_state:
        st.warning("Datos de sesión corruptos. Reiniciando..."); st.session_state.clear(); st.rerun()

    try:
        response = supabase.table("users").select("active_session_id").eq("id", st.session_state.user_id).single().execute()
        if response.data:
            db_session_id = response.data.get('active_session_id')
            if db_session_id != st.session_state.session_id:
                st.error("⚠️ Tu sesión ha sido cerrada porque se detectó un inicio de sesión en otro dispositivo.")
                time.sleep(2)
                supabase.auth.sign_out(); st.session_state.clear(); st.rerun()
        else:
            st.session_state.clear(); st.rerun()
    except Exception as e:
        print(f"Error validando sesión (Heartbeat): {e}")

# ==============================
# RAG LIGERO (Búsqueda Inteligente)
# ==============================

def build_rag_context(query, documents, max_chars=100000):
    """
    Filtra y construye un contexto relevante basado en la pregunta del usuario.
    """
    if not query or not documents: return ""

    query_terms = set(normalize_text(query).split())
    stopwords = get_stopwords()
    keywords = [w for w in query_terms if w not in stopwords and len(w) > 3]
    
    if not keywords: keywords = query_terms 

    scored_chunks = []

    # Fragmentar y Puntuar
    for doc in documents:
        source = doc.get('source', 'Desconocido')
        content = doc.get('content', '')
        paragraphs = content.split('\n\n') # Dividir por párrafos
        
        for i, para in enumerate(paragraphs):
            if len(para) < 50: continue 
            
            para_norm = normalize_text(para)
            score = sum(1 for kw in keywords if kw in para_norm)
            if i == 0: score += 0.5 # Bonus al intro (pero el RAG prefiere keywords)
            
            if score > 0:
                scored_chunks.append({'score': score, 'source': source, 'text': para})

    scored_chunks.sort(key=lambda x: x['score'], reverse=True)

    final_context = ""
    current_chars = 0
    
    # CAMBIO IMPORTANTE: Si no hay coincidencias, devolvemos vacío para que el sistema
    # use el Resumen Global (definido en text_analysis_mode.py)
    if not scored_chunks:
        print("RAG: No se encontraron coincidencias exactas. Usando fallback (vacío).")
        return "" 

    docs_included = set()
    for chunk in scored_chunks:
        if current_chars + len(chunk['text']) > max_chars: break
        final_context += f"\n[Fuente: {chunk['source']}]\n{chunk['text']}\n..."
        current_chars += len(chunk['text'])
        docs_included.add(chunk['source'])

    print(f"RAG: Contexto construido con {current_chars} chars de {len(docs_included)} documentos.")
    return final_context

# ... (código existente) ...

# ==============================
# UTILIDADES DE LIMPIEZA DE IA
# ==============================

def clean_gemini_json(text):
    """
    Limpia la respuesta de Gemini para asegurar que sea un JSON válido.
    Elimina bloques de código Markdown (```json ... ```) y espacios extra.
    """
    if not text: return ""
    text = str(text).strip()
    
    # Eliminar bloque de inicio tipo Markdown
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
        
    # Eliminar bloque de fin tipo Markdown
    if text.endswith("```"):
        text = text[:-3]
        
    return text.strip()
