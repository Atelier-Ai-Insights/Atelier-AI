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

### ¡NUEVO! - Cliente con permisos de administrador ###
try:
    supabase_admin: Client = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_KEY"]
    )
except KeyError:
    # Mostramos el error solo si el usuario actual es admin, para no afectar a otros
    # Usamos st.cache_data para evitar mostrar el error repetidamente en reruns
    @st.cache_data
    def show_admin_key_error():
        st.error("Error: SUPABASE_SERVICE_KEY no encontrada en los secrets. El panel de admin no funcionará.")
    
    # Verificamos el rol ANTES de mostrar el error
    # Necesitamos una forma inicial de obtener el rol o asumirlo si no está logueado aún
    # Esta parte es compleja porque el rol se define DESPUÉS del login.
    # Por ahora, simplemente definimos supabase_admin como None y chequearemos dentro de show_admin_dashboard
    supabase_admin = None

# ==============================
# Funciones de Autenticación
# ==============================

def show_signup_page():
    # ... (Tu código show_signup_page sin cambios) ...
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
    # --- ¡MODIFICADO! Asegura que lee 'rol' ---
    st.header("Iniciar Sesión")
    email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
    password = st.text_input("Contraseña", type="password", placeholder="password")

    if st.button("Ingresar"):
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user_id = response.user.id
            # Asegúrate que tu tabla 'users' tenga la columna 'rol'
            user_profile = supabase.table("users").select("*, clients(client_name, plan), rol").eq("id", user_id).single().execute()
            
            if user_profile.data and user_profile.data.get('clients'):
                client_info = user_profile.data['clients']
                st.session_state.logged_in = True
                st.session_state.user = user_profile.data.get('email', email) # Usa email como fallback
                st.session_state.cliente = client_info['client_name'].lower()
                st.session_state.plan = client_info.get('plan', 'Explorer')
                st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                # Guarda el rol correctamente
                st.session_state.role = user_profile.data.get('rol', 'user') 
                st.rerun()
            else:
                 # Mensaje más específico si falta la asociación cliente-usuario
                 if user_profile.data and not user_profile.data.get('clients'):
                      st.error("Usuario autenticado pero no asociado a un cliente. Contacta al administrador.")
                 else: # Error genérico si no se encuentra el perfil en 'users'
                      st.error("Perfil de usuario no encontrado en la base de datos. Contacta al administrador.")
        except Exception as e:
            # Distinguir errores de Supabase Auth de otros errores
            if "invalid login credentials" in str(e).lower() or "email not confirmed" in str(e).lower():
                 st.error("Credenciales incorrectas o cuenta no confirmada.")
            else:
                 st.error(f"Error inesperado al iniciar sesión: {e}")
                 print(f"----------- ERROR DETALLADO DE LOGIN -----------\n{e}\n-----------------------------------------------")


    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("¿No tienes cuenta? Regístrate", type="secondary"):
            st.session_state.page = "signup"; st.rerun()
    with col2:
        if st.button("¿Olvidaste tu contraseña?", type="secondary"):
            st.session_state.page = "reset_password"; st.rerun()

def show_reset_password_page():
    # ... (Tu código show_reset_password_page sin cambios) ...
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
    model = None

def call_gemini_api(prompt):
    # ... (Tu código call_gemini_api sin cambios) ...
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
# ... (Tus funciones log_query_event, get_monthly_usage, get_daily_usage sin cambios,
#      pero considera añadir manejo de errores como en el ejemplo anterior) ...
def log_query_event(query_text, mode, rating=None):
    try:
        data = {"id": datetime.datetime.now().strftime("%Y%m%d%H%M%S%f"), 
                "user_name": st.session_state.user,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), 
                "mode": mode, "query": query_text, "rating": rating}
        supabase.table("queries").insert(data).execute()
    except Exception as e:
        print(f"Error al registrar evento: {e}") 

def get_monthly_usage(username, action_type):
    try:
        today = datetime.date.today()
        first_day_of_month = today.replace(day=1)
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
# ... (Tus funciones normalize_text, add_markdown_content, load_database,
#      extract_brand, get_relevant_info, clean_text, PDFReport, generate_pdf_html
#      sin cambios funcionales, pero considera añadir manejo de errores/logs) ...

def normalize_text(text):
    if not text: return ""
    try:
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()
    except Exception as e:
        print(f"Error normalizando texto '{text[:50]}...': {e}")
        return str(text).lower() # Fallback a conversión simple

def add_markdown_content(pdf, markdown_text):
    try:
        html_text = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "tables", "break-on-newline"])
        soup = BeautifulSoup(html_text, "html.parser")
        container = soup.body or soup
        for elem in container.children:
            if elem.name:
                if elem.name.startswith("h"):
                    level = int(elem.name[1]) if len(elem.name) > 1 and elem.name[1].isdigit() else 1
                    pdf.add_title(elem.get_text(strip=True), level=level)
                elif elem.name == "p": pdf.add_paragraph(elem.decode_contents(formatter="html")) # Usar formatter html
                elif elem.name == "ul":
                    for li in elem.find_all("li"): pdf.add_paragraph("• " + li.decode_contents(formatter="html"))
                elif elem.name == "ol":
                    for idx, li in enumerate(elem.find_all("li"), 1): pdf.add_paragraph(f"{idx}. {li.decode_contents(formatter="html")}")
                else: # Manejo genérico para otros tags
                     pdf.add_paragraph(elem.decode_contents(formatter="html"))
            else:
                text = elem.string
                if text and text.strip(): pdf.add_paragraph(text.strip())
    except Exception as e:
        print(f"Error procesando Markdown para PDF: {e}")
        pdf.add_paragraph(f"Error al procesar contenido: {e}") # Añade error al PDF

@st.cache_data(show_spinner=False, ttl=3600) 
def load_database(cliente: str):
    try:
        s3 = boto3.client("s3", endpoint_url=st.secrets["S3_ENDPOINT_URL"], aws_access_key_id=st.secrets["S3_ACCESS_KEY"], aws_secret_access_key=st.secrets["S3_SECRET_KEY"])
        response = s3.get_object(Bucket=st.secrets.get("S3_BUCKET"), Key="resultado_presentacion (1).json")
        data = json.loads(response["Body"].read().decode("utf-8"))
        cliente_norm = normalize_text(cliente or "")
        if cliente_norm != "insights-atelier":
             # Filtro mejorado: Comprueba si cliente_norm está en la lista de clientes del doc (si existe)
             data = [doc for doc in data 
                     if cliente_norm in [normalize_text(c) for c in doc.get("cliente", []) if isinstance(doc.get("cliente"), list)] or 
                     cliente_norm == normalize_text(doc.get("cliente", "")) # Soporte para string simple
                    ]
        return data
    except Exception as e:
        st.error(f"Error al cargar datos desde S3: {e}")
        return [] 

def extract_brand(filename):
    if not filename or "In-ATL_" not in filename: return ""
    try:
        # Asegura que partimos desde el último In-ATL_ si hubiera varios
        parts = filename.split("In-ATL_")
        if len(parts) > 1:
             # Toma la última parte y quita la extensión
             return parts[-1].rsplit(".", 1)[0]
        else:
             return ""
    except Exception as e:
        print(f"Error extrayendo marca de '{filename}': {e}")
        return ""

def get_relevant_info(db, question, selected_files):
    all_text = ""
    if not isinstance(selected_files, list): 
        print(f"Advertencia: selected_files no es una lista ({type(selected_files)}).")
        return "" # Evita errores si selected_files no es iterable
    
    selected_files_set = set(selected_files) # Más eficiente para búsquedas

    for pres in db:
        archivo = pres.get("nombre_archivo")
        if archivo and archivo in selected_files_set:
            titulo = pres.get('titulo_estudio', archivo) # Usa archivo como fallback
            all_text += f"Documento: {titulo}\n"
            for grupo in pres.get("grupos", []):
                grupo_idx = grupo.get('grupo_index', 'N/A')
                contenido = grupo.get('contenido_texto', '').strip()
                if contenido: # Solo añade si hay contenido
                     all_text += f"Grupo {grupo_idx}: {contenido}\n"
                # Añade metadatos y hechos si existen, con formato más legible
                if grupo.get("metadatos"): all_text += f"  Metadatos: {json.dumps(grupo.get('metadatos'), ensure_ascii=False, indent=2)}\n"
                if grupo.get("hechos"): all_text += f"  Hechos: {json.dumps(grupo.get('hechos'), ensure_ascii=False, indent=2)}\n"
            all_text += "\n---\n\n"
    return all_text

banner_file = "Banner (2).jpg" 

def clean_text(text):
    if not isinstance(text, str): text = str(text)
    # Escapa caracteres HTML básicos
    return html.escape(text, quote=True) 

class PDFReport:
    # ... (Sin cambios funcionales, solo ajustes menores de robustez) ...
    def __init__(self, buffer_or_filename, banner_path=None):
        self.banner_path = banner_path
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.doc = SimpleDocTemplate(buffer_or_filename, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=45*mm, bottomMargin=18*mm)
        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Heading1'], alignment=1, spaceAfter=12, fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='CustomHeading', parent=self.styles['Heading2'], spaceBefore=10, spaceAfter=6, fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='CustomBodyText', parent=self.styles['Normal'], leading=14, alignment=4, fontSize=12)) # Alignment 4 = Justificado
        self.styles.add(ParagraphStyle(name='CustomFooter', parent=self.styles['Normal'], alignment=2, textColor=colors.grey, fontSize=6))
        default_font = 'Helvetica'
        try:
             pdfmetrics.getFont('DejaVuSans') 
             default_font = 'DejaVuSans'
        except KeyError:
             print("Advertencia: Fuente DejaVuSans no registrada para PDF, usando Helvetica.")
        for style_name in ['CustomTitle', 'CustomHeading', 'CustomBodyText', 'CustomFooter']:
             self.styles[style_name].fontName = default_font

    def header(self, canvas, doc):
        canvas.saveState()
        if self.banner_path and os.path.isfile(self.banner_path):
            try:
                # Ajusta tamaño y posición si es necesario
                img_w, img_h = 210*mm, 30*mm # Altura reducida
                y_pos = A4[1] - img_h - 5*mm # Baja un poco
                canvas.drawImage(self.banner_path, 0, y_pos, width=img_w, height=img_h, 
                                 preserveAspectRatio=True, anchor='n')
            except Exception as e: print(f"Error al dibujar header del PDF: {e}") 
        canvas.restoreState()
    def footer(self, canvas, doc):
        canvas.saveState()
        footer_text = "Atelier Consultoría y Estrategia S.A.S - Todos los Derechos Reservados 2025. Es posible que se muestre información imprecisa. Verifica las respuestas."
        p = Paragraph(footer_text, self.styles['CustomFooter'])
        w, h = p.wrap(doc.width, doc.bottomMargin)
        p.drawOn(canvas, doc.leftMargin, 3 * mm)
        canvas.restoreState()
    def header_footer(self, canvas, doc):
        self.header(canvas, doc)
        self.footer(canvas, doc)
    def add_paragraph(self, text, style='CustomBodyText'):
        # Maneja texto vacío o None
        text_to_add = clean_text(text) if text else ""
        if text_to_add.strip(): # Solo añade si no está vacío después de limpiar
            p = Paragraph(text_to_add, self.styles[style])
            self.elements += [p, Spacer(1, 4)] # Reducir espacio
    def add_title(self, text, level=1):
        text_to_add = clean_text(text) if text else ""
        if text_to_add.strip():
            # Podrías diferenciar estilos por nivel si quieres
            style_name = 'CustomHeading' # Usamos el mismo para todos
            p = Paragraph(text_to_add, self.styles[style_name])
            self.elements += [p, Spacer(1, 8)] # Reducir espacio
    def build_pdf(self):
        try:
             self.doc.build(self.elements, onFirstPage=self.header_footer, onLaterPages=self.header_footer)
        except Exception as e:
             print(f"Error construyendo PDF: {e}")
             # Intenta construir con elementos simples si falla
             try:
                  simple_elements = [Paragraph(f"Error al generar PDF: {e}", getSampleStyleSheet()['Normal'])]
                  self.doc.build(simple_elements)
             except: pass # Falla final


def generate_pdf_html(content, title="Documento Final", banner_path=None):
    if not content: return None # No generar PDF si no hay contenido
    try:
        buffer = BytesIO()
        pdf = PDFReport(buffer, banner_path=banner_path)
        pdf.add_title(title, level=1) 
        add_markdown_content(pdf, content) 
        pdf.build_pdf()
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
    except Exception as e:
        st.error(f"Error crítico al generar el PDF: {e}")
        print(f"Error generando PDF: {e}")
        return None


# =====================================================
# MODOS DE LA APLICACIÓN (Placeholders - Usa tus funciones reales)
# =====================================================
def generate_final_report(question, db, selected_files):
    st.write(f"Ejecutando `generate_final_report` para: {question}") # Log
    # ... (Tu lógica real) ...
    return f"Informe simulado para '{question}'"

def report_mode(db, selected_files):
    # ... (Tu código `report_mode` sin cambios funcionales) ...
    st.markdown("### Generar Reporte de Reportes")
    st.markdown("...") 
    question = st.text_area("...", key="report_question")
    if st.button("Generar Reporte"):
        #... checks ...
        with st.spinner("..."): report = generate_final_report(question, db, selected_files)
        #...
    #...

def grounded_chat_mode(db, selected_files):
    # ... (Tu código `grounded_chat_mode` sin cambios funcionales) ...
    st.subheader("Chat de Consulta Directa")
    st.markdown("...")
    #...
    user_input = st.text_area("...")
    if st.button("Enviar Pregunta"):
        #... checks ...
        with st.spinner("..."): response = call_gemini_api("...") # Placeholder
        #...
    #...

def ideacion_mode(db, selected_files):
    # ... (Tu código `ideacion_mode` sin cambios funcionales) ...
    st.subheader("Conversaciones Creativas")
    #...

def concept_generation_mode(db, selected_files):
    # ... (Tu código `concept_generation_mode` sin cambios funcionales) ...
    st.subheader("Generación de Conceptos")
    #...

def idea_evaluator_mode(db, selected_files):
    # ... (Tu código `idea_evaluator_mode` sin cambios funcionales) ...
    st.subheader("Evaluación de Pre-Ideas")
    #...

# =====================================================
# ### ¡NUEVO! FUNCIONES DEL PANEL DE ADMINISTRADOR ###
# =====================================================
@st.cache_data(ttl=600)
def get_all_clients():
    """Obtiene todos los clientes de la base de datos."""
    try:
        response = supabase.table("clients").select("id, client_name").execute()
        return response.data if response.data else [] # Asegura devolver lista
    except Exception as e:
        st.error(f"Error al cargar clientes: {e}")
        return []

def show_admin_dashboard():
    st.header("Panel de Administrador")

    # Verifica si el cliente admin se inicializó correctamente
    if supabase_admin is None:
        # Intenta mostrar el error cacheado si existe
        if 'show_admin_key_error' in globals(): show_admin_key_error()
        else: st.error("La configuración del cliente administrador (supabase_admin) falló.")
        st.warning("Asegúrate de que SUPABASE_SERVICE_KEY esté en tus secrets.")
        return # No continuar si no hay cliente admin

    tab1, tab2 = st.tabs(["✉️ Invitar Nuevo Usuario", "📊 Estadísticas (Próximamente)"])

    with tab1:
        st.subheader("Invitar Nuevo Usuario")
        clients = get_all_clients()
        if not clients:
            st.warning("No se encontraron clientes para asignar. Añade clientes en la base de datos primero.")
        else:
            client_map = {client['client_name']: client['id'] for client in clients}
            with st.form("invite_form"):
                email_to_invite = st.text_input("Correo Electrónico del Invitado")
                # Asegura que client_map no esté vacío antes de acceder a keys
                client_keys = list(client_map.keys()) if client_map else []
                selected_client_name = st.selectbox("Asignar al Cliente:", client_keys)
                submitted = st.form_submit_button("Enviar Invitación")

            if submitted:
                if not email_to_invite or not selected_client_name:
                    st.warning("Por favor, completa todos los campos.")
                else:
                    selected_client_id = client_map.get(selected_client_name) # Usa get para seguridad
                    if not selected_client_id:
                         st.error("Cliente seleccionado no válido.")
                    else:
                         try:
                             st.info(f"Enviando invitación a {email_to_invite}...")
                             # Llama a la función de admin para invitar
                             supabase_admin.auth.admin.invite_user_by_email(
                                 email_to_invite,
                                 options={"data": {'client_id': selected_client_id}} # Pasa client_id para el trigger
                             )
                             st.success(f"¡Invitación enviada exitosamente a {email_to_invite}!")
                             st.info("El usuario recibirá un correo para establecer su contraseña.")
                         except Exception as e:
                             st.error(f"Error al enviar la invitación: {e}")
                             st.error("Verifica que el usuario no exista ya y que la SERVICE_KEY sea correcta.")

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

    # --- Interfaz de Login/Signup/Reset ---
    if not st.session_state.get("logged_in"):
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            try:
                # Intenta mostrar el logo, si falla no detiene la app
                st.image("LogoDataStudio.png") 
            except Exception as img_err:
                print(f"Advertencia: No se pudo cargar LogoDataStudio.png: {img_err}")

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
    
    # Define la función interna para renderizar la UI de usuario normal
    def render_user_interface():
        # --- Sidebar: Sección Superior ---
        try:
            st.sidebar.image("LogoDataStudio.png")
        except Exception as img_err:
            print(f"Advertencia: No se pudo cargar LogoDataStudio.png en sidebar: {img_err}")
        st.sidebar.write(f"Usuario: {st.session_state.user}")
        st.sidebar.divider()
        
        # --- Carga de Datos ---
        try:
            # Usamos cache_data para db_full
            @st.cache_data(ttl=3600)
            def get_full_db(cliente):
                 # Añade manejo de errores dentro de load_database
                 db = load_database(cliente)
                 if not db:
                     st.sidebar.warning("No se encontraron datos para este cliente o hubo un error al cargar.")
                 return db
            db_full = get_full_db(st.session_state.cliente)
            if not db_full: # Si db_full está vacío después de cargar
                 st.warning("No hay datos disponibles para mostrar.")
                 # Decide si detener o continuar con funcionalidad limitada
                 # st.stop() 
        except Exception as e:
            st.error(f"Error crítico al preparar la base de datos: {e}"); st.stop()
        
        db_filtered = list(db_full) # Asegura que sea una lista mutable
        user_features = st.session_state.plan_features
        
        # --- Lista de Modos Regulares ---
        regular_modes = ["Chat de Consulta Directa"]
        if user_features.get("has_report_generation"): regular_modes.insert(0, "Generar un reporte de reportes")
        if user_features.get("has_creative_conversation"): regular_modes.append("Conversaciones creativas")
        if user_features.get("has_concept_generation"): regular_modes.append("Generación de conceptos")
        if user_features.get("has_idea_evaluation"): regular_modes.append("Evaluar una idea")

        st.sidebar.header("Seleccione el modo de uso")

        # --- Selección de Modo (Radio Único) ---
        current_mode = st.session_state.get('current_mode')
        # Verifica si el modo actual es válido DENTRO de los modos disponibles AHORA
        if current_mode not in regular_modes:
             current_mode = regular_modes[0] # Default al primero disponible
             st.session_state.current_mode = current_mode 

        # Callback simple para actualizar el estado
        def mode_changed_callback():
             st.session_state.current_mode = st.session_state.main_mode_radio_key # Actualiza con el valor del radio
             # Los reseteos ahora se manejan después del renderizado del radio
        
        # Encuentra el índice actual
        try:
             current_index = regular_modes.index(current_mode)
        except ValueError:
             current_index = 0 # Fallback al primer índice si no se encuentra

        selected_mode = st.sidebar.radio(
            "Modos:", 
            regular_modes, 
            key="main_mode_radio_key", # Key única
            label_visibility="collapsed",
            index=current_index,
            on_change=mode_changed_callback 
        )
        
        # Comprueba si el modo cambió DESPUÉS de renderizar el radio
        if 'last_rendered_mode' not in st.session_state: st.session_state.last_rendered_mode = None
        if st.session_state.last_rendered_mode != selected_mode:
             # Resetea los flujos si el modo cambió
             reset_chat_workflow()
             st.session_state.pop("generated_concept", None)
             st.session_state.pop("evaluation_result", None)
             reset_report_workflow()
             st.session_state.last_rendered_mode = selected_mode # Actualiza el último modo renderizado
             # st.rerun() # Considera si es necesario un rerun aquí

        modo = selected_mode # El modo a usar es el seleccionado actualmente

        # --- Sidebar: Filtros ---
        st.sidebar.header("Filtros de Búsqueda")
        
        # Opciones basadas en la base de datos COMPLETA (db_full)
        marcas_options = sorted({doc.get("filtro", "") for doc in db_full if doc.get("filtro")})
        selected_marcas = st.sidebar.multiselect("Marca(s):", marcas_options, key="filter_marcas")
        
        years_options = sorted({str(doc.get("marca", "")) for doc in db_full if doc.get("marca")}) 
        selected_years = st.sidebar.multiselect("Año(s):", years_options, key="filter_years")

        # Filtra la base de datos AHORA basado en selecciones
        if selected_marcas:
            db_filtered = [d for d in db_filtered if d.get("filtro") in selected_marcas]
        if selected_years:
            db_filtered = [d for d in db_filtered if str(d.get("marca", "")) in selected_years]

        # Opciones de proyectos basadas en la base de datos YA FILTRADA
        brands_options = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_filtered if d.get("nombre_archivo")})
        selected_brands = st.sidebar.multiselect("Proyecto(s):", brands_options, key="filter_projects")
        
        # Filtra de nuevo por proyectos seleccionados
        if selected_brands:
            db_filtered = [d for d in db_filtered if extract_brand(d.get("nombre_archivo", "")) in selected_brands]

        # --- Sidebar: Inferior ---
        if st.sidebar.button("Cerrar Sesión", key="logout_main"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()

        st.sidebar.divider()
        st.sidebar.markdown(footer_html, unsafe_allow_html=True)

        # --- Renderizado Principal del Contenido del Modo ---
        selected_files = [d.get("nombre_archivo") for d in db_filtered if d.get("nombre_archivo")] # Asegura que no haya None

        # Muestra un mensaje si no hay archivos seleccionados/filtrados
        if not selected_files and (selected_marcas or selected_years or selected_brands):
             st.warning("No se encontraron proyectos que coincidan con los filtros seleccionados.")
        elif not db_filtered: # Si la base filtrada está vacía por otras razones
             st.info("No hay datos disponibles para el modo seleccionado con los filtros actuales.")
        else:
             # Llama a la función del modo correspondiente
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
            st.divider()
            st.markdown(footer_html, unsafe_allow_html=True)
    else:
        # Si no es admin, renderiza la interfaz normal directamente
        render_user_interface()
        
if __name__ == "__main__":
    main()
