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

# ### NUEVO ### - Paso 2: Centralizar la Lógica de los Planes
# ==============================
# DEFINICIÓN DE PLANES Y PERMISOS
# ==============================
PLAN_FEATURES = {
    "Explorer": {
        "reports_per_month": 2,
        "chat_queries_per_day": 4,
        "projects_per_year": 2, # Nota: La lógica para este límite no está implementada, pero se deja definida.
        "has_creative_conversation": False,
        "has_concept_generation": False,
        "has_idea_evaluation": False,
    },
    "Strategist": {
        "reports_per_month": 25,
        "chat_queries_per_day": float('inf'), # 'inf' significa infinito/ilimitado
        "projects_per_year": 10,
        "has_creative_conversation": True,
        "has_concept_generation": True,
        "has_idea_evaluation": False,
    },
    "Enterprise": {
        "reports_per_month": float('inf'),
        "chat_queries_per_day": float('inf'),
        "projects_per_year": float('inf'),
        "has_creative_conversation": True,
        "has_concept_generation": True,
        "has_idea_evaluation": True,
    }
}

# ==============================
# Autenticación Personalizada
# ==============================
# ### MODIFICADO ### - Paso 3: Actualizar el Inicio de Sesión para usar Supabase
# Se asume que la tabla 'users' en Supabase tiene las columnas: 'username', 'password', 'plan'.
def show_login():
    """
    Muestra el formulario de inicio de sesión que consulta la tabla 'users' en Supabase.
    """
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.header("Iniciar Sesión")
        username = st.text_input("Usuario", placeholder="Apple")
        password = st.text_input("Contraseña", type="password", placeholder="****")

        if st.button("Ingresar"):
            # Consulta a la base de datos de Supabase
            # IMPORTANTE: En un entorno de producción real, NUNCA guardes ni compares contraseñas en texto plano.
            # Usa una librería de hashing como `bcrypt` o la autenticación integrada de Supabase.
            response = supabase.table("users").select("*").eq("username", username).eq("password", password).execute()

            if response.data:
                user_data = response.data[0]
                st.session_state.logged_in = True
                st.session_state.user = user_data['username']
                st.session_state.cliente = user_data['username'].lower()

                # --- ¡AÑADIDO CLAVE! ---
                # Guardamos el plan y los permisos del usuario en la sesión
                user_plan = user_data.get('plan', 'Explorer') # Por defecto es 'Explorer' si no está definido
                st.session_state.plan = user_plan
                st.session_state.plan_features = PLAN_FEATURES.get(user_plan, PLAN_FEATURES['Explorer'])
                # -------------------------

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

# ### NUEVO ### - Paso 4: Implementar el Rastreo de Uso
# ==============================
# FUNCIONES DE RASTREO DE USO
# ==============================
def get_monthly_usage(username, action_type):
    """Cuenta el uso de una acción para un usuario en el mes actual."""
    today = datetime.date.today()
    first_day_of_month = today.replace(day=1)

    response = supabase.table("queries") \
        .select("id", count='exact') \
        .eq("user_name", username) \
        .eq("mode", action_type) \
        .gte("timestamp", str(first_day_of_month)) \
        .execute()
    return response.count

def get_daily_usage(username, action_type):
    """Cuenta el uso de una acción para un usuario en el día actual."""
    today_start = datetime.datetime.now().strftime("%Y-%m-%d 00:00:00")

    response = supabase.table("queries") \
        .select("id", count='exact') \
        .eq("user_name", username) \
        .eq("mode", action_type) \
        .gte("timestamp", today_start) \
        .execute()
    return response.count

# ==============================
# Normalización de Texto y otras utilidades...
# (El resto de las funciones de ayuda permanecen igual)
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


@st.cache_data(show_spinner=False)
def load_database(cliente: str):
    #... (Esta función no necesita cambios)
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

# ... (El resto de funciones de generación de reportes y PDF no necesitan cambios)
def extract_brand(filename):
    if not filename or "In-ATL_" not in filename:
        return ""
    return filename.split("In-ATL_")[1].rsplit(".", 1)[0]
    
# ... (PDFReport class y otras funciones auxiliares no necesitan cambios)
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
    
    # ... (Prompts sin cambios)
    prompt1 = "..." 
    result1 = call_gemini_api(prompt1)
    if result1 is None: return None
    
    prompt2 = "..."
    result2 = call_gemini_api(prompt2)
    if result2 is None: return None
    
    informe_completo = f"{question}\n\n" + result2
    return informe_completo

def clean_text(text):
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;')

class PDFReport:
    pass #... (Clase sin cambios)

def generate_pdf_html(content, title="Documento Final", banner_path=None, output_filename=None):
    pass #... (Función sin cambios)


# =====================================================
# MODOS DE LA APLICACIÓN (AQUÍ SE APLICAN LOS LÍMITES)
# =====================================================

def report_mode(db, selected_files):
    st.markdown("### Generar Reporte de Reportes")
    
    # ... (UI sin cambios)
    if "report" in st.session_state and st.session_state["report"]:
        st.markdown("---")
        st.markdown("### Informe Generado")
        st.markdown(st.session_state["report"])
        st.markdown("---")

    question = st.text_area(
        "Escribe tu consulta para el reporte…", 
        value="", 
        height=150, 
        key="report_question"
    )

    if st.button("Generar Reporte"):
        # ### MODIFICADO ### - Paso 5B: Verificar el límite del plan antes de continuar
        report_limit = st.session_state.plan_features['reports_per_month']
        current_reports = get_monthly_usage(st.session_state.user, "Generar un reporte de reportes")

        if current_reports >= report_limit:
            st.error(f"Has alcanzado tu límite de {int(report_limit)} reportes este mes.")
            st.warning("🚀 ¡Actualiza tu plan para generar más reportes!")
            return # Detiene la ejecución si se alcanzó el límite

        # Si el límite está OK, se procede normalmente
        if not question.strip():
            st.warning("Por favor, ingresa una consulta para generar el reporte.")
        else:
            st.session_state["last_question"] = question
            with st.spinner("Generando informe... Este proceso puede tardar un momento."):
                report = generate_final_report(question, db, selected_files)
            
            if report is None:
                st.error("No se pudo generar el informe.")
                st.session_state.pop("report", None)
            else:
                st.session_state["report"] = report
                # Se registra el evento DESPUÉS de una generación exitosa
                log_query_event(question, mode="Generar un reporte de reportes")
            
            st.rerun()

    # ... (Resto de la UI sin cambios)
    if "report" in st.session_state and st.session_state["report"]:
        final_content = st.session_state["report"]
        pdf_bytes = generate_pdf_html(final_content, title="Informe Final", banner_path=banner_file)
        
        col1, col2 = st.columns(2)
        with col1:
            if pdf_bytes:
                st.download_button("Descargar Informe en PDF", data=pdf_bytes, file_name="Informe_AtelierIA.pdf", mime="application/pdf", use_container_width=True)
        with col2:
            st.button("Nueva consulta", on_click=reset_report_workflow, key="new_report_query_btn", use_container_width=True)


def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    st.markdown(
        "Realiza preguntas específicas y obtén respuestas concretas basadas "
        "únicamente en los hallazgos de los informes seleccionados. "
        "El asistente no utilizará conocimiento externo."
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        st.markdown(f"**{msg['role'].capitalize()}:** {msg['message']}")

    user_input = st.text_area("Escribe tu pregunta...", height=150)

    if st.button("Enviar Pregunta"):
        # ### MODIFICADO ### - Paso 5B: Verificar el límite diario de consultas
        query_limit = st.session_state.plan_features['chat_queries_per_day']
        current_queries = get_daily_usage(st.session_state.user, "Chat de Consulta Directa")

        if current_queries >= query_limit:
            st.error(f"Has alcanzado tu límite de {int(query_limit)} consultas diarias.")
            st.warning("🚀 ¡Actualiza tu plan para tener consultas ilimitadas!")
            return # Detiene la ejecución
        
        # Si el límite está OK, se procede
        if not user_input.strip():
            st.warning("Por favor, ingresa una pregunta para continuar.")
        else:
            st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
            
            relevant_info = get_relevant_info(db, user_input, selected_files)
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history)
            grounded_prompt = f"..." # Prompt sin cambios

            with st.spinner("Buscando en los reportes..."):
                response = call_gemini_api(grounded_prompt)
            
            if response:
                st.session_state.chat_history.append({"role": "Asistente", "message": response})
                # Se registra el evento DESPUÉS de una respuesta exitosa
                log_query_event(user_input, mode="Chat de Consulta Directa")
                st.rerun()
            else:
                st.error("Error al generar la respuesta.")

    if st.session_state.chat_history:
        # ... (UI de descarga sin cambios)
        pass


# Las demás funciones de modo (ideacion_mode, concept_generation_mode, idea_evaluator_mode)
# no necesitan verificación de límites porque se activan/desactivan por completo en el menú.


def main():
    if not st.session_state.get("logged_in"):
        show_login()

    # --- CSS y Logo (sin cambios) ---
    st.markdown("""<style>...</style>""", unsafe_allow_html=True)
    st.sidebar.image("LogoDataStudio.png")

    try:
        db_full = load_database(st.session_state.cliente)
        db_filtered = db_full[:]
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        st.stop()

    # ### MODIFICADO ### - Paso 5A: Filtrar los Modos Disponibles según el Plan
    user_features = st.session_state.plan_features
    
    modos_disponibles = [
        "Generar un reporte de reportes",
        "Chat de Consulta Directa",
    ]

    if user_features.get("has_creative_conversation"):
        modos_disponibles.append("Conversaciones creativas")
    if user_features.get("has_concept_generation"):
        modos_disponibles.append("Generación de conceptos")
    if user_features.get("has_idea_evaluation"):
        modos_disponibles.append("Evaluar una idea")

    st.sidebar.header("Seleccione el modo de uso")
    modo = st.sidebar.radio(
        "Modos:",
        modos_disponibles,
        label_visibility="collapsed"
    )

    # --- Resto de la lógica de filtros y de la UI (sin cambios) ---
    if 'current_mode' not in st.session_state:
        st.session_state.current_mode = modo
    
    if st.session_state.current_mode != modo:
        # ... (lógica de reinicio de flujos sin cambios)
        st.session_state.current_mode = modo

    st.sidebar.header("Filtros de Búsqueda")
    # ... (Filtros sin cambios)

    if modo == "Generar un reporte de reportes":
        st.sidebar.radio("Califique el informe:", [1, 2, 3, 4, 5], horizontal=True, key="rating")

    if st.sidebar.button("Cerrar Sesión", key="logout_main"):
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()

    selected_files = [d.get("nombre_archivo") for d in db_filtered]

    # --- Lógica de renderizado de modo (sin cambios) ---
    if modo == "Generar un reporte de reportes":
        report_mode(db_filtered, selected_files)
    elif modo == "Conversaciones creativas":
        ideacion_mode(db_filtered, selected_files)
    elif modo == "Generación de conceptos":
        concept_generation_mode(db_filtered, selected_files)
    elif modo == "Chat de Consulta Directa":
        grounded_chat_mode(db_filtered, selected_files)
    elif modo == "Evaluar una idea":
        idea_evaluator_mode(db_filtered, selected_files)

if __name__ == "__main__":
    main()
