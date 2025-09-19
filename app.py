# ==============================================================================
# 1. IMPORTACIONES
# ==============================================================================
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

# --- LIBRERÍAS PARA EL CHAT RAG ---
from langchain.docstore.document import Document
from langchain_community.vectorstores import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

# Registrar fuente Unicode
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
except Exception as e:
    st.sidebar.warning(f"Advertencia: No se encontró la fuente DejaVuSans.ttf. {e}")


# ==============================================================================
# 2. AUTENTICACIÓN Y HELPERS
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
    
def reset_rag_chat_workflow():
    st.session_state.pop("rag_chat_history", None)

# ==============================================================================
# 3. CONFIGURACIÓN DE APIS Y MODELOS
# ==============================================================================
api_keys = [st.secrets["API_KEY_1"], st.secrets["API_KEY_2"], st.secrets["API_KEY_3"]]
current_api_key_index = 0

def configure_api():
    global current_api_key_index
    genai.configure(api_key=api_keys[current_api_key_index])

configure_api()

generation_config = {"temperature": 0.5, "top_p": 0.8, "top_k": 32, "max_output_tokens": 8192}
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

supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
def log_query_event(query_text, mode, rating=None):
    data = {"id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"), "user_name": st.session_state.user, "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "mode": mode, "query": query_text, "rating": rating}
    supabase.table("queries").insert(data).execute()

def normalize_text(text):
    if not text: return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()


# ==============================================================================
# 4. CARGA DE DATOS Y FILTROS
# ==============================================================================
@st.cache_data(show_spinner="Cargando base de conocimiento...")
def load_database(cliente: str):
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key   = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key   = st.secrets["S3_SECRET_KEY"]
    bucket_name     = st.secrets.get("S3_BUCKET")
    object_key      = "resultado_presentacion (1).json"
    try:
        s3 = boto3.client("s3", endpoint_url=s3_endpoint_url, aws_access_key_id=s3_access_key, aws_secret_access_key=s3_secret_key)
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        cliente_norm = normalize_text(cliente or "")
        if cliente_norm != "insights-atelier":
            data = [doc for doc in data if "atelier" in normalize_text(doc.get("cliente", "")) or cliente_norm in normalize_text(doc.get("cliente", ""))]
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
# 5. FUNCIONES ORIGINALES (Reporte, Creativo, Conceptos y PDF)
# ==============================================================================

# -- Funciones auxiliares para reportes y PDF
banner_file = "Banner (2).jpg"

def get_relevant_info(db, question, selected_files):
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"
            for grupo in pres.get("grupos", []):
                contenido = grupo.get("contenido_texto", "")
                all_text += f"Grupo {grupo.get('grupo_index')}: {contenido}\n"
    return all_text

def clean_text(text):
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;')

# -- Clase para generar PDF
class PDFReport:
    # (Aquí va el código completo de tu clase PDFReport, sin cambios)
    pass # Reemplaza este 'pass' con tu código completo de la clase

# -- Función para generar PDF
def generate_pdf_html(content, title="Documento Final", banner_path=None, output_filename=None):
    # (Aquí va el código completo de tu función generate_pdf_html, sin cambios)
    pass # Reemplaza este 'pass' con tu código completo de la función

# -- Función para generar el reporte de reportes
def generate_final_report(question, db, selected_files):
    # (Aquí va el código completo de tu función generate_final_report, sin cambios)
    pass # Reemplaza este 'pass' con tu código completo de la función

# -- MODO 1: Generar Reporte de Reportes
def report_mode(db, selected_files):
    st.markdown("### Generar reporte")
    question = st.text_area("Escribe tu consulta…", value=st.session_state.get("last_question", ""), height=150, key="report_question")
    
    if st.button("Generar Reporte"):
        if not question.strip():
            st.warning("Ingrese una consulta.")
        else:
            if question != st.session_state.get("last_question"):
                st.session_state.pop("report", None)
                st.session_state["last_question"] = question

            if "report" not in st.session_state:
                with st.spinner("Generando informe..."):
                    report = generate_final_report(question, db, selected_files)
                if report:
                    st.session_state["report"] = report
                else:
                    st.error("No se pudo generar el informe.")
                    return

    if "report" in st.session_state:
        st.markdown("### Informe Final")
        edited = st.text_area("Informe generado:", value=st.session_state["report"], height=400, key="report_edit")
        pdf_bytes = generate_pdf_html(edited, title="Informe Final", banner_path=banner_file)
        if pdf_bytes:
            st.download_button("Descargar Informe en PDF", data=pdf_bytes, file_name="Informe_AtelierIA.pdf", mime="application/pdf")
        st.button("Nueva consulta", on_click=reset_report_workflow)
        log_query_event(question, mode="Generación")

# -- MODO 2: Conversaciones Creativas
def ideacion_mode(db, selected_files):
    st.subheader("Modo Conversación: Conversa con los datos")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        st.markdown(f"**{msg['role'].capitalize()}:** {msg['message']}")

    user_input = st.text_area("Pregunta algo…", height=150)

    if st.button("Enviar pregunta"):
        if not user_input.strip():
            st.warning("Ingrese su pregunta para continuar.")
        else:
            st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
            relevant = get_relevant_info(db, user_input, selected_files)
            # (El resto de la lógica de ideacion_mode va aquí)
            pass # Reemplaza este 'pass' con la lógica de tu prompt y llamada a la API

# -- MODO 3: Generación de Conceptos
def concept_generation_mode(db, selected_files):
    st.subheader("Modo Generación de Conceptos")
    product_idea = st.text_area("Describe tu idea de producto o servicio:", height=150)

    if st.button("Generar Concepto"):
        if not product_idea.strip():
            st.warning("Por favor, describe tu idea.")
        else:
            with st.spinner("Generando el concepto..."):
                context_info = get_relevant_info(db, product_idea, selected_files)
                # (El resto de la lógica de concept_generation_mode va aquí)
                pass # Reemplaza este 'pass' con la lógica de tu prompt y llamada a la API


# ==============================================================================
# 6. NUEVAS FUNCIONES PARA EL CHAT FIEL (RAG)
# ==============================================================================
def prepare_rag_data(db):
    docs = []
    for pres in db:
        for grupo in pres.get("grupos", []):
            contenido = grupo.get("contenido_texto", "")
            if contenido:
                metadata = {"fuente": pres.get('titulo_estudio', pres.get('nombre_archivo', 'Desconocido')), "grupo": grupo.get('grupo_index', 'N/A')}
                docs.append(Document(page_content=contenido, metadata=metadata))
    return docs

@st.cache_resource(show_spinner="Preparando asistente de chat fiel...")
def setup_rag_pipeline(_db):
    documents = prepare_rag_data(_db)
    if not documents: return None

    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    vectorstore = Chroma.from_documents(documents=documents, embedding=embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

    template = """
    Eres un asistente de IA de Atelier Data Studio. Responde preguntas basándote exclusivamente en el contexto de reportes proporcionado.
    **Instrucciones estrictas:**
    1.  **Usa solo el contexto**. No uses conocimiento externo.
    2.  **Sé conciso y claro**.
    3.  Si la respuesta no está en el contexto, responde: "No tengo suficiente información en los reportes para responder a esa pregunta."
    4.  Al final, añade una sección 'Fuentes:' y lista los títulos de los estudios usados.
    **Contexto:** {context}
    **Pregunta:** {question}
    **Respuesta Fiel:**
    """
    prompt = ChatPromptTemplate.from_template(template)
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1)
    rag_chain = ({"context": retriever, "question": RunnablePassthrough()} | prompt | llm | StrOutputParser())
    return rag_chain

def chat_con_reportes_mode(rag_chain):
    st.subheader("Modo Chat Fiel con Reportes")
    st.markdown("Conversa directamente con los hallazgos de los reportes. Las respuestas se basan **únicamente** en ellos.")

    if rag_chain is None:
        st.warning("No hay datos en los reportes seleccionados para iniciar el chat. Ajusta los filtros.")
        return

    if "rag_chat_history" not in st.session_state:
        st.session_state.rag_chat_history = []

    for message in st.session_state.rag_chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("¿Qué quieres preguntar a los reportes?"):
        st.session_state.rag_chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Generando respuesta..."):
                response = rag_chain.invoke(prompt)
                st.markdown(response)
        
        st.session_state.rag_chat_history.append({"role": "assistant", "content": response})
        log_query_event(prompt, mode="Chat Fiel con Reportes")
        
    if st.session_state.rag_chat_history:
        st.button("Nueva conversación fiel", on_click=reset_rag_chat_workflow)


# ==============================================================================
# 7. FUNCIÓN PRINCIPAL (main)
# ==============================================================================
def main():
    if not st.session_state.get("logged_in"):
        show_login()

    st.title("Atelier Data Studio")
    st.markdown("Herramienta para consultar y conversar con datos de estudios de mercado.")

    db = load_database(st.session_state.cliente)
    if not db:
        st.warning("No se encontraron datos para el cliente actual.")
        st.stop()

    modo = st.sidebar.radio(
        "Seleccione el modo de uso:",
        ["Generar un reporte de reportes", "Conversaciones creativas", "Generación de conceptos", "Chat Fiel con Reportes"]
    )

    # Filtros
    db_filtered = db
    filtros = sorted({doc.get("filtro", "") for doc in db_filtered if doc.get("filtro")})
    filtros.insert(0, "Todos")
    selected_filter = st.sidebar.selectbox("Seleccione la marca:", filtros)
    db_filtered = apply_filter_criteria(db_filtered, selected_filter)
    
    selected_files = [d.get("nombre_archivo") for d in db_filtered]
    
    # Lógica de modos
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
