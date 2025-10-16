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

# === FUNCIÓN AJUSTADA ===
def show_login():
    """
    Muestra el formulario de inicio de sesión centrado en la página utilizando st.columns.
    """
    # Creamos tres columnas para centrar el formulario.
    # Las columnas de los lados (col1 y col3) actúan como márgenes vacíos.
    col1, col2, col3 = st.columns([1, 2, 1])

    # Todo el contenido del formulario se coloca dentro de la columna central (col2).
    with col2:
        st.header("Iniciar Sesión")
        username = st.text_input("Usuario", placeholder="Apple")
        password = st.text_input("Contraseña (4 dígitos)", type="password", placeholder="0000")

        if st.button("Ingresar"):
            # Usamos .get() para una comprobación más segura y evitar errores
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
        
# ====== Helper para reiniciar el flujo de reportes ======
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
        text = html.unescape(text)
        return text
    except Exception as e:
        st.error(f"Error en la llamada a Gemini: {e}. Intentando cambiar API Key.")
        switch_api_key()
        try:
            response = model.generate_content([prompt])
            text = response.text
            text = html.unescape(text)
            return text
        except Exception as e2:
            st.error(f"Error GRAVE en la llamada a Gemini: {e2}")
            return None

# ==============================
# CONEXIÓN A SUPABASE PARA GUARDAR CONSULTAS
# ==============================
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def log_query_event(query_text, mode, rating=None):
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
# Normalización de Texto
# ==============================
def normalize_text(text):
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()

def add_markdown_content(pdf, markdown_text):
    html_text = markdown2.markdown(
        markdown_text,
        extras=["fenced-code-blocks", "tables", "break-on-newline"]
    )
    soup = BeautifulSoup(html_text, "html.parser")
    container = soup.body or soup

    for elem in container.children:
        if elem.name:
            if elem.name.startswith("h"):
                try:
                    level = int(elem.name[1])
                except:
                    level = 1
                pdf.add_title(elem.get_text(strip=True), level=level)
            elif elem.name == "p":
                pdf.add_paragraph(elem.decode_contents())
            elif elem.name == "ul":
                for li in elem.find_all("li"):
                    pdf.add_paragraph("• " + li.decode_contents())
            elif elem.name == "ol":
                for idx, li in enumerate(elem.find_all("li"), 1):
                    pdf.add_paragraph(f"{idx}. {li.decode_contents()}")
            else:
                pdf.add_paragraph(elem.decode_contents())
        else:
            text = elem.string
            if text and text.strip():
                pdf.add_paragraph(text)

# ==============================
# CARGA DEL ARCHIVO JSON DESDE S3
# ==============================
@st.cache_data(show_spinner=False)
def load_database(cliente: str):
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key   = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key   = st.secrets["S3_SECRET_KEY"]
    bucket_name     = st.secrets.get("S3_BUCKET")
    object_key      = "resultado_presentacion (1).json"

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url          = s3_endpoint_url,
            aws_access_key_id     = s3_access_key,
            aws_secret_access_key = s3_secret_key,
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

# ==============================
# EXTRACCIÓN DE DATOS Y FILTROS
# ==============================
def extract_brand(filename):
    if not filename or "In-ATL_" not in filename:
        return ""
    return filename.split("In-ATL_")[1].rsplit(".", 1)[0]

# =====================================================
# FUNCIONES DE GENERACIÓN DE INFORMES Y PDF
# =====================================================
banner_file = "Banner (2).jpg"

def get_relevant_info(db, question, selected_files):
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"
            for grupo in pres.get("grupos", []):
                contenido = grupo.get("contenido_texto", "")
                all_text += f"Grupo {grupo.get('grupo_index')}: {contenido}\n"
                metadatos = grupo.get("metadatos", {})
                hechos      = grupo.get("hechos", {})
                if metadatos:
                    all_text += f"Metadatos: {json.dumps(metadatos, ensure_ascii=False)}\n"
                if hechos:
                    if hechos.get("tipo") == "cita":
                        all_text += "[Cita]\n"
                    else:
                        all_text += f"Hechos: {json.dumps(hechos, ensure_ascii=False)}\n"
            all_text += "\n---\n\n"
    return all_text

def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)
    
    # Prompt 1: Extrae hallazgos clave y referencias.
    prompt1 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones:\n"
        "1. Identifica en la pregunta la marca exacta y/o el producto exacto sobre el cual se hace la consulta. Sé muy específico y riguroso en referenciar información asociada a la marca y/o producto consultado.\n"
        "2. Reitera la pregunta del cliente: ***{question}***.\n"
        "3. Utiliza la 'Información de Contexto' (únicamente extractos de documentos de investigación) para extraer los hallazgos más relevantes que respondan directamente a la pregunta. Cuando se pregunte por una marca (ejemplo: oreo) siempre traer información de todos los reportes relacionados.\n"
        "4. No incluyas el texto completo de las citas, sino extractos breves que permitan identificar la fuente.\n"
        "5. Incluye metadatos relevantes (documentos, grupos, etc.) e indica en cada hallazgo si la cita sigue el estilo IEEE (ejemplo: [1]).\n"
        "6. En la sección 'Referencias', asocia cada número a la referencia completa, no escribas el nombre del archivo, sino el título del proyecto (ejemplo: [1] 'Título del Proyecto', año, etc.). Siempre provee las referencias citadas.\n"
        "7. Enfócate en los resultados y hallazgos positivos de los estudios, asumiendo que todos son estudios realizados.\n\n"
        f"Información de Contexto:\n{relevant_info}\n\n"
        "Respuesta (Hallazgos Clave y Referencias):\n"
        "## Hallazgos Clave:\n"
        "- [Hallazgo 1 con cita IEEE]\n"
        "- [Hallazgo 2 con cita IEEE]\n"
        "## Referencias:\n"
        "- [1] [Referencia completa]\n"
        "- [2] [Referencia completa]\n"
    )
    result1 = call_gemini_api(prompt1)
    if result1 is None: return None

    # Prompt 2: Redacta el informe principal. Se eliminan los '**' y '##' de los títulos para unificar el tamaño de la fuente en la página.
    prompt2 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones Generales:\n"
        "1. Identifica en la pregunta la marca y/o el producto exacto. Responde de manera específica y rigurosa a lo que el cliente pregunta.\n"
        "2. Recuerda que todos los estudios en la base de datos fueron realizados por Atelier. Menciónalo si es relevante, especialmente en 'Principales Hallazgos'.\n"
        "3. Actúa como un analista experto en ciencias del comportamiento, en investigación de mercados, en marketing y en comunicación estratégica. Enfócate en claridad, síntesis poderosa y pensamiento estructurado.\n"
        "4. El estilo de redacción debe ser claro, directo, conciso y memorable (inspirado en “Ideas que pegan” de Chip Heath y Dan Heath). Evita lenguaje técnico innecesario; prioriza lo relevante y accionable.\n\n"
        "Estructura del Informe (sé breve y preciso en cada sección):\n\n"
        "Introducción:\n"
        "   - Preserva esta sección. Plantea el contexto y la pregunta central. Usa un hallazgo relevante (de tipo cualitativo que provenga de los reportes seleccionados), para captar la atención y despierte interés por querer leer el informe.\n\n"
        "Principales Hallazgos:\n"
        "   - Presenta de forma estructurada los hechos más relevantes descubiertos, directamente desde la sección de resultados de los diferentes reportes y la información de contexto.\n"
        "   - Asegúrate de que cada hallazgo responda a la pregunta del cliente y ofrezca valor original y que sume valor para responder a la pregunta.\n"
        "   - Utiliza solo información relevante y que haga referencia a la marca y al producto citados. No utilices estudios de forma innecesaria.\n"
        "   - Referencia en formato IEEE (ej. [1]), usando el título del estudio o el producto del que se habla, más que el nombre del archivo.\n\n"
        "Insights:\n"
        "   - Extrae aprendizajes y verdades profundas a partir de los hallazgos. Utiliza analogías y comparaciones que refuercen el mensaje y transformen la comprensión del problema. Sé conciso. Utiliza frases suscitantas, es decir, frase cortas con mucho significado\n\n"
        "Conclusiones:\n"
        "   - Sintetiza la información y ofrece una dirección clara basada en los insights. Evita repetir información.\n\n"
        "Recomendaciones:\n"
        "   - Con base en el informe, proporciona 3-4 recomendaciones concretas, creativas, precisas y accionables que sirvan como inspiración para la toma de decisiones.\n"
        "   - Deben estar alineadas con los insights y conclusiones. Evita la extensión innecesaria.\n\n"
        "Referencias:\n"
        "   - Cita el título del estudio (no el nombre del archivo), utilizando la información de la primera diapositiva o metadatos disponibles.\n\n"
        "Utiliza el siguiente resumen (Hallazgos Clave y Referencias) y la Información de Contexto para elaborar el informe:\n\n"
        "5
