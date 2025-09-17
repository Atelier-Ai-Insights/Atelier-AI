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
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
except IOError:
    st.sidebar.warning("Fuente DejaVuSans.ttf no encontrada. Los PDFs podrían no mostrar caracteres especiales.")

# ==============================
# Autenticación Personalizada
# ==============================
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

def logout():
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()
        
# ====== Helpers para reiniciar flujos ======
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

# ==============================
# CARGA DE DATOS DESDE S3
# ==============================
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
# FILTROS Y PROCESAMIENTO
# ==============================
def extract_brand(filename):
    if not filename or "In-ATL_" not in filename:
        return ""
    return filename.split("In-ATL_")[1].rsplit(".", 1)[0]

def apply_filter_criteria(db, selected_filter):
    if not selected_filter or selected_filter == "Todos":
        return db
    return [doc for doc in db if doc.get("filtro") == selected_filter]

def get_relevant_info(db, question, selected_files):
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"
            for grupo in pres.get("grupos", []):
                contenido = grupo.get("contenido_texto", "")
                all_text += f"Grupo {grupo.get('grupo_index')}: {contenido}\n"
                if grupo.get("metadatos"):
                    all_text += f"Metadatos: {json.dumps(grupo.get('metadatos'), ensure_ascii=False)}\n"
                if grupo.get("hechos"):
                    all_text += f"Hechos: {json.dumps(grupo.get('hechos'), ensure_ascii=False)}\n"
            all_text += "\n---\n\n"
    return all_text

# ... (Aquí irían las funciones de PDF que son muy largas, se incluyen al final del script) ...

# =====================================================
# LÓGICA DE LOS MODOS DE OPERACIÓN
# =====================================================

def report_mode(db, selected_files):
    # ... (Tu código para report_mode) ...
    pass

def ideacion_mode(db, selected_files):
    # ... (Tu código para ideacion_mode) ...
    pass

def concept_generation_mode(db, selected_files):
    # ... (Tu código para concept_generation_mode) ...
    pass

# === INICIO DE LA NUEVA FUNCIÓN Y SU LÓGICA ===

def prepare_notebook_context(db, selected_files):
    """
    Prepara el contexto para el chat estilo NotebookLM, asignando una
    etiqueta de fuente única a cada 'grupo' de cada documento.
    """
    context_string = "CONTEXTO DE LOS DOCUMENTOS:\n\n"
    doc_counter = 1
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            doc_title = pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin Título'))
            for grupo in pres.get("grupos", []):
                grupo_index = grupo.get('grupo_index')
                # Crear una etiqueta de fuente clara y única
                source_tag = f"[Fuente {doc_counter}.{grupo_index}: {doc_title}]"
                
                # Unir el contenido del grupo en un solo texto
                contenido_grupo = f"{source_tag}\n"
                contenido_grupo += f"Texto Principal: {grupo.get('contenido_texto', '')}\n"
                if grupo.get('metadatos'):
                    contenido_grupo += f"Metadatos: {json.dumps(grupo.get('metadatos'), ensure_ascii=False)}\n"
                if grupo.get('hechos'):
                    contenido_grupo += f"Hechos Clave: {json.dumps(grupo.get('hechos'), ensure_ascii=False)}\n"
                
                context_string += contenido_grupo + "\n---\n"
            doc_counter += 1
    return context_string

def notebooklm_chat_mode(db, selected_files):
    """
    Modo de Chat estilo NotebookLM: Conversa con los datos de los reportes
    con respuestas basadas en fuentes y con citaciones.
    """
    st.subheader("Chat con Documentos (estilo NotebookLM)")
    st.info("Haz preguntas sobre los documentos que seleccionaste en los filtros. La IA responderá basándose únicamente en esa información y citará sus fuentes.")

    # Inicializar historial de chat para este modo específico
    if "notebook_chat_history" not in st.session_state:
        st.session_state.notebook_chat_history = [
            {"role": "assistant", "content": "Hola, ¿en qué puedo ayudarte a investigar dentro de los documentos seleccionados?"}
        ]

    # Mostrar historial de mensajes
    for message in st.session_state.notebook_chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Input del usuario
    if prompt := st.chat_input("Pregunta sobre los documentos seleccionados..."):
        # Añadir mensaje del usuario al historial y mostrarlo
        st.session_state.notebook_chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generar y mostrar respuesta del asistente
        with st.chat_message("assistant"):
            with st.spinner("Buscando en los documentos y generando respuesta..."):
                # 1. Preparar el contexto con fuentes
                contexto_fuentes = prepare_notebook_context(db, selected_files)

                # 2. Construir el historial de conversación para el prompt
                historial_str = "\n".join([f'{m["role"]}: {m["content"]}' for m in st.session_state.notebook_chat_history])
                
                # 3. Diseñar el prompt para la IA
                notebook_prompt = f"""
                Eres un asistente de investigación experto y preciso. Tu tarea es responder la pregunta del usuario basándote ÚNICA Y EXCLUSIVAMENTE en la información proporcionada en el "CONTEXTO DE LOS DOCUMENTOS".

                **INSTRUCCIONES CRÍTICAS:**
                1.  **CITA TUS FUENTES:** Para CADA afirmación que hagas, debes citar la fuente exacta de donde obtuviste la información. Utiliza el identificador que aparece al inicio de cada bloque de texto, por ejemplo: [Fuente 1.2: Título del Estudio]. Si una misma frase se basa en varias fuentes, cítalas todas.
                2.  **SÉ FIEL AL TEXTO:** No inventes, supongas ni añadas información que no esté explícitamente en el contexto.
                3.  **SI NO SABES, DILO:** Si la respuesta a la pregunta no se encuentra en el contexto, DEBES responder únicamente con: "La información solicitada no se encuentra en los documentos proporcionados."
                4.  **SINTETIZA:** Combina información de diferentes fuentes si es necesario para dar una respuesta completa, pero siempre cita cada pieza de información.

                **HISTORIAL DE LA CONVERSACIÓN:**
                {historial_str}

                {contexto_fuentes}

                **PREGUNTA DEL USUARIO:**
                {prompt}

                **TU RESPUESTA (precisa y citando cada fuente):**
                """
                
                # 4. Llamar a la API
                response = call_gemini_api(notebook_prompt)
                
                if response:
                    st.markdown(response)
                    # Añadir respuesta del asistente al historial
                    st.session_state.notebook_chat_history.append({"role": "assistant", "content": response})
                    log_query_event(prompt, mode="Chat NotebookLM")
                else:
                    error_message = "Hubo un error al generar la respuesta."
                    st.error(error_message)
                    st.session_state.notebook_chat_history.append({"role": "assistant", "content": error_message})

# === FIN DE LA NUEVA FUNCIÓN ===

def main():
    st.set_page_config(page_title="Atelier Data Studio", layout="wide")
    if not st.session_state.get("logged_in"):
        show_login()

    st.title("Atelier Data Studio")
    st.markdown(
        "Herramienta de IA para realizar consultas y conversar con datos de estudios de mercado."
    )

    db = load_database(st.session_state.cliente)
    if not db:
        st.warning("No se encontraron datos para tu usuario o no se pudo cargar la base de datos.")
        logout()
        st.stop()
    
    with st.sidebar:
        st.header("Menú de Opciones")
        # === LÍNEA MODIFICADA ===
        modo = st.radio(
            "Seleccione el modo de uso:",
            ["Generar un reporte de reportes", "Conversaciones creativas", "Generación de conceptos", "Chat con Documentos (estilo NotebookLM)"],
            key="modo_seleccionado"
        )

        st.divider()
        st.header("Filtros de Datos")
        
        filtros = sorted({doc.get("filtro", "") for doc in db if doc.get("filtro")})
        filtros.insert(0, "Todos")
        selected_filter = st.selectbox("Seleccione la marca:", filtros)
        
        db_filtered_by_marca = apply_filter_criteria(db, selected_filter)
        
        years = sorted({doc.get("marca", "") for doc in db_filtered_by_marca if doc.get("marca")})
        years.insert(0, "Todos")
        selected_year = st.selectbox("Seleccione el año:", years)
        
        if selected_year != "Todos":
            db_filtered_by_year = [d for d in db_filtered_by_marca if d.get("marca") == selected_year]
        else:
            db_filtered_by_year = db_filtered_by_marca

        brands = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_filtered_by_year})
        brands.insert(0, "Todas")
        selected_brand = st.selectbox("Seleccione el proyecto:", brands)
        
        if selected_brand != "Todas":
            final_db = [d for d in db_filtered_by_year if extract_brand(d.get("nombre_archivo", "")) == selected_brand]
        else:
            final_db = db_filtered_by_year

        st.divider()

        if modo == "Generar un reporte de reportes":
            st.radio("Califique el informe:", [1, 2, 3, 4, 5], horizontal=True, key="rating")

        logout()

    selected_files = [d.get("nombre_archivo") for d in final_db]

    if not selected_files and (selected_filter != "Todos" or selected_year != "Todos" or selected_brand != "Todas"):
        st.warning("No hay documentos que coincidan con los filtros seleccionados. Por favor, ajusta tu selección.")
    
    # === BLOQUE MODIFICADO ===
    if modo == "Generar un reporte de reportes":
        # Asegúrate de que esta función exista en tu código
        # report_mode(final_db, selected_files) 
        pass
    elif modo == "Conversaciones creativas":
        # Asegúrate de que esta función exista en tu código
        # ideacion_mode(final_db, selected_files)
        pass
    elif modo == "Generación de conceptos":
        # Asegúrate de que esta función exista en tu código
        # concept_generation_mode(final_db, selected_files)
        pass
    elif modo == "Chat con Documentos (estilo NotebookLM)":
        notebooklm_chat_mode(final_db, selected_files)


if __name__ == "__main__":
    main()

# --- NOTA: Asegúrate de tener el código completo para las funciones de PDF y los otros modos ---
# --- que se omitieron por brevedad en la explicación.                     ---
