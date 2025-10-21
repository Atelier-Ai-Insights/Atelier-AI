import datetime
import html
import json
import unicodedata
from io import BytesIO
import os
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
from supabase import create_client, Client
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

import streamlit as st

# --- Estilos para ocultar elementos de Streamlit ---
hide_st_style = """
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stStatusWidget"] {visibility: hidden;}
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- Registro de Fuentes ---
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
except Exception as e:
    st.sidebar.warning(f"Advertencia: No se encontró la fuente DejaVuSans.ttf. {e}")

# ==============================
# DEFINICIÓN DE PLANES Y PERMISOS
# ==============================
PLAN_FEATURES = {
    "Explorer": {
        "reports_per_month": 0, "chat_queries_per_day": 4, "projects_per_year": 2,
        "has_report_generation": False, "has_creative_conversation": False, "has_concept_generation": False, "has_idea_evaluation": False,
    },
    "Strategist": {
        "reports_per_month": 0, "chat_queries_per_day": float('inf'), "projects_per_year": 10,
        "has_report_generation": False, "has_creative_conversation": True, "has_concept_generation": True, "has_idea_evaluation": False,
    },
    "Enterprise": {
        "reports_per_month": float('inf'), "chat_queries_per_day": float('inf'), "projects_per_year": float('inf'),
        "has_report_generation": True, "has_creative_conversation": True, "has_concept_generation": True, "has_idea_evaluation": True,
    }
}

# ==============================
# CONEXIÓN A SUPABASE
# ==============================
supabase: Client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# Cliente con permisos de administrador
try:
    supabase_admin: Client = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_KEY"]
    )
except KeyError:
    # Mostramos el error solo si el usuario actual es admin, para no afectar a otros
    if st.session_state.get("role") == "admin":
        st.error("Error: SUPABASE_SERVICE_KEY no encontrada en los secrets. El panel de admin no funcionará.")
    # No detenemos la app para usuarios normales
    supabase_admin = None # Define como None si falla


# ==============================
# Funciones de Autenticación
# ==============================

def show_signup_page():
    st.header("Crear Nueva Cuenta")
    email = st.text_input("Tu Correo Electrónico")
    password = st.text_input("Crea una Contraseña", type="password")
    invite_code = st.text_input("Código de Invitación de tu Empresa")

    if st.button("Registrarse"):
        if not email or not password or not invite_code:
            st.error("Por favor, completa todos los campos."); return
        try:
            client_response = supabase.table("clients").select("id").eq("invite_code", invite_code).single().execute()
            if not client_response.data:
                st.error("El código de invitación no es válido."); return
            selected_client_id = client_response.data['id']
            auth_response = supabase.auth.sign_up({
                "email": email, "password": password,
                "options": {"data": {'client_id': selected_client_id}}
            })
            st.success("¡Registro exitoso! Revisa tu correo para confirmar tu cuenta.")
        except Exception as e:
            print(f"----------- ERROR DETALLADO DE REGISTRO -----------\n{e}\n-------------------------------------------------")
            st.error(f"Error en el registro: {e}")

def show_login_page():
    st.header("Iniciar Sesión")
    email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
    password = st.text_input("Contraseña", type="password", placeholder="password")

    if st.button("Ingresar"):
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user_id = response.user.id
            user_profile = supabase.table("users").select("*, clients(client_name, plan), rol").eq("id", user_id).single().execute()
            if user_profile.data and user_profile.data.get('clients'):
                client_info = user_profile.data['clients']
                st.session_state.logged_in = True
                st.session_state.user = user_profile.data['email']
                st.session_state.cliente = client_info['client_name'].lower()
                st.session_state.plan = client_info.get('plan', 'Explorer')
                st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                st.session_state.role = user_profile.data.get('rol', 'user')
                st.rerun()
            else:
                st.error("Perfil de usuario no encontrado o no asociado a un cliente. Contacta al administrador.")
        except Exception as e:
            st.error("Credenciales incorrectas o cuenta no confirmada.")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("¿No tienes cuenta? Regístrate", type="secondary"):
            st.session_state.page = "signup"; st.rerun()
    with col2:
        if st.button("¿Olvidaste tu contraseña?", type="secondary"):
            st.session_state.page = "reset_password"; st.rerun()

def show_reset_password_page():
    st.header("Restablecer Contraseña")
    st.write("Ingresa tu correo electrónico y te enviaremos un enlace para restablecer tu contraseña.")
    email = st.text_input("Tu Correo Electrónico")
    if st.button("Enviar enlace de recuperación"):
        if not email:
            st.warning("Por favor, ingresa tu correo electrónico."); return
        try:
            supabase.auth.reset_password_for_email(email)
            st.success("¡Correo enviado! Revisa tu bandeja de entrada.")
            st.info("Sigue las instrucciones del correo para crear una nueva contraseña.")
        except Exception as e:
            st.error(f"Error al enviar el correo: {e}")

# ==============================
# Funciones de Reseteo de Flujo
# ==============================
def reset_report_workflow():
    for k in ["report", "last_question", "report_question", "personalization", "rating"]:
        st.session_state.pop(k, None)

def reset_chat_workflow():
    st.session_state.pop("chat_history", None)

# ==============================
# Configuración API Gemini
# ==============================
try:
    api_keys = [st.secrets["API_KEY_1"], st.secrets["API_KEY_2"], st.secrets["API_KEY_3"]]
    current_api_key_index = 0
    def configure_api():
        global current_api_key_index
        genai.configure(api_key=api_keys[current_api_key_index])
    configure_api()
    generation_config = {"temperature": 0.5, "top_p": 0.8, "top_k": 32, "max_output_tokens": 8192}
    safety_settings = [
        {"category": c, "threshold": "BLOCK_ONLY_HIGH"} for c in
        ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]
    ]
    def create_model():
        return genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=generation_config, safety_settings=safety_settings)
    model = create_model()
except KeyError as e:
    st.error(f"Error: Falta la clave API de Gemini '{e}' en los secrets.")
    model = None # Define model como None si falla la configuración

def call_gemini_api(prompt):
    if model is None:
        st.error("La API de Gemini no está configurada correctamente.")
        return None
    try:
        response = model.generate_content([prompt])
        return html.unescape(response.text)
    except Exception as e:
        print(f"----------- ERROR DETALLADO DE GEMINI -----------\n{e}\n-----------------------------------------------")
        st.error(f"Error en la llamada a Gemini: {e}.")
        return None

# ==============================
# Rastreo de Uso
# ==============================
def log_query_event(query_text, mode, rating=None):
    try:
        data = {"id": datetime.datetime.now().strftime("%Y%m%d%H%M%S%f"), # Añadido microsegundos para ID único
                "user_name": st.session_state.user,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), # Usar UTC
                "mode": mode, "query": query_text, "rating": rating}
        supabase.table("queries").insert(data).execute()
    except Exception as e:
        print(f"Error al registrar evento: {e}") # Loggear error sin detener la app

def get_monthly_usage(username, action_type):
    try:
        today = datetime.date.today()
        first_day_of_month = today.replace(day=1)
        # Asegurar formato correcto para Supabase (ISO 8601 con zona horaria)
        first_day_iso = datetime.datetime.combine(first_day_of_month, datetime.time.min, tzinfo=datetime.timezone.utc).isoformat()
        response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", first_day_iso).execute()
        return response.count
    except Exception as e:
        print(f"Error al obtener uso mensual: {e}"); return 0

def get_daily_usage(username, action_type):
    try:
        today_start = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", today_start).execute()
        return response.count
    except Exception as e:
        print(f"Error al obtener uso diario: {e}"); return 0

# ==============================
# Funciones Auxiliares y PDF
# ==============================
def normalize_text(text):
    if not text: return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()

def add_markdown_content(pdf, markdown_text):
    # ... (código sin cambios) ...
    html_text = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "tables", "break-on-newline"])
    soup = BeautifulSoup(html_text, "html.parser")
    container = soup.body or soup
    for elem in container.children:
        if elem.name:
            if elem.name.startswith("h"):
                level = int(elem.name[1]) if len(elem.name) > 1 and elem.name[1].isdigit() else 1
                pdf.add_title(elem.get_text(strip=True), level=level)
            elif elem.name == "p": pdf.add_paragraph(elem.decode_contents())
            elif elem.name == "ul":
                for li in elem.find_all("li"): pdf.add_paragraph("• " + li.decode_contents())
            elif elem.name == "ol":
                for idx, li in enumerate(elem.find_all("li"), 1): pdf.add_paragraph(f"{idx}. {li.decode_contents()}")
            else: pdf.add_paragraph(elem.decode_contents())
        else:
            text = elem.string
            if text and text.strip(): pdf.add_paragraph(text)

@st.cache_data(show_spinner=False, ttl=3600) # Añadido TTL para recargar datos cada hora
def load_database(cliente: str):
    try:
        s3 = boto3.client("s3", endpoint_url=st.secrets["S3_ENDPOINT_URL"], aws_access_key_id=st.secrets["S3_ACCESS_KEY"], aws_secret_access_key=st.secrets["S3_SECRET_KEY"])
        response = s3.get_object(Bucket=st.secrets.get("S3_BUCKET"), Key="resultado_presentacion (1).json")
        data = json.loads(response["Body"].read().decode("utf-8"))
        cliente_norm = normalize_text(cliente or "")
        # Simplificado el filtro
        if cliente_norm != "insights-atelier":
            data = [doc for doc in data if cliente_norm in normalize_text(doc.get("cliente", ""))]
        return data
    except Exception as e:
        st.error(f"Error al cargar datos desde S3: {e}")
        return [] # Devuelve lista vacía en caso de error

def extract_brand(filename):
    if not filename or "In-ATL_" not in filename: return ""
    try:
        return filename.split("In-ATL_")[1].rsplit(".", 1)[0]
    except IndexError:
        return "" # Manejo por si el formato no es el esperado

def get_relevant_info(db, question, selected_files):
    # ... (código sin cambios) ...
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"
            for grupo in pres.get("grupos", []):
                all_text += f"Grupo {grupo.get('grupo_index', 'N/A')}: {grupo.get('contenido_texto', '')}\n" # Añadido N/A
                if grupo.get("metadatos"): all_text += f"Metadatos: {json.dumps(grupo.get('metadatos'), ensure_ascii=False, indent=2)}\n" # Indentado para legibilidad
                if grupo.get("hechos"): all_text += f"Hechos: {json.dumps(grupo.get('hechos'), ensure_ascii=False, indent=2)}\n" # Indentado
            all_text += "\n---\n\n"
    return all_text

banner_file = "Banner (2).jpg" # Asegúrate que este archivo exista

def clean_text(text):
    # ... (código sin cambios) ...
    if not isinstance(text, str): text = str(text)
    return text.replace('&', '&amp;')

class PDFReport:
    # ... (código de la clase sin cambios) ...
    def __init__(self, buffer_or_filename, banner_path=None):
        self.banner_path = banner_path
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.doc = SimpleDocTemplate(buffer_or_filename, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=45*mm, bottomMargin=18*mm)
        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Heading1'], alignment=1, spaceAfter=12, fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='CustomHeading', parent=self.styles['Heading2'], spaceBefore=10, spaceAfter=6, fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='CustomBodyText', parent=self.styles['Normal'], leading=14, alignment=4, fontSize=12))
        self.styles.add(ParagraphStyle(name='CustomFooter', parent=self.styles['Normal'], alignment=2, textColor=colors.grey, fontSize=6))
        # Intenta usar la fuente registrada, si falla, usa Helvetica por defecto
        default_font = 'Helvetica'
        try:
             pdfmetrics.getFont('DejaVuSans') # Verifica si existe
             default_font = 'DejaVuSans'
        except KeyError:
             print("Advertencia: Fuente DejaVuSans no registrada para PDF, usando Helvetica.")
        for style_name in ['CustomTitle', 'CustomHeading', 'CustomBodyText', 'CustomFooter']:
             self.styles[style_name].fontName = default_font

    def header(self, canvas, doc):
        canvas.saveState()
        if self.banner_path and os.path.isfile(self.banner_path):
            try:
                img_w, img_h = 210*mm, 35*mm
                y_pos = A4[1] - img_h
                canvas.drawImage(self.banner_path, 0, y_pos, width=img_w, height=img_h, preserveAspectRatio=True, anchor='n')
            except Exception as e: print(f"Error al dibujar header del PDF: {e}") # Log error
        canvas.restoreState()
    def footer(self, canvas, doc):
        canvas.saveState()
        footer_text = "Es posible que se muestre información imprecisa. Verifica las respuestas."
        p = Paragraph(footer_text, self.styles['CustomFooter'])
        w, h = p.wrap(doc.width, doc.bottomMargin)
        p.drawOn(canvas, doc.leftMargin, 3 * mm)
        canvas.restoreState()
    def header_footer(self, canvas, doc):
        self.header(canvas, doc)
        self.footer(canvas, doc)
    def add_paragraph(self, text, style='CustomBodyText'):
        p = Paragraph(clean_text(text), self.styles[style])
        self.elements += [p, Spacer(1, 6)]
    def add_title(self, text, level=1):
        # Usamos CustomHeading para todos los niveles por simplicidad, podrías diferenciar
        p = Paragraph(clean_text(text), self.styles['CustomHeading'])
        self.elements += [p, Spacer(1, 12)]
    def build_pdf(self):
        self.doc.build(self.elements, onFirstPage=self.header_footer, onLaterPages=self.header_footer)

def generate_pdf_html(content, title="Documento Final", banner_path=None):
    try:
        buffer = BytesIO()
        pdf = PDFReport(buffer, banner_path=banner_path)
        pdf.add_title(title, level=1) # Título principal
        add_markdown_content(pdf, content) # Contenido del Markdown
        pdf.build_pdf()
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
    except Exception as e:
        st.error(f"Error al generar el PDF: {e}")
        return None

# =====================================================
# MODOS DE LA APLICACIÓN (Funciones report_mode, etc.)
# =====================================================
# ... (Las funciones generate_final_report, report_mode, grounded_chat_mode, 
#      ideacion_mode, concept_generation_mode, idea_evaluator_mode 
#      permanecen exactamente iguales que en tu último código) ...

# (Incluyo una versión resumida aquí para referencia, usa tus versiones completas)
def generate_final_report(question, db, selected_files):
    # Tu lógica compleja con prompt1 y prompt2...
    st.write("Generando reporte final...") # Placeholder
    relevant_info = get_relevant_info(db, question, selected_files)
    # Simulación de llamada a API
    response = f"## Informe para: {question}\n\nBasado en la información:\n{relevant_info[:500]}..."
    return response

def report_mode(db, selected_files):
    st.markdown("### Generar Reporte de Reportes")
    st.markdown("...") # Tu descripción
    # ... Tu lógica de report_mode ...
    question = st.text_area("Escribe tu consulta para el reporte…", key="report_question")
    if st.button("Generar Reporte"):
        # ... Tus chequeos de límite y pregunta vacía ...
        with st.spinner("Generando informe..."):
            report = generate_final_report(question, db, selected_files) # Usa tu función real
            if report:
                st.session_state["report"] = report
                log_query_event(question, mode="Generar un reporte de reportes")
                st.rerun()
            else: st.error("No se pudo generar el reporte.")
    if "report" in st.session_state:
        st.markdown("### Informe Generado")
        st.markdown(st.session_state["report"])
        # ... Tu lógica de descarga PDF y botón "Nueva Consulta" ...

def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    st.markdown("...") # Tu descripción
    # ... Tu lógica de grounded_chat_mode ...
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    # ... Mostrar historial ...
    user_input = st.text_area("Escribe tu pregunta...")
    if st.button("Enviar Pregunta"):
         # ... Tus chequeos de límite y pregunta vacía ...
         with st.spinner("Buscando..."):
              # response = call_gemini_api(...) # Tu llamada real
              response = f"Respuesta basada en reportes para: {user_input}" # Placeholder
              if response:
                   st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
                   st.session_state.chat_history.append({"role": "Asistente", "message": response})
                   log_query_event(user_input, mode="Chat de Consulta Directa")
                   st.rerun()
              else: st.error("Error al generar respuesta.")
    # ... Tu lógica de descarga PDF y botón "Nueva Conversación" ...


def ideacion_mode(db, selected_files):
    st.subheader("Conversaciones Creativas")
    st.markdown("...") # Tu descripción
    # ... Lógica similar a grounded_chat_mode ...

def concept_generation_mode(db, selected_files):
    st.subheader("Generación de Conceptos")
    st.markdown("...") # Tu descripción
    # ... Tu lógica de concept_generation_mode ...

def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluación de Pre-Ideas")
    st.markdown("...") # Tu descripción
    # ... Tu lógica de idea_evaluator_mode ...


# =====================================================
# FUNCIONES DEL PANEL DE ADMINISTRADOR
# =====================================================
@st.cache_data(ttl=600)
def get_all_clients():
    """Obtiene todos los clientes de la base de datos."""
    try:
        response = supabase.table("clients").select("id, client_name").execute()
        return response.data
    except Exception as e:
        st.error(f"Error al cargar clientes: {e}")
        return []

def show_admin_dashboard():
    st.header("Panel de Administrador")

    # Verifica si el cliente admin se inicializó correctamente
    if supabase_admin is None:
        st.error("La configuración del cliente administrador falló. Revisa los secrets.")
        return

    tab1, tab2 = st.tabs(["✉️ Invitar Nuevo Usuario", "📊 Estadísticas (Próximamente)"])

    with tab1:
        st.subheader("Invitar Nuevo Usuario")
        clients = get_all_clients()
        if not clients:
            st.warning("No se encontraron clientes para asignar.")
        else:
            client_map = {client['client_name']: client['id'] for client in clients}
            with st.form("invite_form"):
                email_to_invite = st.text_input("Correo Electrónico del Invitado")
                selected_client_name = st.selectbox("Asignar al Cliente:", client_map.keys())
                submitted = st.form_submit_button("Enviar Invitación")

            if submitted:
                if not email_to_invite or not selected_client_name:
                    st.warning("Por favor, completa todos los campos.")
                else:
                    selected_client_id = client_map[selected_client_name]
                    try:
                        st.info(f"Enviando invitación a {email_to_invite}...")
                        supabase_admin.auth.admin.invite_user_by_email(
                            email_to_invite,
                            options={"data": {'client_id': selected_client_id}}
                        )
                        st.success(f"¡Invitación enviada exitosamente a {email_to_invite}!")
                        st.info("El usuario recibirá un correo para establecer su contraseña.")
                    except Exception as e:
                        st.error(f"Error al enviar la invitación: {e}")
                        st.error("Verifica que el usuario no exista ya.")

    with tab2:
        st.subheader("Estadísticas de Uso")
        st.info("Esta sección está en desarrollo.")

# =====================================================
# FUNCIÓN PRINCIPAL DE LA APLICACIÓN (CON PESTAÑAS SUPERIORES PARA ADMIN)
# =====================================================
def main():
    if 'page' not in st.session_state:
        st.session_state.page = "login"

    footer_text = "Atelier Consultoría y Estrategia S.A.S - Todos los Derechos Reservados 2025"
    footer_html = f"<div style='text-align: center; color: gray; font-size: 12px;'>{footer_text}</div>"

    if not st.session_state.get("logged_in"):
        # --- Interfaz de Login/Signup/Reset ---
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.image("LogoDataStudio.png") # Asumiendo que existe el logo
            if st.session_state.page == "login":
                show_login_page()
            elif st.session_state.page == "signup":
                show_signup_page()
                if st.button("¿Ya tienes cuenta? Inicia Sesión"):
                    st.session_state.page = "login"; st.rerun()
            elif st.session_state.page == "reset_password":
                show_reset_password_page()
                if st.button("Volver a Iniciar Sesión"):
                    st.session_state.page = "login"; st.rerun()
        st.divider()
        st.markdown(footer_html, unsafe_allow_html=True)
        st.stop()

    # --- Usuario Logueado ---

    # Función interna para renderizar la UI de usuario normal
    def render_user_interface():
        st.sidebar.image("LogoDataStudio.png")
        st.sidebar.write(f"Usuario: {st.session_state.user}")
        st.sidebar.divider()
        
        try:
            # Usamos cache_data para db_full también para evitar recargas constantes
            @st.cache_data(ttl=3600)
            def get_full_db(cliente):
                 return load_database(cliente)
            db_full = get_full_db(st.session_state.cliente)
        except Exception as e:
            st.error(f"Error crítico al cargar la base de datos: {e}"); st.stop()
        
        db_filtered = db_full[:] # Copia para filtrar
        user_features = st.session_state.plan_features
        
        # --- Lista de Modos Regulares ---
        regular_modes = ["Chat de Consulta Directa"]
        if user_features.get("has_report_generation"): regular_modes.insert(0, "Generar un reporte de reportes")
        if user_features.get("has_creative_conversation"): regular_modes.append("Conversaciones creativas")
        if user_features.get("has_concept_generation"): regular_modes.append("Generación de conceptos")
        if user_features.get("has_idea_evaluation"): regular_modes.append("Evaluar una idea")

        st.sidebar.header("Seleccione el modo de uso")

        # Asegura que el modo actual sea válido o establece default
        current_mode = st.session_state.get('current_mode')
        if current_mode not in regular_modes:
             current_mode = regular_modes[0]
             st.session_state.current_mode = current_mode 

        # Callback para cambio de modo
        def mode_changed():
             new_mode = st.session_state.main_mode_radio 
             # Solo resetea si el modo realmente cambió
             if st.session_state.current_mode != new_mode:
                 st.session_state.current_mode = new_mode
                 reset_chat_workflow()
                 st.session_state.pop("generated_concept", None)
                 st.session_state.pop("evaluation_result", None)
                 reset_report_workflow()
        
        # Radio único para modos regulares
        selected_mode = st.sidebar.radio(
            "Modos:", 
            regular_modes, 
            key="main_mode_radio", 
            label_visibility="collapsed",
            index=regular_modes.index(current_mode),
            on_change=mode_changed
        )
        
        modo = selected_mode 

        # --- Sidebar: Filtros ---
        st.sidebar.header("Filtros de Búsqueda")
        marcas_options = sorted({doc.get("filtro", "") for doc in db_full if doc.get("filtro")})
        selected_marcas = st.sidebar.multiselect("Seleccione la(s) marca(s):", marcas_options)
        if selected_marcas:
            db_filtered = [d for d in db_filtered if d.get("filtro") in selected_marcas]

        years_options = sorted({str(doc.get("marca", "")) for doc in db_full if doc.get("marca")}) # Convertido a str por si acaso
        selected_years = st.sidebar.multiselect("Seleccione el/los año(s):", years_options)
        if selected_years:
            db_filtered = [d for d in db_filtered if str(d.get("marca", "")) in selected_years]

        brands_options = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_filtered if d.get("nombre_archivo")})
        selected_brands = st.sidebar.multiselect("Seleccione el/los proyecto(s):", brands_options)
        if selected_brands:
            db_filtered = [d for d in db_filtered if extract_brand(d.get("nombre_archivo", "")) in selected_brands]

        # --- Sidebar: Inferior ---
        if st.sidebar.button("Cerrar Sesión", key="logout_main"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()

        st.sidebar.divider()
        st.sidebar.markdown(footer_html, unsafe_allow_html=True)

        # --- Renderizado Principal ---
        selected_files = [d.get("nombre_archivo") for d in db_filtered]

        if modo == "Generar un reporte de reportes": report_mode(db_filtered, selected_files)
        elif modo == "Conversaciones creativas": ideacion_mode(db_filtered, selected_files)
        elif modo == "Generación de conceptos": concept_generation_mode(db_filtered, selected_files)
        elif modo == "Chat de Consulta Directa": grounded_chat_mode(db_filtered, selected_files)
        elif modo == "Evaluar una idea": idea_evaluator_mode(db_filtered, selected_files)

    # --- Lógica Principal de Main: Tabs Condicionales ---
    is_admin = st.session_state.get("role") == "admin"

    if is_admin:
        tab_user, tab_admin = st.tabs(["Interfaz de Usuario", "Panel de Administrador"])
        with tab_user:
            render_user_interface() 
        with tab_admin:
            show_admin_dashboard()
            # Footer opcional en pestaña admin
            # st.divider()
            # st.markdown(footer_html, unsafe_allow_html=True)
    else:
        render_user_interface()
        
if __name__ == "__main__":
    main()
