import datetime
import html
import json
import unicodedata
from io import BytesIO
from PIL import Image
import os
from bs4 import BeautifulSoup

import boto3
import google.generativeai as genai
import markdown2
import streamlit as st
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from supabase import create_client, Client
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

import streamlit as st

hide_st_style = """
    <style>
    /* Oculta el menú de hamburguesa */
    #MainMenu {visibility: hidden;}

    /* Oculta el encabezado de la app */
    header {visibility: hidden;}

    /* Oculta el "Made with Streamlit" footer */
    footer {visibility: hidden;}

    /* Oculta la barra de estado inferior (iconos) */
    [data-testid="stStatusWidget"] {visibility: hidden;}
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# Registrar fuente Unicode para tildes/ñ
FONT_REGISTERED = False
FONT_NAME = 'DejaVuSans'
FALLBACK_FONT_NAME = 'Helvetica' # Fuente por defecto de ReportLab
try:
    # Asegúrate que 'DejaVuSans.ttf' está en tu repositorio o es accesible
    pdfmetrics.registerFont(TTFont(FONT_NAME, 'DejaVuSans.ttf'))
    FONT_REGISTERED = True
    print(f"INFO: Fuente '{FONT_NAME}' registrada correctamente para PDF.")
except Exception as e:
    st.sidebar.warning(f"Advertencia PDF: No se encontró '{FONT_NAME}.ttf'. Caracteres especiales podrían no mostrarse. Usando '{FALLBACK_FONT_NAME}'. Error: {e}")
    FONT_NAME = FALLBACK_FONT_NAME # Usar fallback si falla el registro

# ==============================
# DEFINICIÓN DE PLANES Y PERMISOS
# ==============================

PLAN_FEATURES = {
    "Explorer": {
        "reports_per_month": 0, "chat_queries_per_day": 4, "projects_per_year": 2,
        "has_report_generation": False, "has_creative_conversation": False,
        "has_concept_generation": False, "has_idea_evaluation": False,
        "has_image_evaluation": False, 
    },
    "Strategist": {
        "reports_per_month": 0, "chat_queries_per_day": float('inf'), "projects_per_year": 10,
        "has_report_generation": False, "has_creative_conversation": True,
        "has_concept_generation": True, "has_idea_evaluation": False,
        "has_image_evaluation": False,
    },
    "Enterprise": {
        "reports_per_month": float('inf'), "chat_queries_per_day": float('inf'), "projects_per_year": float('inf'),
        "has_report_generation": True, "has_creative_conversation": True,
        "has_concept_generation": True, "has_idea_evaluation": True,
        "has_image_evaluation": True, 
    }
}

# ==============================
# CONEXIÓN A SUPABASE
# ==============================
supabase: Client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# ==============================
# Autenticación con Supabase Auth (Botones ajustados)
# ==============================

def show_signup_page():
    st.header("Crear Nueva Cuenta")
    email = st.text_input("Tu Correo Electrónico")
    password = st.text_input("Crea una Contraseña", type="password")
    invite_code = st.text_input("Código de Invitación de tu Empresa")

    if st.button("Registrarse", use_container_width=True):
        if not email or not password or not invite_code:
            st.error("Por favor, completa todos los campos.")
            return

        try:
            client_response = supabase.table("clients").select("id").eq("invite_code", invite_code).single().execute()
            if not client_response.data:
                st.error("El código de invitación no es válido.")
                return
            selected_client_id = client_response.data['id']
            auth_response = supabase.auth.sign_up({
                "email": email, "password": password,
                "options": { "data": { 'client_id': selected_client_id } }
            })
            st.success("¡Registro exitoso! Revisa tu correo para confirmar tu cuenta.")
        except Exception as e:
            print(f"----------- ERROR DETALLADO DE REGISTRO -----------\n{e}\n-------------------------------------------------")
            st.error(f"Error en el registro: {e}")

    if st.button("¿Ya tienes cuenta? Inicia Sesión", type="secondary", use_container_width=True):
         st.session_state.page = "login"
         st.rerun()


def show_login_page():
    st.header("Iniciar Sesión")
    email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
    password = st.text_input("Contraseña", type="password", placeholder="password")

    if st.button("Ingresar", use_container_width=True):
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user_id = response.user.id
            user_profile = supabase.table("users").select("*, rol, clients(client_name, plan)").eq("id", user_id).single().execute()
            if user_profile.data and user_profile.data.get('clients'):
                client_info = user_profile.data['clients']
                st.session_state.logged_in = True
                st.session_state.user = user_profile.data['email']
                st.session_state.cliente = client_info['client_name'].lower()
                st.session_state.plan = client_info.get('plan', 'Explorer')
                st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                st.session_state.is_admin = (user_profile.data.get('rol', '') == 'admin')
                st.rerun()
            else:
                st.error("Perfil de usuario no encontrado. Contacta al administrador.")
        except Exception as e:
            st.error("Credenciales incorrectas o cuenta no confirmada.")

    # Apilar botones verticalmente (divisor eliminado)
    if st.button("¿No tienes cuenta? Regístrate", type="secondary", use_container_width=True):
        st.session_state.page = "signup"
        st.rerun()

    if st.button("¿Olvidaste tu contraseña?", type="secondary", use_container_width=True):
        st.session_state.page = "reset_password"
        st.rerun()


def show_reset_password_page():
    st.header("Restablecer Contraseña")
    st.write("Ingresa tu correo electrónico y te enviaremos un enlace para restablecer tu contraseña.")
    email = st.text_input("Tu Correo Electrónico")

    if st.button("Enviar enlace de recuperación", use_container_width=True):
        if not email:
            st.warning("Por favor, ingresa tu correo electrónico.")
            return

        try:
            supabase.auth.reset_password_for_email(email)
            st.success("¡Correo enviado! Revisa tu bandeja de entrada.")
            st.info("Sigue las instrucciones del correo para crear una nueva contraseña. Una vez creada, podrás iniciar sesión.")
        except Exception as e:
            st.error(f"Error al enviar el correo: {e}")

    if st.button("Volver a Iniciar Sesión", type="secondary", use_container_width=True):
         st.session_state.page = "login"
         st.rerun()

# ==============================
# Funciones de Reset
# ==============================
def reset_report_workflow():
    for k in ["report", "last_question", "report_question", "personalization", "rating"]:
        st.session_state.pop(k, None)

def reset_chat_workflow():
    st.session_state.pop("chat_history", None)

# ==============================
# CONFIGURACIÓN DE LA API DE GEMINI (CON ROTACIÓN)
# ==============================
api_keys = [st.secrets["API_KEY_1"], st.secrets["API_KEY_2"], st.secrets["API_KEY_3"]]

if "api_key_index" not in st.session_state:
    st.session_state.api_key_index = 0

def configure_api_dynamically():
    """Configura Gemini con la API key actual y rota el índice para la próxima llamada."""
    global api_keys
    index = st.session_state.api_key_index
    try:
        api_key = api_keys[index]
        genai.configure(api_key=api_key)
        st.session_state.api_key_index = (index + 1) % len(api_keys)
        print(f"INFO: Usando API Key #{index + 1}")
    except IndexError:
        st.error(f"Error: Índice de API Key ({index}) fuera de rango. Verifica tus secretos.")
    except Exception as e:
         st.error(f"Error configurando API Key #{index + 1}: {e}")

generation_config = {"temperature": 0.5, "top_p": 0.8, "top_k": 32, "max_output_tokens": 8192}
safety_settings = [
    {"category": c, "threshold": "BLOCK_ONLY_HIGH"} for c in
    ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]
]

model = genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=generation_config, safety_settings=safety_settings)

def call_gemini_api(prompt):
    configure_api_dynamically()
    try:
        response = model.generate_content([prompt])
        # Usar html.unescape para decodificar entidades HTML como &oacute;
        return html.unescape(response.text)
    except Exception as e:
        print(f"----------- ERROR DETALLADO DE GEMINI -----------\n{e}\n-----------------------------------------------")
        st.error(f"Error en la llamada a Gemini (Key #{st.session_state.api_key_index}): {e}.")
        return None

# ==============================
# RASTREO DE USO
# ==============================
def log_query_event(query_text, mode, rating=None):
    try:
        data = {
            "id": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S%f"),
            "user_name": st.session_state.user,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mode": mode,
            "query": query_text,
            "rating": rating
        }
        supabase.table("queries").insert(data).execute()
    except Exception as e:
        print(f"Error logging query event: {e}")

def get_monthly_usage(username, action_type):
    try:
        first_day_of_month = datetime.date.today().replace(day=1)
        first_day_iso = first_day_of_month.isoformat()
        response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", first_day_iso).execute()
        return response.count
    except Exception as e:
        print(f"Error getting monthly usage: {e}")
        return 0

def get_daily_usage(username, action_type):
    try:
        today_start_utc = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_iso = today_start_utc.isoformat()
        response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", today_start_iso).execute()
        return response.count
    except Exception as e:
        print(f"Error getting daily usage: {e}")
        return 0


# ==============================
# FUNCIONES AUXILIARES Y DE PDF
# ==============================
def normalize_text(text):
    if not text: return ""
    try:
        normalized = unicodedata.normalize("NFD", str(text))
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()
    except Exception as e:
        print(f"Error normalizing text '{text}': {e}")
        return str(text).lower()

def add_markdown_content(pdf, markdown_text):
    try:
        # Decodificar entidades HTML ANTES de pasar a markdown2/BeautifulSoup
        decoded_text = html.unescape(markdown_text)
        html_text = markdown2.markdown(decoded_text, extras=["fenced-code-blocks", "tables", "break-on-newline", "code-friendly"])
        soup = BeautifulSoup(html_text, "html.parser")
        container = soup.body if soup.body else soup

        for elem in container.children:
            if isinstance(elem, str):
                text = elem.strip()
                if text: pdf.add_paragraph(text)
                continue
            if not hasattr(elem, 'name') or not elem.name: continue
            tag_name = elem.name.lower()
            if tag_name.startswith("h"):
                level = int(tag_name[1]) if len(tag_name) > 1 and tag_name[1].isdigit() else 1
                pdf.add_title(elem.get_text(strip=True), level=level)
            elif tag_name == "p": pdf.add_paragraph(elem.decode_contents(formatter="html"))
            elif tag_name == "ul":
                for li in elem.find_all("li", recursive=False): pdf.add_paragraph("• " + li.decode_contents(formatter="html"))
            elif tag_name == "ol":
                for idx, li in enumerate(elem.find_all("li", recursive=False), 1): pdf.add_paragraph(f"{idx}. {li.decode_contents(formatter="html")}")
            elif tag_name == "pre": pdf.add_paragraph(elem.get_text(), style='Code') # Usar estilo 'Code' existente
            elif tag_name == "blockquote": pdf.add_paragraph(">" + elem.decode_contents(formatter="html"))
            else:
                 try: pdf.add_paragraph(elem.decode_contents(formatter="html"))
                 except: pdf.add_paragraph(elem.get_text(strip=True)) # Fallback
    except Exception as e:
        print(f"Error adding markdown content to PDF: {e}")
        pdf.add_paragraph("--- Error parsing markdown ---"); pdf.add_paragraph(markdown_text); pdf.add_paragraph("--- End error ---")

@st.cache_data(show_spinner=False)
def load_database(cliente: str):
    try:
        s3 = boto3.client("s3", endpoint_url=st.secrets["S3_ENDPOINT_URL"], aws_access_key_id=st.secrets["S3_ACCESS_KEY"], aws_secret_access_key=st.secrets["S3_SECRET_KEY"])
        response = s3.get_object(Bucket=st.secrets.get("S3_BUCKET"), Key="resultado_presentacion (1).json")
        data = json.loads(response["Body"].read().decode("utf-8"))
        cliente_norm = normalize_text(cliente or "")
        if cliente_norm != "insights-atelier":
            data = [doc for doc in data if cliente_norm in normalize_text(doc.get("cliente", ""))]
        return data
    except Exception as e:
        st.error(f"Error crítico al cargar datos desde S3: {e}")
        return []

def extract_brand(filename):
    if not filename or not isinstance(filename, str) or "In-ATL_" not in filename: return ""
    try:
        base_filename = filename.replace("\\", "/").split("/")[-1]
        if "In-ATL_" in base_filename: return base_filename.split("In-ATL_")[1].rsplit(".", 1)[0]
        else: return ""
    except Exception as e:
        print(f"Error extracting brand from '{filename}': {e}")
        return ""

def get_relevant_info(db, question, selected_files):
    all_text = ""
    if not isinstance(selected_files, (list, set)): selected_files = []
    selected_files_set = set(selected_files)

    for pres in db:
        doc_name = pres.get('nombre_archivo')
        if doc_name and doc_name in selected_files_set:
            try:
                title = pres.get('titulo_estudio', doc_name)
                all_text += f"Documento: {title}\n"
                for grupo in pres.get("grupos", []):
                    grupo_index = grupo.get('grupo_index', 'N/A')
                    contenido = str(grupo.get('contenido_texto', ''))
                    metadatos = json.dumps(grupo.get('metadatos', {}), ensure_ascii=False) if grupo.get('metadatos') else ""
                    hechos = json.dumps(grupo.get('hechos', []), ensure_ascii=False) if grupo.get('hechos') else ""
                    all_text += f" Grupo {grupo_index}: {contenido}\n"
                    if metadatos: all_text += f"  Metadatos: {metadatos}\n"
                    if hechos: all_text += f"  Hechos: {hechos}\n"
                all_text += "\n---\n\n"
            except Exception as e: print(f"Error processing document '{doc_name}': {e}")
    return all_text

banner_file = "Banner (2).jpg"

def clean_text(text):
    if not isinstance(text, str): text = str(text)
    # Reemplazar solo ampersands que no forman parte de una entidad HTML conocida
    # Esto es más seguro que un replace simple
    # Usamos ReportLab Paragraph que ya maneja entidades HTML básicas
    return text # Dejar que Paragraph maneje la codificación

# --- AJUSTE CLASE PDFReport (Refuerzo Fuente Base y Estilo Code) ---
class PDFReport:
    def __init__(self, buffer_or_filename, banner_path=None):
        self.banner_path = banner_path
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.doc = SimpleDocTemplate(buffer_or_filename, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=45*mm, bottomMargin=18*mm)

        # Usar la fuente registrada globalmente (FONT_NAME)
        pdf_font_name = FONT_NAME

        # Aplicar la fuente a los estilos base más comunes
        base_styles_to_update = ['Normal', 'BodyText', 'Italic', 'Bold', 'Heading1', 'Heading2', 'Heading3', 'Heading4', 'Heading5', 'Heading6', 'Code']
        for style_name in base_styles_to_update:
            if style_name in self.styles:
                try:
                    self.styles[style_name].fontName = pdf_font_name
                    # Ajustes específicos para estilos base si es necesario
                    if style_name == 'Code':
                        # Usar Courier si la fuente principal no es monoespaciada (o si falló DejaVuSans)
                        if pdf_font_name == FALLBACK_FONT_NAME or not FONT_REGISTERED:
                             self.styles[style_name].fontName = 'Courier'
                        self.styles[style_name].fontSize = 9
                        self.styles[style_name].leading = 11
                        self.styles[style_name].leftIndent = 6*mm
                except Exception as e:
                    print(f"Advertencia: No se pudo aplicar fuente '{pdf_font_name}' al estilo base '{style_name}'. {e}")


        # Definir estilos personalizados asegurando que hereden la fuente correcta
        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Heading1'], fontName=pdf_font_name, alignment=1, spaceAfter=12, fontSize=14, leading=18))
        self.styles.add(ParagraphStyle(name='CustomHeading', parent=self.styles['Heading2'], fontName=pdf_font_name, spaceBefore=10, spaceAfter=6, fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='CustomBodyText', parent=self.styles['Normal'], fontName=pdf_font_name, leading=14, alignment=4, fontSize=11))
        self.styles.add(ParagraphStyle(name='CustomFooter', parent=self.styles['Normal'], fontName=pdf_font_name, alignment=1, textColor=colors.grey, fontSize=8))

    def header(self, canvas, doc):
        canvas.saveState()
        if self.banner_path and os.path.isfile(self.banner_path):
            try:
                img_w, img_h = 210*mm, 35*mm; y_pos = A4[1] - img_h
                canvas.drawImage(self.banner_path, 0, y_pos, width=img_w, height=img_h, preserveAspectRatio=True, anchor='n')
            except Exception as e: print(f"Error drawing PDF header image: {e}")
        canvas.restoreState()
    def footer(self, canvas, doc):
        canvas.saveState()
        footer_text = "Generado por Atelier Data Studio IA. Es posible que se muestre información imprecisa. Verifica las respuestas."
        p = Paragraph(footer_text, self.styles['CustomFooter']); w, h = p.wrap(doc.width, doc.bottomMargin); p.drawOn(canvas, doc.leftMargin, 5 * mm)
        canvas.restoreState()
    def header_footer(self, canvas, doc): self.header(canvas, doc); self.footer(canvas, doc)
    def add_paragraph(self, text, style='CustomBodyText'):
        try:
             style_to_use = self.styles.get(style, self.styles.get('BodyText', self.styles['Normal']))
             # Dejar que Paragraph maneje las entidades HTML básicas
             p = Paragraph(text, style_to_use); self.elements.append(p); self.elements.append(Spacer(1, 4))
        except Exception as e: print(f"Error adding paragraph: {e}. Text was: {text[:100]}..."); self.elements.append(Paragraph(f"Error rendering: {text[:100]}...", self.styles['Code']))
    def add_title(self, text, level=1):
        if level == 1: style_name = 'CustomTitle'
        elif level == 2: style_name = 'CustomHeading'
        elif level >= 3: style_name = f'Heading{level}'
        else: style_name = 'CustomHeading'
        style_to_use = self.styles.get(style_name, self.styles['CustomHeading'])
        # Dejar que Paragraph maneje las entidades HTML básicas
        p = Paragraph(text, style_to_use); spacer_height = 10 if level == 1 else (6 if level == 2 else 4)
        self.elements.append(p); self.elements.append(Spacer(1, spacer_height))
    def build_pdf(self):
        try: self.doc.build(self.elements, onFirstPage=self.header_footer, onLaterPages=self.header_footer)
        except Exception as e: st.error(f"Error building PDF: {e}")
# --- FIN AJUSTE CLASE PDFReport ---


def generate_pdf_html(content, title="Documento Final", banner_path=None):
    try:
        buffer = BytesIO(); pdf = PDFReport(buffer, banner_path=banner_path); pdf.add_title(title, level=1)
        add_markdown_content(pdf, content); pdf.build_pdf(); pdf_data = buffer.getvalue(); buffer.close()
        if pdf_data: return pdf_data
        else: st.error("Error interno al construir PDF."); return None
    except Exception as e: st.error(f"Error crítico al generar PDF: {e}"); return None

# =====================================================
# MODOS DE LA APLICACIÓN (SIN CAMBIOS FUNCIONALES)
# =====================================================
def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)
    prompt1 = ( f"Pregunta del Cliente: ***{question}***\n\nInstrucciones:\n1. Identifica marca/producto exacto.\n2. Reitera: ***{question}***.\n3. Usa contexto para hallazgos relevantes.\n4. Extractos breves, no citas completas.\n5. Metadatos y cita IEEE [1].\n6. Referencias completas asociadas a [1], usar título de proyecto.\n7. Enfócate en hallazgos positivos.\n\nContexto:\n{relevant_info}\n\nRespuesta:\n## Hallazgos Clave:\n- [Hallazgo 1 [1]]\n- [Hallazgo 2 [2]]\n## Referencias:\n- [1] [Referencia completa 1]\n- [2] [Referencia completa 2]" )
    result1 = call_gemini_api(prompt1)
    if result1 is None: return None
    prompt2 = ( f"Pregunta: ***{question}***\n\nInstrucciones:\n1. Responde específico a marca/producto.\n2. Menciona que estudios son de Atelier.\n3. Rol: Analista experto (Ciencias Comportamiento, Mkt Research, Mkt Estratégico). Claridad, síntesis, estructura.\n4. Estilo: Claro, directo, conciso, memorable (Heath). Evita tecnicismos.\n\nEstructura Informe (breve y preciso):\n- Introducción: Contexto, pregunta, hallazgo cualitativo atractivo.\n- Hallazgos Principales: Hechos relevantes del contexto/resultados, respondiendo a pregunta. Solo info relevante de marca/producto. Citas IEEE [1] (título estudio).\n- Insights: Aprendizajes profundos, analogías. Frases cortas con significado.\n- Conclusiones: Síntesis, dirección clara basada en insights. No repetir.\n- Recomendaciones (3-4): Concretas, creativas, accionables, alineadas con insights/conclusiones.\n- Referencias: Título estudio [1].\n\n5. IMPORTANTE: Espaciar nombres de marcas/productos (ej: 'marca X debe...').\n\nUsa este Resumen y Contexto:\nResumen:\n{result1}\n\nContexto Adicional:\n{relevant_info}\n\nRedacta informe completo:" )
    result2 = call_gemini_api(prompt2)
    if result2 is None: return None
    return f"**Consulta Original:** {question}\n\n---\n\n" + result2

def report_mode(db, selected_files):
    st.markdown("### Generar Reporte de Reportes")
    st.markdown("Herramienta potente para síntesis. Analiza estudios seleccionados y genera informe consolidado.")
    if "report" in st.session_state and st.session_state["report"]:
        st.markdown("---"); st.markdown("### Informe Generado"); st.markdown(st.session_state["report"], unsafe_allow_html=True); st.markdown("---")
    question = st.text_area("Escribe tu consulta para el reporte…", value=st.session_state.get("last_question", ""), height=150, key="report_question")
    if st.button("Generar Reporte", use_container_width=True):
        report_limit = st.session_state.plan_features.get('reports_per_month', 0); current_reports = get_monthly_usage(st.session_state.user, "Generar un reporte de reportes")
        if current_reports >= report_limit and report_limit != float('inf'): st.error(f"Límite de {int(report_limit)} reportes alcanzado."); return
        if not question.strip(): st.warning("Ingresa una consulta."); return
        st.session_state["last_question"] = question
        with st.spinner("Generando informe..."): report = generate_final_report(question, db, selected_files)
        if report is None: st.error("No se pudo generar."); st.session_state.pop("report", None)
        else: st.session_state["report"] = report; log_query_event(question, mode="Generar un reporte de reportes"); st.rerun()
    if "report" in st.session_state and st.session_state["report"]:
        pdf_bytes = generate_pdf_html(st.session_state["report"], title="Informe Final", banner_path=banner_file)
        col1, col2 = st.columns(2)
        with col1:
            if pdf_bytes: st.download_button("Descargar PDF", data=pdf_bytes, file_name="Informe_AtelierIA.pdf", mime="application/pdf", use_container_width=True)
            else: st.button("Error PDF", disabled=True, use_container_width=True)
        with col2: st.button("Nueva consulta", on_click=reset_report_workflow, key="new_report_query_btn", use_container_width=True)

def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa"); st.markdown("Preguntas específicas, respuestas basadas solo en hallazgos seleccionados.")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    for msg in st.session_state.chat_history:
        with st.chat_message(msg['role']): st.markdown(msg['message'])
    user_input = st.chat_input("Escribe tu pregunta...")
    if user_input:
        st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
        with st.chat_message("Usuario"): st.markdown(user_input)
        query_limit = st.session_state.plan_features.get('chat_queries_per_day', 0); current_queries = get_daily_usage(st.session_state.user, "Chat de Consulta Directa")
        if current_queries >= query_limit and query_limit != float('inf'): st.error(f"Límite de {int(query_limit)} consultas diarias alcanzado."); return
        with st.chat_message("Asistente"):
            message_placeholder = st.empty(); message_placeholder.markdown("Pensando...")
            relevant_info = get_relevant_info(db, user_input, selected_files); conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history[-10:])
            grounded_prompt = (f"**Tarea:** Asistente IA. Responde **última pregunta** del Usuario usando **solo** 'Información documentada' e 'Historial'.\n\n**Historial (reciente):**\n{conversation_history}\n\n**Información documentada:**\n{relevant_info}\n\n**Instrucciones:**\n1. Enfócate en última pregunta.\n2. Sintetiza hallazgos relevantes.\n3. Respuesta corta, clara, basada en hallazgos (no metodología/objetivos).\n4. Fidelidad absoluta a info documentada.\n5. Si falta info: \"La información solicitada no se encuentra disponible...\".\n6. Especificidad marca/producto.\n7. Sin citas.\n\n**Respuesta:**")
            response = call_gemini_api(grounded_prompt)
            if response: message_placeholder.markdown(response); st.session_state.chat_history.append({"role": "Asistente", "message": response}); log_query_event(user_input, mode="Chat de Consulta Directa")
            else: message_placeholder.error("Error al generar respuesta.")
    if st.session_state.chat_history:
        col1, col2 = st.columns([1,1])
        with col1:
             pdf_bytes = generate_pdf_html("\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial Consulta", banner_path=banner_file)
             if pdf_bytes: st.download_button("Descargar Chat PDF", data=pdf_bytes, file_name="chat_consulta.pdf", mime="application/pdf", use_container_width=True)
        with col2: st.button("Nueva Conversación", on_click=reset_chat_workflow, key="new_grounded_chat_btn", use_container_width=True)

def ideacion_mode(db, selected_files):
    st.subheader("Conversaciones Creativas"); st.markdown("Explora ideas novedosas basadas en hallazgos.")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    for msg in st.session_state.chat_history:
        with st.chat_message(msg['role']): st.markdown(msg['message'])
    user_input = st.chat_input("Lanza una idea o pregunta...")
    if user_input:
        st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
        with st.chat_message("Usuario"): st.markdown(user_input)
        with st.chat_message("Asistente"):
            message_placeholder = st.empty(); message_placeholder.markdown("Generando ideas...")
            relevant = get_relevant_info(db, user_input, selected_files); conv_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history[-10:])
            conv_prompt = (f"**Tarea:** Experto Mkt/Innovación creativo. Conversación inspiradora con usuario sobre ideas/soluciones basadas **solo** en 'Información de contexto' e 'Historial'.\n\n**Historial:**\n{conv_history}\n\n**Contexto (hallazgos):**\n{relevant}\n\n**Instrucciones:**\n1. Rol: Experto creativo.\n2. Base: Solo 'Contexto' (resultados/hallazgos).\n3. Objetivo: Ayudar a explorar soluciones creativas conectando datos.\n4. Inicio (1er msg asistente): Breve resumen estudios relevantes.\n5. Estilo: Claro, sintético, inspirador.\n6. Citas: IEEE [1] (ej: estudio snacks [1]).\n\n**Respuesta creativa:**")
            resp = call_gemini_api(conv_prompt)
            if resp: message_placeholder.markdown(resp); st.session_state.chat_history.append({"role": "Asistente", "message": resp}); log_query_event(user_input, mode="Conversaciones creativas")
            else: message_placeholder.error("Error generando respuesta.")
    if st.session_state.chat_history:
        col1, col2 = st.columns([1,1])
        with col1:
            pdf_bytes = generate_pdf_html("\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial Creativo", banner_path=banner_file)
            if pdf_bytes: st.download_button("Descargar Chat PDF", data=pdf_bytes, file_name="chat_creativo.pdf", mime="application/pdf", use_container_width=True)
        with col2: st.button("Nueva conversación", on_click=reset_chat_workflow, key="new_chat_btn", use_container_width=True)

def concept_generation_mode(db, selected_files):
    st.subheader("Generación de Conceptos"); st.markdown("Genera concepto de producto/servicio a partir de idea y hallazgos.")
    if "generated_concept" in st.session_state:
        st.markdown("---"); st.markdown("### Concepto Generado"); st.markdown(st.session_state.generated_concept)
        if st.button("Generar nuevo concepto", use_container_width=True): st.session_state.pop("generated_concept"); st.rerun()
    else:
        product_idea = st.text_area("Describe tu idea:", height=150, placeholder="Ej: Snack saludable...")
        if st.button("Generar Concepto", use_container_width=True):
            if not product_idea.strip(): st.warning("Describe tu idea."); return
            with st.spinner("Generando concepto..."):
                context_info = get_relevant_info(db, product_idea, selected_files)
                prompt = ( f"**Tarea:** Estratega Mkt/Innovación. Desarrolla concepto estructurado a partir de 'Idea' y 'Contexto'.\n\n**Idea:**\n\"{product_idea}\"\n\n**Contexto (Hallazgos):**\n\"{context_info}\"\n\n**Instrucciones:**\nGenera Markdown con estructura exacta. Basa respuestas en contexto. Sé claro, conciso, accionable.\n\n---\n\n### 1. Necesidad Consumidor\n* Identifica tensiones/deseos clave del contexto. Conecta con oportunidad.\n\n### 2. Descripción Producto/Servicio\n* Basado en Idea y enriquecido por Contexto. Características, funcionamiento.\n\n### 3. Beneficios Clave (3-4)\n* Responde a necesidad (Pto 1). Sustentado en Contexto. Funcional/Racional/Emocional.\n\n### 4. Conceptos para Evaluar (2 Opc.)\n* **Opción A:**\n    * **Insight:** (Dolor + Deseo. Basado en contexto).\n    * **What:** (Características/Beneficios. Basado en contexto/descripción).\n    * **RTB:** (¿Por qué creíble? Basado en contexto).\n    * **Claim:** (Esencia memorable).\n\n* **Opción B:** (Alternativa)\n    * **Insight:**\n    * **What:**\n    * **RTB:**\n    * **Claim:**" )
                response = call_gemini_api(prompt)
                if response: st.session_state.generated_concept = response; log_query_event(product_idea, mode="Generación de conceptos"); st.rerun()
                else: st.error("No se pudo generar concepto.")

def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluación de Pre-Ideas"); st.markdown("Evalúa potencial de idea contra hallazgos.")
    if "evaluation_result" in st.session_state:
        st.markdown("---"); st.markdown("### Evaluación"); st.markdown(st.session_state.evaluation_result)
        if st.button("Evaluar otra idea", use_container_width=True): del st.session_state["evaluation_result"]; st.rerun()
    else:
        idea_input = st.text_area("Describe la idea a evaluar:", height=150, placeholder="Ej: Yogures con probióticos...")
        if st.button("Evaluar Idea", use_container_width=True):
            if not idea_input.strip(): st.warning("Describe una idea."); return
            with st.spinner("Evaluando potencial..."):
                context_info = get_relevant_info(db, idea_input, selected_files)
                prompt = ( f"**Tarea:** Estratega Mkt/Innovación. Evalúa potencial de 'Idea' **solo** con 'Contexto' (hallazgos Atelier).\n\n**Idea:**\n\"{idea_input}\"\n\n**Contexto (Hallazgos):**\n\"{context_info}\"\n\n**Instrucciones:**\nEvalúa en Markdown estructurado. Basa **cada punto** en 'Contexto'. No conocimiento externo. No citas explícitas.\n\n---\n\n### 1. Valoración General Potencial\n* Resume: Alto, Moderado con Desafíos, Bajo según Hallazgos.\n\n### 2. Sustento Detallado (Basado en Contexto)\n* **Positivos:** Conecta idea con necesidades/tensiones clave del contexto. Hallazgos específicos que respaldan.\n* **Desafíos/Contradicciones:** Hallazgos que obstaculizan/contradicen.\n\n### 3. Sugerencias Evaluación Consumidor (Basado en Contexto)\n* 3-4 **hipótesis cruciales** (de hallazgos o vacíos). Para c/u:\n    * **Hipótesis:** (Ej: \"Consumidores valoran X sobre Y...\").\n    * **Pregunta Clave:** (Ej: \"¿Qué tan importante es X para Ud? ¿Por qué?\").\n    * **Aporte Pregunta:** (Ej: \"Validar si beneficio X resuena...\")." )
                response = call_gemini_api(prompt)
                if response: st.session_state.evaluation_result = response; log_query_event(idea_input, mode="Evaluación de Idea"); st.rerun()
                else: st.error("No se pudo generar evaluación.")

def image_evaluation_mode(db, selected_files):
    st.subheader("Evaluación Visual de Creatividades")
    st.markdown("""
        Sube una imagen (JPG/PNG) y describe tu público objetivo y objetivos de comunicación.
        El asistente evaluará la imagen basándose en criterios de marketing y
        utilizará los hallazgos de los estudios seleccionados como contexto.
    """)

    uploaded_file = st.file_uploader("Sube tu imagen aquí:", type=["jpg", "png", "jpeg"])
    target_audience = st.text_area("Describe el público objetivo (Target):", height=100, placeholder="Ej: Mujeres jóvenes, 25-35 años, interesadas en vida sana...")
    comm_objectives = st.text_area("Define 2-3 objetivos de comunicación:", height=100, placeholder="Ej:\n1. Generar reconocimiento de nuevo producto.\n2. Comunicar frescura y naturalidad.\n3. Incentivar visita a la web.")

    image_bytes = None
    if uploaded_file is not None:
        # Leer los bytes de la imagen
        image_bytes = uploaded_file.getvalue()
        # Mostrar la imagen subida
        st.image(image_bytes, caption="Imagen a evaluar", use_column_width=True)

    st.markdown("---") # Separador visual

    # Botón para iniciar la evaluación
    if st.button("🧠 Evaluar Imagen", use_container_width=True, disabled=(uploaded_file is None)):
        if not image_bytes:
            st.warning("Por favor, sube una imagen.")
            return
        if not target_audience.strip():
            st.warning("Por favor, describe el público objetivo.")
            return
        if not comm_objectives.strip():
            st.warning("Por favor, define los objetivos de comunicación.")
            return

        with st.spinner("Analizando imagen y contexto... 🧠✨"):
            # Obtener contexto de texto de los estudios seleccionados
            # Usaremos TODO el texto filtrado como contexto general del mercado/consumidor
            # Una mejora futura podría ser filtrar más específicamente basado en palabras clave
            relevant_text_context = get_relevant_info(db, f"Contexto para imagen: {target_audience}", selected_files)

            # Construir el prompt multimodal
            prompt_parts = [
                "Actúa como un director creativo y estratega de marketing experto. Analiza la siguiente imagen en el contexto de un público objetivo y objetivos de comunicación específicos, utilizando también los hallazgos de estudios de mercado proporcionados como referencia.",
                f"\n\n**Público Objetivo (Target):**\n{target_audience}",
                f"\n\n**Objetivos de Comunicación:**\n{comm_objectives}",
                "\n\n**Imagen a Evaluar:**",
                # Pasar los bytes de la imagen al modelo
                # Necesitamos importar PIL Image
                Image.open(BytesIO(image_bytes)), # Asume que tienes 'from PIL import Image' y 'from io import BytesIO'
                f"\n\n**Contexto (Hallazgos de Estudios de Mercado):**\n```\n{relevant_text_context[:10000]}\n```", # Limitar contexto para no exceder límites
                "\n\n**Evaluación Detallada (Formato Markdown):**",
                "\n### 1. Notoriedad e Impacto Visual",
                "* ¿La imagen capta la atención? ¿Es visualmente atractiva o disruptiva para el target descrito?",
                "* ¿Qué elementos visuales (colores, composición, personajes, etc.) contribuyen (o restan) a su impacto? Apóyate en el contexto si encuentras insights relevantes sobre preferencias visuales del target.",
                "\n### 2. Mensaje Clave y Claridad",
                "* ¿Qué mensaje principal y secundarios transmite la imagen? ¿Son coherentes con los objetivos?",
                "* ¿Es el mensaje fácil de entender para el público objetivo? ¿Hay ambigüedades?",
                "* ¿Cómo se relaciona el mensaje visual con posibles insights del consumidor encontrados en el contexto?",
                "\n### 3. Branding e Identidad",
                "* ¿Se integra la marca (logo, colores corporativos, estilo visual) de forma efectiva? ¿Es reconocible?",
                "* ¿La imagen refuerza la personalidad o valores de la marca (según se pueda inferir o si hay contexto relevante)?",
                "\n### 4. Llamada a la Acción (Implícita o Explícita) y Respuesta Esperada",
                "* ¿La imagen sugiere alguna acción o genera alguna emoción/pensamiento específico en el espectador (curiosidad, deseo, confianza, urgencia)?",
                "* ¿Está alineada esta respuesta esperada con los objetivos de comunicación?",
                "* Considerando el contexto, ¿es probable que esta creatividad motive al target a dar el siguiente paso?",
                "\n\n**Conclusión General:**",
                "* Resume tu valoración sobre la efectividad potencial de esta imagen para el target y objetivos dados, mencionando sus puntos fuertes y áreas de mejora, idealmente conectando con algún insight clave del contexto si aplica."
            ]

            # Llamar a la API de Gemini (asegúrate que call_gemini_api puede manejar listas como prompt)
            # La librería google.generativeai maneja la lista de partes automáticamente
            evaluation_result = call_gemini_api(prompt_parts)

            if evaluation_result:
                st.session_state.image_evaluation_result = evaluation_result
                log_query_event(f"Evaluación Imagen: {uploaded_file.name}", mode="Evaluación Visual")
                # No necesitamos rerun aquí, el resultado se mostrará abajo
            else:
                st.error("No se pudo generar la evaluación de la imagen.")
                st.session_state.pop("image_evaluation_result", None)

    # Mostrar el resultado si existe
    if "image_evaluation_result" in st.session_state:
        st.markdown("---")
        st.markdown("### ✨ Resultados de la Evaluación:")
        st.markdown(st.session_state.image_evaluation_result)
        # Botón para limpiar y evaluar otra
        if st.button("Evaluar Otra Imagen", use_container_width=True):
            st.session_state.pop("image_evaluation_result", None)
            # No limpiamos el uploader, pero sí el resultado. El usuario puede subir otra.
            st.rerun()

# =====================================================
# PANEL DE ADMINISTRACIÓN (CON EDICIÓN DE USUARIOS)
# =====================================================
def show_admin_dashboard():
    st.subheader("Estadísticas de Uso", divider="grey")
    with st.spinner("Cargando estadísticas..."):
        try:
            stats_response = supabase.table("queries").select("user_name, mode, timestamp, query").execute()
            if stats_response.data:
                df_stats = pd.DataFrame(stats_response.data); df_stats['timestamp'] = pd.to_datetime(df_stats['timestamp']).dt.tz_localize(None); df_stats['date'] = df_stats['timestamp'].dt.date
                col1, col2 = st.columns(2)
                with col1: st.write("**Consultas por Usuario (Total)**"); user_counts = df_stats.groupby('user_name')['mode'].count().reset_index(name='Total Consultas').sort_values(by="Total Consultas", ascending=False); st.dataframe(user_counts, use_container_width=True, hide_index=True)
                with col2: st.write("**Consultas por Modo de Uso (Total)**"); mode_counts = df_stats.groupby('mode')['user_name'].count().reset_index(name='Total Consultas').sort_values(by="Total Consultas", ascending=False); st.dataframe(mode_counts, use_container_width=True, hide_index=True)
                st.write("**Actividad Reciente (Últimas 50 consultas)**"); df_recent = df_stats[['timestamp', 'user_name', 'mode', 'query']].sort_values(by="timestamp", ascending=False).head(50); df_recent['timestamp'] = df_recent['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S'); st.dataframe(df_recent, use_container_width=True, hide_index=True)
            else: st.info("Aún no hay datos de uso.")
        except Exception as e: st.error(f"Error cargando estadísticas: {e}")

    st.subheader("Gestión de Clientes (Invitaciones)", divider="grey")
    try:
        clients_response = supabase.table("clients").select("client_name, plan, invite_code, created_at").order("created_at", desc=True).execute()
        if clients_response.data: st.write("**Clientes Actuales**"); df_clients = pd.DataFrame(clients_response.data); df_clients['created_at'] = pd.to_datetime(df_clients['created_at']).dt.strftime('%Y-%m-%d'); st.dataframe(df_clients, use_container_width=True, hide_index=True)
        else: st.info("No hay clientes.")
    except Exception as e: st.error(f"Error cargando clientes: {e}")

    with st.expander("➕ Crear Nuevo Cliente y Código"):
        with st.form("new_client_form"):
            new_client_name = st.text_input("Nombre"); new_plan = st.selectbox("Plan", options=list(PLAN_FEATURES.keys()), index=0); new_invite_code = st.text_input("Código Invitación")
            submitted = st.form_submit_button("Crear Cliente")
            if submitted:
                if not new_client_name or not new_plan or not new_invite_code: st.warning("Completa campos."); return
                try: supabase_admin_client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"]); supabase_admin_client.table("clients").insert({"client_name": new_client_name, "plan": new_plan, "invite_code": new_invite_code}).execute(); st.success(f"Cliente '{new_client_name}' creado. Código: {new_invite_code}")
                except Exception as e: st.error(f"Error al crear: {e}")

    st.subheader("Gestión de Usuarios", divider="grey")
    try:
        if "SUPABASE_SERVICE_KEY" not in st.secrets: st.error("Falta 'SUPABASE_SERVICE_KEY'"); st.stop()
        supabase_admin_client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])
        users_response = supabase_admin_client.table("users").select("id, email, created_at, rol, client_id, clients(client_name, plan)").order("created_at", desc=True).execute()
        if users_response.data:
            st.write("**Usuarios Registrados** (Puedes editar Rol)")
            user_list = [{'id': u.get('id'), 'email': u.get('email'), 'creado_el': u.get('created_at'), 'rol': u.get('rol', 'user'), 'cliente': u.get('clients', {}).get('client_name', "N/A"), 'plan': u.get('clients', {}).get('plan', "N/A")} for u in users_response.data]
            original_df = pd.DataFrame(user_list);
            if 'original_users_df' not in st.session_state: st.session_state.original_users_df = original_df.copy()
            display_df = original_df.copy(); display_df['creado_el'] = pd.to_datetime(display_df['creado_el']).dt.strftime('%Y-%m-%d %H:%M')
            edited_df = st.data_editor( display_df, key="user_editor", column_config={"id": None, "rol": st.column_config.SelectboxColumn("Rol", options=["user", "admin"], required=True), "email": st.column_config.TextColumn("Email", disabled=True), "creado_el": st.column_config.TextColumn("Creado", disabled=True), "cliente": st.column_config.TextColumn("Cliente", disabled=True), "plan": st.column_config.TextColumn("Plan", disabled=True)}, use_container_width=True, hide_index=True, num_rows="fixed")
            if st.button("Guardar Cambios Usuarios", use_container_width=True):
                updates_to_make = []; original_users = st.session_state.original_users_df; edited_df_indexed = edited_df.set_index(original_df.index); edited_df_with_ids = original_df[['id']].join(edited_df_indexed)
                for index, original_row in original_users.iterrows():
                    edited_rows_match = edited_df_with_ids[edited_df_with_ids['id'] == original_row['id']]
                    if not edited_rows_match.empty:
                        edited_row = edited_rows_match.iloc[0]
                        if original_row['rol'] != edited_row['rol']: updates_to_make.append({"id": original_row['id'], "email": original_row['email'], "new_rol": edited_row['rol']})
                    else: print(f"Warn: Row ID {original_row['id']} not in edited df.")
                if updates_to_make:
                    success_count, error_count, errors = 0, 0, []
                    with st.spinner(f"Guardando {len(updates_to_make)} cambio(s)..."):
                        for update in updates_to_make:
                            try: supabase_admin_client.table("users").update({"rol": update["new_rol"]}).eq("id", update["id"]).execute(); success_count += 1
                            except Exception as e: errors.append(f"Error {update['email']} (ID: {update['id']}): {e}"); error_count += 1
                    if success_count > 0: st.success(f"{success_count} actualizado(s).")
                    if error_count > 0: st.error(f"{error_count} error(es):"); [st.error(f"- {err}") for err in errors]
                    del st.session_state.original_users_df; st.rerun()
                else: st.info("No se detectaron cambios.")
        else: st.info("No hay usuarios.")
    except Exception as e: st.error(f"Error gestión usuarios: {e}")

# =====================================================
# FUNCIÓN PARA EL MODO USUARIO (REFACTORIZADA)
# =====================================================

def run_user_mode(db_full, user_features, footer_html):
    """
    Ejecuta toda la lógica de la aplicación para el modo de usuario estándar.
    """
    st.sidebar.image("LogoDataStudio.png")
    st.sidebar.write(f"Usuario: {st.session_state.user}")
    if st.session_state.get("is_admin", False): st.sidebar.caption("Rol: Administrador")
    st.sidebar.divider()

    db_filtered = db_full[:]

    modos_disponibles = ["Chat de Consulta Directa"]
    if user_features.get("has_report_generation"): modos_disponibles.insert(0, "Generar un reporte de reportes")
    if user_features.get("has_creative_conversation"): modos_disponibles.append("Conversaciones creativas")
    if user_features.get("has_concept_generation"): modos_disponibles.append("Generación de conceptos")
    if user_features.get("has_idea_evaluation"): modos_disponibles.append("Evaluar una idea")
    # --- AÑADIR NUEVO MODO AQUÍ ---
    if user_features.get("has_image_evaluation"): modos_disponibles.append("Evaluación Visual")
    # --- FIN AÑADIR ---

    st.sidebar.header("Seleccione el modo de uso")
    modo = st.sidebar.radio("Modos:", modos_disponibles, label_visibility="collapsed", key="main_mode_selector")

    # Resetear estados específicos del modo si cambia (incluir nuevo estado)
    if 'current_mode' not in st.session_state: st.session_state.current_mode = modo
    if st.session_state.current_mode != modo:
        reset_chat_workflow()
        st.session_state.pop("generated_concept", None); st.session_state.pop("evaluation_result", None)
        st.session_state.pop("report", None); st.session_state.pop("last_question", None)
        st.session_state.pop("image_evaluation_result", None) # <-- Limpiar resultado de imagen
        st.session_state.current_mode = modo

    st.sidebar.header("Filtros de Búsqueda")
    # ... (código de filtros sin cambios) ...
    marcas_options = sorted({doc.get("filtro", "") for doc in db_full if doc.get("filtro")})
    selected_marcas = st.sidebar.multiselect("Marca(s):", marcas_options, key="filter_marcas")
    if selected_marcas: db_filtered = [d for d in db_filtered if d.get("filtro") in selected_marcas]

    years_options = sorted({doc.get("marca", "") for doc in db_full if doc.get("marca")})
    selected_years = st.sidebar.multiselect("Año(s):", years_options, key="filter_years")
    if selected_years: db_filtered = [d for d in db_filtered if d.get("marca") in selected_years]

    brands_options = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_filtered if extract_brand(d.get("nombre_archivo", ""))})
    selected_brands = st.sidebar.multiselect("Proyecto(s):", brands_options, key="filter_projects")
    if selected_brands: db_filtered = [d for d in db_filtered if extract_brand(d.get("nombre_archivo", "")) in selected_brands]


    if st.sidebar.button("Cerrar Sesión", key="logout_main", use_container_width=True):
        supabase.auth.sign_out(); st.session_state.clear(); st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown(footer_html, unsafe_allow_html=True)

    selected_files = [d.get("nombre_archivo") for d in db_filtered]
    # Mostrar advertencia si es necesario (sin cambios)
    # if not selected_files and modo not in ["Generar un reporte de reportes", "Evaluación Visual"]: # Ajustar si evaluación necesita filtros
    #      st.warning("⚠️ No hay estudios que coincidan con los filtros seleccionados.")

    # --- AÑADIR ELIF PARA NUEVO MODO ---
    if modo == "Generar un reporte de reportes": report_mode(db_filtered, selected_files)
    elif modo == "Conversaciones creativas": ideacion_mode(db_filtered, selected_files)
    elif modo == "Generación de conceptos": concept_generation_mode(db_filtered, selected_files)
    elif modo == "Chat de Consulta Directa": grounded_chat_mode(db_filtered, selected_files)
    elif modo == "Evaluar una idea": idea_evaluator_mode(db_filtered, selected_files)
    elif modo == "Evaluación Visual": image_evaluation_mode(db_filtered, selected_files) 

# =====================================================
# FUNCIÓN PRINCIPAL DE LA APLICACIÓN
# =====================================================
def main():
    if 'page' not in st.session_state: st.session_state.page = "login"
    footer_text = "Atelier Consultoría y Estrategia S.A.S - Todos los Derechos Reservados 2025"
    footer_html = f"<div style='text-align: center; color: gray; font-size: 12px;'>{footer_text}</div>"

    if not st.session_state.get("logged_in"):
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.image("LogoDataStudio.png")
            if st.session_state.page == "login": show_login_page()
            elif st.session_state.page == "signup": show_signup_page()
            elif st.session_state.page == "reset_password": show_reset_password_page()
        st.divider() # Mantener el divider del footer general
        st.markdown(footer_html, unsafe_allow_html=True)
        st.stop()

    try: db_full = load_database(st.session_state.cliente)
    except Exception as e: st.error(f"Error crítico al cargar BD: {e}"); st.stop()

    user_features = st.session_state.plan_features

    if st.session_state.get("is_admin", False):
        tab_user, tab_admin = st.tabs(["[ Modo Usuario ]", "[ Modo Administrador ]"])
        with tab_user: run_user_mode(db_full, user_features, footer_html)
        with tab_admin:
            st.title("Panel de Administración")
            st.write(f"Gestionando como: {st.session_state.user}")
            show_admin_dashboard()
    else: run_user_mode(db_full, user_features, footer_html)

if __name__ == "__main__":
    main()

