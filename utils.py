import streamlit as st
import unicodedata
import json
import re
import fitz  # PyMuPDF
import time

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
    if not text: return ""
    text = str(text).strip()
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    return text.strip()

# ==============================
# PROCESAMIENTO DE PDFS (ONE PAGER)
# ==============================
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
# RAG: RECUPERACIÓN DE INFORMACIÓN (Segura)
# ==============================
def get_relevant_info(db, question, selected_files, max_chars=150000):
    all_text = ""
    selected_files_set = set(selected_files) if isinstance(selected_files, (list, set)) else set()
    
    for pres in db:
        if len(all_text) > max_chars:
            all_text += f"\n\n[ALERTA: Contexto truncado por límite de seguridad ({max_chars} chars)...]"
            break 

        doc_name = pres.get('nombre_archivo')
        if doc_name and doc_name in selected_files_set:
            try:
                titulo = pres.get('titulo_estudio', doc_name)
                ano = pres.get('marca')
                citation_header = f"{titulo} - {ano}" if ano else titulo

                doc_content = f"Documento: {citation_header}\n"
                
                for grupo in pres.get("grupos", []):
                    contenido = str(grupo.get('contenido_texto', ''))
                    metadatos = json.dumps(grupo.get('metadatos', {}), ensure_ascii=False) if grupo.get('metadatos') else ""
                    
                    if contenido: doc_content += f"  - {contenido}\n";
                    if metadatos: doc_content += f"  (Contexto: {metadatos})\n"
                        
                doc_content += "\n---\n\n"
                
                if len(all_text) + len(doc_content) > max_chars:
                    remaining = max_chars - len(all_text)
                    all_text += doc_content[:remaining]
                    break
                else:
                    all_text += doc_content

            except Exception as e: 
                print(f"Error proc doc '{doc_name}': {e}")

    print(f"🔥 DEBUG TAMAÑO: Enviando contexto de {len(all_text)} caracteres a la IA.")
    return all_text

def build_rag_context(query, documents, max_chars=100000):
    """
    Filtra y construye un contexto relevante para Text Analysis.
    """
    if not query or not documents: return ""

    query_terms = set(normalize_text(query).split())
    stopwords = get_stopwords()
    keywords = [w for w in query_terms if w not in stopwords and len(w) > 3]
    if not keywords: keywords = query_terms 

    scored_chunks = []

    for doc in documents:
        source = doc.get('source', 'Desconocido')
        content = doc.get('content', '')
        paragraphs = content.split('\n\n') 
        
        for i, para in enumerate(paragraphs):
            if len(para) < 50: continue 
            
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
        if current_chars + len(chunk['text']) > max_chars: break
        final_context += f"\n[Fuente: {chunk['source']}]\n{chunk['text']}\n..."
        current_chars += len(chunk['text'])

    return final_context

# ==============================
# RESET WORKFLOWS
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
            print(f"Warning session check: {e}")
            pass
