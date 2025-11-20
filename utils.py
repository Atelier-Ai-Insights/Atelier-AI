import streamlit as st
import unicodedata
import json
import io
import fitz
import nltk
import time
from services.supabase_db import supabase

# ==============================
# Funciones de Reset (MODIFICADAS)
# ==============================

def reset_report_workflow():
    """Limpia el estado del modo REPORTE DENTRO de mode_state."""
    for k in ["report", "last_question"]:
        st.session_state.mode_state.pop(k, None) 

def reset_chat_workflow():
    """Limpia el estado del modo CHAT DENTRO de mode_state."""
    st.session_state.mode_state.pop("chat_history", None) 

def reset_transcript_chat_workflow():
    """Limpia el historial del chat de transcripciones DENTRO de mode_state."""
    st.session_state.mode_state.pop("transcript_chat_history", None)

def reset_etnochat_chat_workflow():
    """Limpia el historial del chat de EtnoChat DENTRO de mode_state."""
    st.session_state.mode_state.pop("etno_chat_history", None)

# ==============================
# FUNCIONES AUXILIARES (Sin cambios)
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
    """Descarga y cachea las stopwords en español Y EN INGLÉS de NLTK."""
    try:
        nltk.download('stopwords')
    except Exception as e:
        print(f"Error descargando stopwords de NLTK (se usarán las básicas): {e}")
    
    # Cargar stopwords en español
    try:
        spanish_stopwords = nltk.corpus.stopwords.words('spanish')
    except:
        spanish_stopwords = ['de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta']
    
    # Cargar stopwords en inglés
    try:
        english_stopwords = nltk.corpus.stopwords.words('english')
    except:
        english_stopwords = ['i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now']

    # Lista de ruido meta (de tu captura de pantalla)
    custom_list = [
        '...', 'p', 'r', 'rta', 'respuesta', 'respuestas', 'si', 'no', 'na', 'ninguno', 'ninguna', 'nan',
        'document', 'presentation', 'python', 'warning', 'created', 'page',
        'objetivo', 'tecnica', 'investigacion', 'investigación', 'participante', 'participantes',
        'sesiones', 'sesión', 'proyecto', 'análisis', 'analisis', 'ficha', 'tecnica', 'slide',
        'bogotá', 'colombia', 'atelier', 'insights', 'cliente', 'consumidor', 'consumidores',
        'evaluación', 'evaluacion', 'entrevistado', 'entrevistados', 'pregunta', 'focus', 'group'
    ]
    
    # Combinar todas las listas
    final_stopwords = set(spanish_stopwords) | set(english_stopwords) | set(custom_list)
    return final_stopwords

# ==============================
# FUNCIÓN RAG (Recuperación de Información S3)
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
                    
                    if contenido:
                        all_text += f"  - {contenido}\n";
                    
                    if metadatos: 
                        all_text += f"  (Contexto adicional: {metadatos})\n"
                    if hechos: 
                        all_text += f"  (Datos clave: {hechos})\n"
                        
                all_text += "\n---\n\n"
            except Exception as e: 
                print(f"Error proc doc '{doc_name}': {e}")
                
    return all_text

# ==============================
# FUNCIÓN (Extracción de PDF)
# ==============================
def extract_text_from_pdfs(uploaded_files):
    """
    Recibe una lista de archivos UploadedFile de Streamlit y devuelve
    todo el texto extraído, separado por nombre de archivo.
    """
    combined_text = ""
    if not uploaded_files:
        return combined_text

    for file in uploaded_files:
        try:
            file_bytes = file.getvalue()
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            combined_text += f"\n\n--- INICIO DOCUMENTO: {file.name} ---\n\n"
            
            for page in pdf_document:
                combined_text += page.get_text() + "\n"
                
            pdf_document.close()
            combined_text += f"\n--- FIN DOCUMENTO: {file.name} ---\n"
            
        except Exception as e:
            print(f"Error al procesar PDF '{file.name}': {e}")
            combined_text += f"\n\n--- ERROR AL PROCESAR: {file.name} ---\n"
            
    return combined_text

# ==============================
# GESTIÓN DE SESIÓN (NUEVO)
# ==============================

def validate_session_integrity():
    """
    Verifica si la sesión actual del navegador coincide con la sesión activa en la base de datos.
    Si no coinciden (ej. se inició sesión en otro lado), cierra la sesión local.
    """
    # Si no está logueado, no hay nada que validar
    if not st.session_state.get("logged_in"):
        return

    # Si faltan datos críticos, limpiar y salir
    if 'user_id' not in st.session_state or 'session_id' not in st.session_state:
        st.warning("Datos de sesión corruptos. Reiniciando...")
        st.session_state.clear()
        st.rerun()

    try:
        # Consultar solo el campo active_session_id para ser eficiente
        response = supabase.table("users").select("active_session_id").eq("id", st.session_state.user_id).single().execute()
        
        if response.data:
            db_session_id = response.data.get('active_session_id')
            
            # CASO DE CONFLICTO: El ID en DB es diferente al del navegador
            if db_session_id != st.session_state.session_id:
                st.error("⚠️ Tu sesión ha sido cerrada porque se detectó un inicio de sesión en otro dispositivo.")
                time.sleep(2) # Dar tiempo al usuario para leer
                
                # Cerrar sesión limpiamente
                supabase.auth.sign_out()
                st.session_state.clear()
                st.rerun()
        else:
            # El usuario no existe en la tabla users (caso raro)
            st.session_state.clear()
            st.rerun()

    except Exception as e:
        # Si falla la conexión (ej. internet intermitente), no expulsamos inmediatamente al usuario
        # pero registramos el error en consola.
        print(f"Error validando sesión (Heartbeat): {e}")

# ==============================
# RAG LIGERO (Búsqueda Inteligente de Texto)
# ==============================

def build_rag_context(query, documents, max_chars=100000):
    """
    Filtra y construye un contexto relevante basado en la pregunta del usuario.
    
    Args:
        query (str): La pregunta del usuario.
        documents (list): Lista de dicts {'source': nombre, 'content': texto}.
        max_chars (int): Límite aproximado de caracteres para enviar a la IA.
    
    Returns:
        str: Contexto formateado con solo las partes relevantes.
    """
    if not query or not documents:
        return ""

    # 1. Normalizar query para búsqueda (minusculas, sin tildes básicas)
    query_terms = set(normalize_text(query).split())
    # Eliminamos stopwords para mejorar la búsqueda
    stopwords = get_stopwords()
    keywords = [w for w in query_terms if w not in stopwords and len(w) > 3]
    
    if not keywords: # Si la query es muy corta o genérica, devolvemos un contexto truncado general
        keywords = query_terms 

    scored_chunks = []

    # 2. Fragmentar y Puntuar (Chunking & Scoring)
    for doc in documents:
        source = doc.get('source', 'Desconocido')
        content = doc.get('content', '')
        
        # Dividir en párrafos o bloques de ~1000 caracteres
        # Usamos saltos de línea dobles como separador natural de párrafos
        paragraphs = content.split('\n\n')
        
        for i, para in enumerate(paragraphs):
            if len(para) < 50: continue # Ignorar párrafos muy cortos/ruido
            
            # Puntuar el párrafo según coincidencia de keywords
            para_norm = normalize_text(para)
            score = sum(1 for kw in keywords if kw in para_norm)
            
            # Bonus: Si es el inicio del documento, darle un poco de peso (contexto general)
            if i == 0: score += 0.5
            
            if score > 0:
                scored_chunks.append({
                    'score': score,
                    'source': source,
                    'text': para
                })

    # 3. Ordenar por relevancia (Score más alto primero)
    scored_chunks.sort(key=lambda x: x['score'], reverse=True)

    # 4. Construir el contexto final hasta llenar el presupuesto (max_chars)
    final_context = ""
    current_chars = 0
    
    # Si no encontramos coincidencias (score 0), usamos el inicio de los docs como fallback
    if not scored_chunks:
        print("RAG: No se encontraron coincidencias exactas. Usando inicio de documentos.")
        for doc in documents[:5]: # Tomar primeros 5 docs
            snippet = doc['content'][:2000] # Primeros 2k caracteres de cada uno
            final_context += f"\nDocumento: {doc['source']}\n{snippet}\n...\n"
        return final_context

    # Si hay coincidencias, armamos el puzzle
    docs_included = set()
    for chunk in scored_chunks:
        if current_chars + len(chunk['text']) > max_chars:
            break
        
        citation = f"\n[Fuente: {chunk['source']}]"
        final_context += f"{citation}\n{chunk['text']}\n..."
        current_chars += len(chunk['text'])
        docs_included.add(chunk['source'])

    print(f"RAG: Contexto construido con {current_chars} chars de {len(docs_included)} documentos.")
    return final_context
