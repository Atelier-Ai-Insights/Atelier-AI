import streamlit as st
import unicodedata
import json
import io
import fitz  # PyMuPDF
import nltk # <-- ¡NUEVA IMPORTACIÓN!

# ==============================
# Funciones de Reset
# ==============================
def reset_report_workflow():
    for k in ["report", "last_question", "report_question", "personalization", "rating"]:
        st.session_state.pop(k, None)

def reset_chat_workflow():
    st.session_state.pop("chat_history", None)

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

# --- ¡INICIO DE NUEVA FUNCIÓN MOVILIZADA! ---
@st.cache_resource
def get_stopwords():
    """Descarga y cachea las stopwords en español de NLTK."""
    try:
        nltk.download('stopwords')
    except Exception as e:
        print(f"Error descargando stopwords de NLTK (se usarán las básicas): {e}")
    
    try:
        spanish_stopwords = nltk.corpus.stopwords.words('spanish')
    except:
        # Lista fallback por si NLTK falla
        spanish_stopwords = ['de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta']
    
    # Añade palabras comunes de encuestas que no aportan valor
    custom_list = ['...', 'p', 'r', 'rta', 'respuesta', 'si', 'no', 'na', 'ninguno', 'ninguna', 'nan']
    spanish_stopwords.extend(custom_list)
    return set(spanish_stopwords)
# --- ¡FIN DE NUEVA FUNCIÓN MOVILIZADA! ---


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