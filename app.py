# ==============================================================================
# 1. IMPORTACIONES
# ==============================================================================
# Librerías existentes
import datetime
import html
import json
import unicodedata
from io import BytesIO
import os
import tempfile
from bs4 import BeautifulSoup
import boto3
import google.generativeai as genai
import markdown2
import streamlit as st
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from supabase import create_client
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# --- INICIO: NUEVAS LIBRERÍAS PARA EL CHAT RAG ---
# Asegúrate de instalar estas librerías:
# pip install langchain langchain-google-genai langchain_community chromadb
from langchain.docstore.document import Document
from langchain_community.vectorstores import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
# --- FIN: NUEVAS LIBRERÍAS ---


# Registrar fuente Unicode (código existente sin cambios)
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
except Exception as e:
    st.sidebar.warning(f"Advertencia: No se encontró la fuente DejaVuSans.ttf. {e}")


# ==============================================================================
# 2. SECCIÓN DE AUTENTICACIÓN Y HELPERS
# ==============================================================================
ALLOWED_USERS = st.secrets.get("ALLOWED_USERS", {})

def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.header("Iniciar Sesión")
        username = st.text_input("Usuario", placeholder="Apple")
        password = st.text_input("Contraseña (4 dígitos)", type="password", placeholder="0000")
        if st.button("Ingresar"):
            if username in ALLOWED_USERS and password == ALLOWED_USERS.get(username):
                st.session_state.logged_in = True
                st.session_state.user = username
                st.session_state.cliente = username.lower()
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()
        
def reset_report_workflow():
    for k in ["report", "last_question", "report_question", "personalization", "rating"]:
        st.session_state.pop(k, None)

def reset_chat_workflow():
    st.session_state.pop("chat_history", None)
    
# --- INICIO: NUEVO HELPER PARA REINICIAR EL CHAT RAG ---
def reset_rag_chat_workflow():
    st.session_state.pop("rag_chat_history", None)
# --- FIN: NUEVO HELPER ---


# ==============================================================================
# 3. CONFIGURACIÓN DE APIS Y MODELOS (código existente sin cambios)
# ==============================================================================
api_keys = [st.secrets["API_KEY_1"], st.secrets["API_KEY_2"], st.secrets["API_KEY_3"]]
current_api_key_index = 0

def configure_api():
    global current_api_key_index
    genai.configure(api_key=api_keys[current_api_key_index])

configure_api()

generation_config = {
    "temperature": 0.5, "top_p": 0.8, "top_k": 32, "max_output_tokens": 8192,
}
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
]

def create_model():
    return genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=generation_config,
        safety_settings=safety_settings,
    )

model = create_model()

def switch_api_key():
    global current_api_key_index, model
    current_api_key_index = (current_api_key_index + 1) % len(api_keys)
    configure_api()
    model = create_model()

def call_gemini_api(prompt):
    try:
        response = model.generate_content([prompt])
        return html.unescape(response.text)
    except Exception as e:
        st.error(f"Error en la llamada a Gemini: {e}. Intentando cambiar API Key.")
        switch_api_key()
        try:
            response = model.generate_content([prompt])
            return html.unescape(response.text)
        except Exception as e2:
            st.error(f"Error GRAVE en la llamada a Gemini: {e2}")
            return None

# Supabase y logging (código existente sin cambios)
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
def log_query_event(query_text, mode, rating=None):
    data = { "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"), "user_name": st.session_state.user, "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "mode": mode, "query": query_text, "rating": rating, }
    supabase.table("queries").insert(data).execute()

# Normalización de texto (código existente sin cambios)
def normalize_text(text):
    if not text: return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()


# ==============================================================================
# 4. CARGA DE DATOS Y FILTROS (código existente sin cambios)
# ==============================================================================
@st.cache_data(show_spinner="Cargando base de conocimiento...")
def load_database(cliente: str):
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key   = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key   = st.secrets["S3_SECRET_KEY"]
    bucket_name     = st.secrets.get("S3_BUCKET")
    object_key      = "resultado_presentacion (1).json"
    try:
        s3 = boto3.client(
            "s3", endpoint_url=s3_endpoint_url, aws_access_key_id=s3_access_key, aws_secret_access_key=s3_secret_key,
        )
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        cliente_norm = normalize_text(cliente or "")
        if cliente_norm != "insights-atelier":
            filtered_data = []
            for doc in data:
                doc_cliente_norm = normalize_text(doc.get("cliente", ""))
                if "atelier" in doc_cliente_norm or cliente_norm in doc_cliente_norm:
                    filtered_data.append(doc)
            data = filtered_data
    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        data = []
    return data

def extract_brand(filename):
    if not filename or "In-ATL_" not in filename: return ""
    return filename.split("In-ATL_")[1].rsplit(".", 1)[0]

def apply_filter_criteria(db, selected_filter):
    if not selected_filter or selected_filter == "Todos": return db
    return [doc for doc in db if doc.get("filtro") == selected_filter]

# ==============================================================================
# 5. LÓGICA DE MODOS Y GENERACIÓN DE REPORTES/PDF
# (Tu código existente para report_mode, ideacion_mode, etc., va aquí)
# ==============================================================================
# ... (Aquí va todo tu código existente para `add_markdown_content`, `get_relevant_info`,
#      `generate_final_report`, `PDFReport`, `generate_pdf_html`, `ideacion_mode`,
#      `report_mode`, `concept_generation_mode`. NO lo elimines).
def get_relevant_info(db, question, selected_files):
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"
            for grupo in pres.get("grupos", []):
                contenido = grupo.get("contenido_texto", "")
                all_text += f"Grupo {grupo.get('grupo_index')}: {contenido}\n"
    return all_text
# (El resto de tus funciones existentes continúan aquí...)


# ==============================================================================
# 6. --- INICIO: NUEVAS FUNCIONES PARA EL CHAT FIEL (RAG) ---
# ==============================================================================

def prepare_rag_data(db):
    """Convierte los datos del JSON en una lista de Documentos para LangChain."""
    docs = []
    for pres in db:
        for grupo in pres.get("grupos", []):
            contenido = grupo.get("contenido_texto", "")
            if contenido:  # Solo añadir si hay contenido
                metadata = {
                    "fuente": pres.get('titulo_estudio', pres.get('nombre_archivo', 'Desconocido')),
                    "grupo": grupo.get('grupo_index', 'N/A')
                }
                docs.append(Document(page_content=contenido, metadata=metadata))
    return docs

@st.cache_resource(show_spinner="Preparando asistente de chat fiel...")
def setup_rag_pipeline(_db):
    """
    Crea y cachea el pipeline de RAG (VectorStore y Retriever).
    El `_` en `_db` indica a Streamlit que cachee basado en el objeto en sí.
    """
    documents = prepare_rag_data(_db)
    if not documents:
        return None

    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    vectorstore = Chroma.from_documents(documents=documents, embedding=embeddings)
    
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

    template = """
    Eres un asistente de IA llamado Atelier Data Studio. Tu única función es responder preguntas basándote exclusivamente en el contexto proporcionado, que proviene de reportes de investigación.

    **Instrucciones estrictas:**
    1.  **Usa solo el contexto**: Basa tu respuesta 100% en la información del siguiente 'Contexto'. No uses conocimiento externo.
    2.  **Sé conciso y claro**: Responde directamente a la pregunta sin añadir información superflua.
    3.  **Si no sabes, dilo**: Si la respuesta no se encuentra en el contexto, responde exactamente: "No tengo suficiente información en los reportes para responder a esa pregunta."
    4.  **Cita tus fuentes**: Al final de tu respuesta, añade una sección 'Fuentes:' y lista los títulos de los estudios usados del contexto.

    **Contexto:**
    {context}

    **Pregunta:**
    {question}

    **Respuesta Fiel:**
    """
    prompt = ChatPromptTemplate.from_template(template)
    
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1)

    rag_chain = (
        {"context": retriever, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    
    return rag_chain

def chat_con_reportes_mode(rag_chain):
    """Función para el modo 'Chat Fiel con Reportes'."""
    st.subheader("Modo Chat Fiel con Reportes")
    st.markdown("Conversa directamente con los hallazgos de los reportes seleccionados. Las respuestas se generan **únicamente** a partir de la información contenida en ellos para garantizar máxima fidelidad.")

    if rag_chain is None:
        st.warning("No hay datos en los reportes seleccionados para iniciar el chat. Por favor, ajusta los filtros.")
        return

    if "rag_chat_history" not in st.session_state:
        st.session_state.rag_chat_history = []

    for message in st.session_state.rag_chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("¿Qué quieres preguntar a los reportes?"):
        st.session_state.rag_chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Buscando en los reportes y generando respuesta..."):
                response = rag_chain.invoke(prompt)
                st.markdown(response)
        
        st.session_state.rag_chat_history.append({"role": "assistant", "content": response})
        log_query_event(prompt, mode="Chat Fiel con Reportes")
        
    if st.session_state.rag_chat_history:
        st.button("Nueva conversación fiel", on_click=reset_rag_chat_workflow, key="new_rag_chat_btn")


# ==============================================================================
# 7. FUNCIÓN PRINCIPAL (main) - MODIFICADA
# ==============================================================================
def main():
    if not st.session_state.get("logged_in"):
        show_login()

    st.title("Atelier Data Studio")
    st.markdown(
        "Herramienta impulsada por modelos lingüísticos para consultar y conversar con datos de estudios de mercado."
    )

    db = load_database(st.session_state.cliente)
    if not db:
        st.warning("No se encontraron datos para el cliente actual o hubo un error al cargar la base de datos.")
        st.stop()

    # --- MODIFICADO: Añadida la nueva opción de chat ---
    modo = st.sidebar.radio(
        "Seleccione el modo de uso:",
        ["Generar un reporte de reportes", "Conversaciones creativas", "Generación de conceptos", "Chat Fiel con Reportes"]
    )

    # Filtros en la sidebar (aplicados a una copia para no afectar la DB original)
    db_filtered = db
    filtros = sorted({doc.get("filtro", "") for doc in db_filtered if doc.get("filtro")})
    filtros.insert(0, "Todos")
    selected_filter = st.sidebar.selectbox("Seleccione la marca:", filtros)
    db_filtered = apply_filter_criteria(db_filtered, selected_filter)
    
    # (El resto de tus filtros aquí, aplicados a `db_filtered`)
    
    selected_files = [d.get("nombre_archivo") for d in db_filtered]
    
    # --- MODIFICADO: Lógica para llamar a la función del modo seleccionado ---
    if modo == "Generar un reporte de reportes":
        report_mode(db_filtered, selected_files)
    elif modo == "Conversaciones creativas":
        ideacion_mode(db_filtered, selected_files)
    elif modo == "Generación de conceptos":
        concept_generation_mode(db_filtered, selected_files)
    elif modo == "Chat Fiel con Reportes":
        rag_chain = setup_rag_pipeline(db_filtered)
        chat_con_reportes_mode(rag_chain)

    if st.sidebar.button("Cerrar Sesión", key="logout_main"):
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()

if __name__ == "__main__":
    main()
