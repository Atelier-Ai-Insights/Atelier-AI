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

# Registrar fuente Unicode para tildes/ñ
# Asegúrate de que el archivo 'DejaVuSans.ttf' esté en el mismo directorio.
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
except Exception as e:
    # Si la fuente no se encuentra, la app funcionará pero el PDF puede no mostrar tildes/ñ correctamente.
    st.sidebar.warning(f"Advertencia: No se encontró la fuente DejaVuSans.ttf. {e}")


# ==============================
# Autenticación Personalizada
# ==============================
ALLOWED_USERS = st.secrets.get("ALLOWED_USERS", {})

def show_login():
    """
    Muestra el formulario de inicio de sesión centrado en la página utilizando st.columns.
    """
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


def logout():
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()
        
# ====== Helper para reiniciar flujos ======
def reset_report_workflow():
    for k in ["report", "last_question", "report_question", "personalization", "rating"]:
        st.session_state.pop(k, None)

def reset_chat_workflow():
    st.session_state.pop("chat_history", None)

# ==============================
# CONFIGURACIÓN DE LA API DE GEMINI
# ==============================
api_keys = [st.secrets["API_KEY_1"], st.secrets["API_KEY_2"], st.secrets["API_KEY_3"]]
current_api_key_index = 0

def configure_api():
    global current_api_key_index
    genai.configure(api_key=api_keys[current_api_key_index])

configure_api()

generation_config = {
    "temperature": 0.5,
    "top_p": 0.8,
    "top_k": 32,
    "max_output_tokens": 8192,
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
        text = response.text
        return html.unescape(text)
    except Exception as e:
        st.error(f"Error en la llamada a Gemini: {e}. Intentando cambiar API Key.")
        switch_api_key()
        try:
            response = model.generate_content([prompt])
            text = response.text
            return html.unescape(text)
        except Exception as e2:
            st.error(f"Error GRAVE en la llamada a Gemini: {e2}")
            return None

# ==============================
# CONEXIÓN A SUPABASE
# ==============================
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def log_query_event(query_text, mode, rating=None):
    if "user" not in st.session_state:
        return
    data = {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "user_name": st.session_state.user,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "query": query_text,
        "rating": rating,
    }
    supabase.table("queries").insert(data).execute()

# ==============================
# Normalización y Carga de Datos
# ==============================
def normalize_text(text):
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()

@st.cache_data(show_spinner="Cargando base de datos...")
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
            filtered_data = [doc for doc in data if "atelier" in normalize_text(doc.get("cliente", "")) or cliente_norm in normalize_text(doc.get("cliente", ""))]
            data = filtered_data
    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        data = []
    return data

# ==============================
# Filtros y Procesamiento
# ==============================
def extract_brand(filename):
    if not filename or "In-ATL_" not in filename:
        return ""
    return filename.split("In-ATL_")[1].rsplit(".", 1)[0]

def apply_filter_criteria(db, selected_filter):
    if not selected_filter or selected_filter == "Todos":
        return db
    return [doc for doc in db if doc.get("filtro") == selected_filter]

def get_relevant_info(db, selected_files):
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            doc_title = pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin Título'))
            all_text += f"## Documento: {doc_title}\n\n"
            for grupo in pres.get("grupos", []):
                all_text += f"### Fragmento {grupo.get('grupo_index')}\n"
                all_text += f"**Contenido:** {grupo.get('contenido_texto', '')}\n"
                if grupo.get("metadatos"):
                    all_text += f"**Metadatos:** {json.dumps(grupo.get('metadatos'), ensure_ascii=False, indent=2)}\n"
                if grupo.get("hechos"):
                    all_text += f"**Hechos Clave:** {json.dumps(grupo.get('hechos'), ensure_ascii=False, indent=2)}\n"
                all_text += "\n"
            all_text += "---\n\n"
    return all_text
    
# =====================================================
# LÓGICA DE LOS MODOS DE OPERACIÓN
# =====================================================

def report_mode(db, selected_files):
    st.markdown("### Generar reporte")
    # ... (código completo de report_mode)
    pass

def ideacion_mode(db, selected_files):
    st.subheader("Modo Conversación: Conversa con los datos")
    # ... (código completo de ideacion_mode)
    pass

def concept_generation_mode(db, selected_files):
    st.subheader("Modo Generación de Conceptos")
    # ... (código completo de concept_generation_mode)
    pass

# === INICIO DE LA NUEVA FUNCIÓN AÑADIDA ===

def research_chat_mode(db, selected_files):
    """
    Modo de Chat de Investigación: Conversa con los datos de los reportes,
    con respuestas basadas únicamente en la información proporcionada.
    """
    st.subheader("Chat de Investigación")
    st.info("Realiza preguntas sobre los documentos seleccionados en los filtros. La IA responderá basándose estrictamente en esa
