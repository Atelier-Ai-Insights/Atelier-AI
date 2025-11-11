import streamlit as st
import unicodedata
import json
import io
import fitz  # PyMuPDF
import nltk 

# ==============================
# Funciones de Reset (MODIFICADAS)
# ==============================

def reset_report_workflow():
    """Limpia el estado del modo REPORTE DENTRO de mode_state."""
    for k in ["report", "last_question"]:
        st.session_state.mode_state.pop(k, None) # <-- MODIFICADO

def reset_chat_workflow():
    """Limpia el estado del modo CHAT DENTRO de mode_state."""
    st.session_state.mode_state.pop("chat_history", None) # <-- MODIFICADO

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
