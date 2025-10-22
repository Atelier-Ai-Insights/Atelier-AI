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

# ==============================
# Autenticación con Supabase Auth (Botones ajustados)
# ==============================

def show_signup_page():
    st.header("Crear Nueva Cuenta")
    email = st.text_input("Tu Correo Electrónico")
    password = st.text_input("Crea una Contraseña", type="password")
    invite_code = st.text_input("Código de Invitación de tu Empresa")

    # Botón Registrarse ajustado
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

    # Botón Volver al Login ajustado
    if st.button("¿Ya tienes cuenta? Inicia Sesión", type="secondary", use_container_width=True):
         st.session_state.page = "login"
         st.rerun()


def show_login_page():
    st.header("Iniciar Sesión")
    email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
    password = st.text_input("Contraseña", type="password", placeholder="password")

    # Botón Ingresar ajustado
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

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        # Botón Registrarse ajustado
        if st.button("¿No tienes cuenta? Regístrate", type="secondary", use_container_width=True):
            st.session_state.page = "signup"
            st.rerun()
    with col2:
        # Botón Olvidaste Contraseña ajustado
        if st.button("¿Olvidaste tu contraseña?", type="secondary", use_container_width=True):
            st.session_state.page = "reset_password"
            st.rerun()


def show_reset_password_page():
    st.header("Restablecer Contraseña")
    st.write("Ingresa tu correo electrónico y te enviaremos un enlace para restablecer tu contraseña.")
    email = st.text_input("Tu Correo Electrónico")

    # Botón Enviar Enlace ajustado
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

    # Botón Volver al Login ajustado
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
        html_text = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "tables", "break-on-newline", "code-friendly"])
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
                for idx, li in enumerate(elem.find_all("li", recursive=False), 1): pdf.add_paragraph(f"{idx}. {li.decode_contents(formatter='html')}")
            elif tag_name == "pre": pdf.add_paragraph(elem.get_text(), style='Code')
            elif tag_name == "blockquote": pdf.add_paragraph(">" + elem.decode_contents(formatter="html"))
            else:
                 try: pdf.add_paragraph(elem.decode_contents(formatter="html"))
                 except: pdf.add_paragraph(elem.get_text(strip=True))
    except Exception as e:
        print(f"Error adding markdown content to PDF: {e}")
        pdf.add_paragraph("--- Error parsing markdown ---")
        pdf.add_paragraph(markdown_text)
        pdf.add_paragraph("--- End error ---")


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
            except Exception as e:
                 print(f"Error processing document '{doc_name}': {e}")
    return all_text

banner_file = "Banner (2).jpg"

def clean_text(text):
    if not isinstance(text, str): text = str(text)
    return text.replace('&', '&amp;')

class PDFReport:
    def __init__(self, buffer_or_filename, banner_path=None):
        self.banner_path = banner_path; self.elements = []
        self.styles = getSampleStyleSheet()
        self.doc = SimpleDocTemplate(buffer_or_filename, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=45*mm, bottomMargin=18*mm)
        font_name = 'DejaVuSans' if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Heading1'], fontName=font_name, alignment=1, spaceAfter=12, fontSize=14, leading=18))
        self.styles.add(ParagraphStyle(name='CustomHeading', parent=self.styles['Heading2'], fontName=font_name, spaceBefore=10, spaceAfter=6, fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='CustomBodyText', parent=self.styles['Normal'], fontName=font_name, leading=14, alignment=4, fontSize=11))
        self.styles.add(ParagraphStyle(name='CustomFooter', parent=self.styles['Normal'], fontName=font_name, alignment=2, textColor=colors.grey, fontSize=8))
        self.styles.add(ParagraphStyle(name='Code', parent=self.styles['Code'], fontName='Courier', fontSize=9, leading=11, leftIndent=6*mm))

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
        page_num = canvas.getPageNumber(); page_text = f"Página {page_num}"
        p_page = Paragraph(page_text, self.styles['CustomFooter']); w_page, h_page = p_page.wrap(doc.width, doc.bottomMargin); p_page.drawOn(canvas, doc.width + doc.leftMargin - w_page, 5 * mm)
        canvas.restoreState()
    def header_footer(self, canvas, doc): self.header(canvas, doc); self.footer(canvas, doc)
    def add_paragraph(self, text, style='CustomBodyText'):
        try:
             cleaned_text = text.replace('<br>', '<br/>').replace('<br />', '<br/>').replace('<strong>', '<b>').replace('</strong>', '</b>').replace('<em>', '<i>').replace('</em>', '</i>')
             p = Paragraph(clean_text(cleaned_text), self.styles[style]); self.elements.append(p); self.elements.append(Spacer(1, 4))
        except Exception as e:
            print(f"Error adding paragraph: {e}. Text was: {text[:100]}...")
            self.elements.append(Paragraph(f"Error rendering: {text[:100]}...", self.styles['Code']))
    def add_title(self, text, level=1):
        style_name = 'CustomTitle' if level == 1 else ('CustomHeading' if level == 2 else 'h3')
        if level > 2: style_name = self.styles.get(f'h{level}', self.styles['CustomHeading']).name
        p = Paragraph(clean_text(text), self.styles[style_name]); spacer_height = 10 if level == 1 else (6 if level == 2 else 4)
        self.elements.append(p); self.elements.append(Spacer(1, spacer_height))
    def build_pdf(self):
        try: self.doc.build(self.elements, onFirstPage=self.header_footer, onLaterPages=self.header_footer)
        except Exception as e: st.error(f"Error building PDF: {e}")

def generate_pdf_html(content, title="Documento Final", banner_path=None):
    try:
        buffer = BytesIO(); pdf = PDFReport(buffer, banner_path=banner_path)
        pdf.add_title(title, level=1); add_markdown_content(pdf, content); pdf.build_pdf()
        pdf_data = buffer.getvalue(); buffer.close(); return pdf_data
    except Exception as e: st.error(f"Error crítico al generar el PDF: {e}"); return None

# =====================================================
# MODOS DE LA APLICACIÓN
# =====================================================
# (generate_final_report, report_mode, grounded_chat_mode, ideacion_mode, concept_generation_mode, idea_evaluator_mode - sin cambios)
def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)
    prompt1 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones:\n"
        "1. Identifica en la pregunta la marca exacta y/o el producto exacto sobre el cual se hace la consulta. Sé muy específico y riguroso en referenciar información asociada a la marca y/o producto consultado.\n"
        f"2. Reitera la pregunta del cliente: ***{question}***.\n"
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
        "5. MUY IMPORTANTE: Asegúrate de que los nombres de marcas y productos estén correctamente espaciados del texto circundante. Por ejemplo, escribe 'la marca Crem Helado debe...' en lugar de 'lamarcaCrem Heladodebe...'. Presta especial atención a este detalle de formato para asegurar la legibilidad.\n\n"
        f"Resumen de Hallazgos Clave y Referencias:\n{result1}\n\n"
        f"Información de Contexto Adicional (si es necesaria para complementar el resumen):\n{relevant_info}\n\n"
        "Por favor, redacta el informe completo respetando la estructura y las instrucciones, en un estilo profesional, claro, conciso y coherente."
    )
    result2 = call_gemini_api(prompt2)
    if result2 is None: return None
    return f"**Consulta Original:** {question}\n\n---\n\n" + result2


def report_mode(db, selected_files):
    st.markdown("### Generar Reporte de Reportes")
    st.markdown(
        "Esta es la herramienta más potente para la síntesis. A partir de una pregunta, el asistente analizará **todos los estudios seleccionados** y generará un único informe consolidado con introducción, hallazgos, insights, conclusiones y recomendaciones."
    )
    if "report" in st.session_state and st.session_state["report"]:
        st.markdown("---")
        st.markdown("### Informe Generado")
        st.markdown(st.session_state["report"], unsafe_allow_html=True)
        st.markdown("---")
    question = st.text_area("Escribe tu consulta para el reporte…", value=st.session_state.get("last_question", ""), height=150, key="report_question")

    if st.button("Generar Reporte"):
        report_limit = st.session_state.plan_features.get('reports_per_month', 0)
        if not isinstance(report_limit, (int, float)): report_limit = 0
        current_reports = get_monthly_usage(st.session_state.user, "Generar un reporte de reportes")

        if current_reports >= report_limit and report_limit != float('inf'):
            st.error(f"Has alcanzado tu límite de {int(report_limit)} reportes este mes.")
            st.warning("🚀 ¡Actualiza tu plan para generar más reportes!")
            return
        if not question.strip():
            st.warning("Por favor, ingresa una consulta para generar el reporte.")
        else:
            st.session_state["last_question"] = question
            with st.spinner("Generando informe... Este proceso puede tardar unos minutos."):
                report = generate_final_report(question, db, selected_files)

            if report is None:
                st.error("No se pudo generar el informe. Inténtalo de nuevo o revisa los logs si el problema persiste.")
                st.session_state.pop("report", None)
            else:
                st.session_state["report"] = report
                log_query_event(question, mode="Generar un reporte de reportes")
                st.rerun()

    if "report" in st.session_state and st.session_state["report"]:
        pdf_bytes = generate_pdf_html(st.session_state["report"], title="Informe Final", banner_path=banner_file)
        col1, col2 = st.columns(2)
        with col1:
            if pdf_bytes:
                 st.download_button("Descargar Informe en PDF", data=pdf_bytes, file_name="Informe_AtelierIA.pdf", mime="application/pdf", use_container_width=True)
            else:
                 st.error("No se pudo generar el PDF del informe.")
        with col2:
            st.button("Nueva consulta", on_click=reset_report_workflow, key="new_report_query_btn", use_container_width=True)

def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    st.markdown("Realiza preguntas específicas y obtén respuestas concretas basadas únicamente en los hallazgos de los informes seleccionados.")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg['role']):
            st.markdown(msg['message'])

    user_input = st.chat_input("Escribe tu pregunta...")

    if user_input:
        st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
        with st.chat_message("Usuario"):
            st.markdown(user_input)

        query_limit = st.session_state.plan_features.get('chat_queries_per_day', 0)
        if not isinstance(query_limit, (int, float)): query_limit = 0
        current_queries = get_daily_usage(st.session_state.user, "Chat de Consulta Directa")

        if current_queries >= query_limit and query_limit != float('inf'):
            st.error(f"Has alcanzado tu límite de {int(query_limit)} consultas diarias.")
            st.warning("🚀 ¡Actualiza tu plan para tener consultas ilimitadas!")
            return

        with st.chat_message("Asistente"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Pensando...")
            relevant_info = get_relevant_info(db, user_input, selected_files)
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history[-10:])

            grounded_prompt = (
                f"**Tarea:** Eres un **asistente de IA** experto en sintetizar estudios de mercado. Responde a la **última pregunta del Usuario** basándote **únicamente** en la 'Información documentada' y el 'Historial'.\n\n"
                f"**Historial de la Conversación (reciente):**\n{conversation_history}\n\n"
                f"**Información documentada en los reportes (Única fuente de verdad):**\n{relevant_info}\n\n"
                "**Instrucciones Estrictas:**\n"
                "1. **Enfoque:** Responde SOLO la última pregunta del 'Usuario'.\n"
                "2. **Síntesis:** Conecta hallazgos de TODOS los reportes relevantes para una respuesta completa y agrupada por temas.\n"
                "3. **Estructura:** Respuesta corta, clara y concreta, sustentada por hallazgos clave. NO incluyas metodología ni objetivos.\n"
                "4. **Fidelidad Absoluta:** Usa EXCLUSIVAMENTE la 'Información documentada'. NO inventes ni supongas.\n"
                "5. **Info Faltante:** Si no está en los documentos, indica: \"La información solicitada no se encuentra disponible en los documentos analizados.\"\n"
                "6. **Especificidad:** Si preguntan por marca/producto/categoría específica, usa SOLO información de reportes relacionados.\n"
                "7. **Sin Citas:** No cites fuentes para mantener fluidez.\n\n"
                "**Respuesta:**"
            )

            response = call_gemini_api(grounded_prompt)

            if response:
                message_placeholder.markdown(response)
                st.session_state.chat_history.append({"role": "Asistente", "message": response})
                log_query_event(user_input, mode="Chat de Consulta Directa")
            else:
                 message_placeholder.error("Error al generar la respuesta. Inténtalo de nuevo.")

    if st.session_state.chat_history:
        col1, col2 = st.columns([1,1])
        with col1:
             pdf_bytes = generate_pdf_html("\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial de Consulta Directa", banner_path=banner_file)
             if pdf_bytes:
                 st.download_button( "Descargar Chat en PDF", data=pdf_bytes, file_name="chat_consulta.pdf", mime="application/pdf", use_container_width=True)
        with col2:
             st.button("Nueva Conversación", on_click=reset_chat_workflow, key="new_grounded_chat_btn", use_container_width=True)


def ideacion_mode(db, selected_files):
    st.subheader("Conversaciones Creativas")
    st.markdown("Este es un espacio para explorar ideas novedosas. Basado en los hallazgos, el asistente te ayudará a generar conceptos creativos.")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg['role']):
            st.markdown(msg['message'])

    user_input = st.chat_input("Lanza una idea o pregunta para iniciar la conversación...")

    if user_input:
        st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
        with st.chat_message("Usuario"):
            st.markdown(user_input)

        with st.chat_message("Asistente"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Generando ideas...")
            relevant = get_relevant_info(db, user_input, selected_files)
            conv_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history[-10:])

            conv_prompt = (
                f"**Tarea:** Eres un **experto en marketing e innovación** muy creativo. Tu objetivo es tener una conversación inspiradora con el usuario, ayudándole a generar soluciones o ideas novedosas basadas en la 'Información de contexto' y el 'Historial'.\n\n"
                f"**Historial de conversación (reciente):**\n{conv_history}\n\n"
                f"**Información de contexto (hallazgos de estudios):**\n{relevant}\n\n"
                "**Instrucciones:**\n"
                "1. **Rol:** Actúa como un experto creativo en marketing.\n"
                "2. **Base:** Usa **únicamente** la 'Información de contexto' (sección de resultados/hallazgos) para fundamentar tus ideas.\n"
                "3. **Objetivo:** Ayuda al usuario a explorar soluciones creativas para su problema o situación, conectando los datos disponibles.\n"
                "4. **Inicio (si es el primer mensaje del asistente):** Comienza con un breve resumen (1-2 frases) de los estudios relevantes encontrados en el contexto relacionados con la primera pregunta del usuario.\n"
                "5. **Estilo:** Sé claro, sintético, concreto e inspirador. Fomenta la exploración.\n"
                "6. **Citas:** Incluye citas numeradas al estilo IEEE (ej: [1]) referenciando brevemente la fuente (ej: estudio sobre snacks [1]).\n\n"
                "**Respuesta detallada y creativa:**"
            )

            resp = call_gemini_api(conv_prompt)
            if resp:
                message_placeholder.markdown(resp)
                st.session_state.chat_history.append({"role": "Asistente", "message": resp})
                log_query_event(user_input, mode="Conversaciones creativas")
            else:
                message_placeholder.error("Error al generar la respuesta creativa.")

    if st.session_state.chat_history:
        col1, col2 = st.columns([1,1])
        with col1:
            pdf_bytes = generate_pdf_html("\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial de Chat Creativo", banner_path=banner_file)
            if pdf_bytes:
                st.download_button("Descargar Chat en PDF", data=pdf_bytes, file_name="chat_creativo.pdf", mime="application/pdf", use_container_width=True)
        with col2:
            st.button("Nueva conversación", on_click=reset_chat_workflow, key="new_chat_btn", use_container_width=True)


def concept_generation_mode(db, selected_files):
    st.subheader("Generación de Conceptos")
    st.markdown("A partir de una idea inicial y los hallazgos, generaremos un concepto de producto o servicio.")

    if "generated_concept" in st.session_state:
        st.markdown("---")
        st.markdown("### Concepto Generado")
        st.markdown(st.session_state.generated_concept)
        if st.button("Generar un nuevo concepto"):
            st.session_state.pop("generated_concept")
            st.rerun()
    else:
        product_idea = st.text_area("Describe tu idea de producto o servicio:", height=150, placeholder="Ej: Un snack saludable para niños basado en frutas deshidratadas...")
        if st.button("Generar Concepto"):
            if not product_idea.strip():
                st.warning("Por favor, describe tu idea para continuar.")
            else:
                with st.spinner("Analizando hallazgos y generando el concepto..."):
                    context_info = get_relevant_info(db, product_idea, selected_files)
                    prompt = (
                        f"**Tarea:** Eres un estratega de innovación y marketing. A partir de una idea de producto y un contexto de estudios de mercado, debes desarrollar un concepto de producto o servicio estructurado.\n\n"
                        f'**Idea de Producto del Usuario:**\n"{product_idea}"\n\n'
                        f'**Contexto (Hallazgos de Estudios de Mercado):**\n"{context_info}"\n\n'
                        "**Instrucciones:**\n"
                        "Genera una respuesta en formato Markdown con la siguiente estructura exacta. Basa tus respuestas **directamente** en los hallazgos relevantes del contexto proporcionado. Sé claro, conciso y accionable.\n\n"
                        "---\n\n"
                        "### 1. Definición de la Necesidad del Consumidor\n"
                        "* Identifica y describe las tensiones, deseos o problemas clave de los consumidores que se encuentran en el **Contexto de los estudios**. Conecta explícitamente estos hallazgos con la oportunidad para la idea de producto/servicio propuesta.\n\n"
                        "### 2. Descripción del Producto/Servicio\n"
                        "* Basado en la **Idea del Usuario** y enriquecido por el **Contexto**, describe el producto o servicio propuesto. Detalla sus características principales y cómo funcionaría. Sé creativo pero mantente anclado en la necesidad insatisfecha detectada y los hallazgos.\n\n"
                        "### 3. Beneficios Clave\n"
                        "* Enumera 3-4 beneficios principales. Cada beneficio debe: a) Responder directamente a una necesidad del punto 1. b) Estar sustentado por evidencia del **Contexto**. c) Ser funcional, racional o emocional.\n\n"
                        "### 4. Conceptos para Evaluar (2 Opciones)\n"
                        "* **Opción A:**\n"
                        "    * **Insight:** (Dolor del consumidor + Lo que le gustaría tener. Basado en contexto).\n"
                        "    * **What:** (Características y beneficios clave del producto/servicio. Basado en contexto y descripción).\n"
                        "    * **Reason To Believe (RTB):** (¿Por qué el producto puede resolver la tensión? ¿Qué lo hace creíble? Basado en contexto).\n"
                        "    * **Claim:** (Frase corta y memorable que capta la esencia).\n\n"
                        "* **Opción B:** (Presenta una alternativa, quizás enfocada en otro beneficio o insight del contexto)\n"
                        "    * **Insight:**\n"
                        "    * **What:**\n"
                        "    * **Reason To Believe (RTB):**\n"
                        "    * **Claim:**"
                    )
                    response = call_gemini_api(prompt)
                    if response:
                        st.session_state.generated_concept = response
                        log_query_event(product_idea, mode="Generación de conceptos")
                        st.rerun()
                    else:
                        st.error("No se pudo generar el concepto. Inténtalo de nuevo.")


def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluación de Pre-Ideas")
    st.markdown("Presenta una idea y el asistente la evaluará contra los hallazgos, indicando su potencial.")

    if "evaluation_result" in st.session_state:
        st.markdown("---")
        st.markdown("### Evaluación de la Idea")
        st.markdown(st.session_state.evaluation_result)
        if st.button("Evaluar otra idea"):
            del st.session_state["evaluation_result"]
            st.rerun()
    else:
        idea_input = st.text_area("Describe la idea que quieres evaluar:", height=150, placeholder="Ej: Una línea de yogures con probióticos enfocada en mejorar la digestión...")
        if st.button("Evaluar Idea"):
            if not idea_input.strip():
                st.warning("Por favor, describe una idea para continuar.")
            else:
                with st.spinner("Evaluando el potencial de la idea..."):
                    context_info = get_relevant_info(db, idea_input, selected_files)
                    prompt = (
                        f"**Tarea:** Eres un estratega de mercado y analista de innovación. Tu objetivo es evaluar el potencial de una idea de producto o servicio, basándote **exclusivamente** en los hallazgos ('Contexto') de estudios de mercado realizados por Atelier.\n\n"
                        f'**Idea a Evaluar:**\n"{idea_input}"\n\n'
                        f'**Contexto (Hallazgos de Estudios de Mercado Atelier):**\n"{context_info}"\n\n'
                        "**Instrucciones:**\n"
                        "Genera una evaluación estructurada y razonada en formato Markdown. Sigue esta estructura exacta y basa **cada punto** en información específica del 'Contexto'. No uses conocimiento externo. No cites fuentes explícitamente, pero asegúrate que todo esté fundamentado en el contexto.\n\n"
                        "---\n\n"
                        "### 1. Valoración General del Potencial\n"
                        "* Resume en una frase el potencial de la idea (ej: \"Potencial Alto\", \"Potencial Moderado con Desafíos Específicos\", \"Bajo Potencial Aparente según Hallazgos\").\n\n"
                        "### 2. Sustento Detallado de la Valoración (Basado en Contexto)\n"
                        "* **Aspectos Positivos:** Justifica tu valoración conectando la idea con necesidades, tensiones o deseos **clave encontrados en los reportes**. Detalla los hallazgos **específicos** que respaldan el potencial de la idea.\n"
                        "* **Posibles Desafíos o Contradicciones:** Menciona cualquier hallazgo en el contexto que pueda representar un obstáculo, riesgo o que contradiga la premisa de la idea.\n\n"
                        "### 3. Sugerencias Clave para Evaluación con Consumidor (Basado en Contexto)\n"
                        "* Identifica 3-4 **hipótesis cruciales** que surgen de los hallazgos (o de vacíos en ellos) y que deben validarse directamente con consumidores. Para cada hipótesis:\n"
                        "    * **Hipótesis:** (Ej: \"Los consumidores realmente valoran [beneficio X] por encima de [beneficio Y] al elegir [categoría de producto]\").\n"
                        "    * **Pregunta Clave:** (Ej: \"¿Qué tan importante es para usted que [producto] le ayude a [beneficio X]? ¿Por qué?\").\n"
                        "    * **Aporte de la Pregunta:** (Ej: \"Validar si el beneficio principal propuesto resuena y es prioritario para el target\")."
                    )

                    response = call_gemini_api(prompt)
                    if response:
                        st.session_state.evaluation_result = response
                        log_query_event(idea_input, mode="Evaluación de Idea")
                        st.rerun()
                    else:
                        st.error("No se pudo generar la evaluación. Inténtalo de nuevo.")


# =====================================================
# PANEL DE ADMINISTRACIÓN (CON EDICIÓN DE USUARIOS)
# =====================================================
def show_admin_dashboard():
    st.subheader("📊 Estadísticas de Uso", divider="rainbow")
    with st.spinner("Cargando estadísticas..."):
        try:
            stats_response = supabase.table("queries").select("user_name, mode, timestamp, query").execute()
            if stats_response.data:
                df_stats = pd.DataFrame(stats_response.data)
                df_stats['timestamp'] = pd.to_datetime(df_stats['timestamp']).dt.tz_localize(None)
                df_stats['date'] = df_stats['timestamp'].dt.date
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Consultas por Usuario (Total)**"); user_counts = df_stats.groupby('user_name')['mode'].count().reset_index(name='Total Consultas').sort_values(by="Total Consultas", ascending=False); st.dataframe(user_counts, use_container_width=True, hide_index=True)
                with col2:
                    st.write("**Consultas por Modo de Uso (Total)**"); mode_counts = df_stats.groupby('mode')['user_name'].count().reset_index(name='Total Consultas').sort_values(by="Total Consultas", ascending=False); st.dataframe(mode_counts, use_container_width=True, hide_index=True)
                st.write("**Actividad Reciente (Últimas 50 consultas)**"); df_recent = df_stats[['timestamp', 'user_name', 'mode', 'query']].sort_values(by="timestamp", ascending=False).head(50); df_recent['timestamp'] = df_recent['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S'); st.dataframe(df_recent, use_container_width=True, hide_index=True)
            else: st.info("Aún no hay datos de uso registrados.")
        except Exception as e: st.error(f"Error al cargar estadísticas: {e}")

    st.subheader("🔑 Gestión de Clientes (Invitaciones)", divider="rainbow")
    try:
        clients_response = supabase.table("clients").select("client_name, plan, invite_code, created_at").order("created_at", desc=True).execute()
        if clients_response.data:
            st.write("**Clientes Actuales**"); df_clients = pd.DataFrame(clients_response.data); df_clients['created_at'] = pd.to_datetime(df_clients['created_at']).dt.strftime('%Y-%m-%d'); st.dataframe(df_clients, use_container_width=True, hide_index=True)
        else: st.info("No hay clientes registrados.")
    except Exception as e: st.error(f"Error al cargar clientes: {e}")

    with st.expander("➕ Crear Nuevo Cliente y Código de Invitación"):
        with st.form("new_client_form"):
            new_client_name = st.text_input("Nombre del Nuevo Cliente"); new_plan = st.selectbox("Plan Asignado", options=list(PLAN_FEATURES.keys()), index=0); new_invite_code = st.text_input("Nuevo Código de Invitación (Ej: CLIENTE2025)")
            submitted = st.form_submit_button("Crear Cliente")
            if submitted:
                if not new_client_name or not new_plan or not new_invite_code: st.warning("Por favor, completa todos los campos.")
                else:
                    try:
                        supabase_admin_client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"]); supabase_admin_client.table("clients").insert({"client_name": new_client_name, "plan": new_plan, "invite_code": new_invite_code}).execute()
                        st.success(f"Cliente '{new_client_name}' creado con éxito. Código: {new_invite_code}")
                    except Exception as e: st.error(f"Error al crear cliente: {e} (¿Código duplicado?)")

    st.subheader("👥 Gestión de Usuarios", divider="rainbow")
    try:
        if "SUPABASE_SERVICE_KEY" not in st.secrets: st.error("Configuración requerida: Falta 'SUPABASE_SERVICE_KEY' en los secretos."); st.stop()
        supabase_admin_client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])
        users_response = supabase_admin_client.table("users").select("id, email, created_at, rol, client_id, clients(client_name, plan)").order("created_at", desc=True).execute()
        if users_response.data:
            st.write("**Usuarios Registrados** (Puedes editar la columna 'Rol')")
            user_list = []
            for user in users_response.data:
                client_info = user.get('clients'); user_list.append({"id": user.get('id'), "email": user.get('email'), "creado_el": user.get('created_at'), "rol": user.get('rol', 'user'), "cliente": client_info.get('client_name') if client_info else "N/A", "plan": client_info.get('plan') if client_info else "N/A"})
            original_df = pd.DataFrame(user_list)
            if 'original_users_df' not in st.session_state: st.session_state.original_users_df = original_df.copy()
            display_df = original_df.copy(); display_df['creado_el'] = pd.to_datetime(display_df['creado_el']).dt.strftime('%Y-%m-%d %H:%M')
            edited_df = st.data_editor(display_df, key="user_editor", column_config={"id": None, "rol": st.column_config.SelectboxColumn("Rol", options=["user", "admin"], required=True), "email": st.column_config.TextColumn("Email", disabled=True), "creado_el": st.column_config.TextColumn("Creado El", disabled=True), "cliente": st.column_config.TextColumn("Cliente", disabled=True), "plan": st.column_config.TextColumn("Plan", disabled=True)}, use_container_width=True, hide_index=True, num_rows="fixed")
            if st.button("Guardar Cambios en Usuarios"):
                updates_to_make = []; original_users = st.session_state.original_users_df; edited_df_indexed = edited_df.set_index(original_df.index); edited_df_with_ids = original_df[['id']].join(edited_df_indexed)
                for index, original_row in original_users.iterrows():
                    edited_rows_match = edited_df_with_ids[edited_df_with_ids['id'] == original_row['id']]
                    if not edited_rows_match.empty:
                        edited_row = edited_rows_match.iloc[0]
                        if original_row['rol'] != edited_row['rol']: updates_to_make.append({"id": original_row['id'], "email": original_row['email'], "new_rol": edited_row['rol']})
                    else: print(f"Advertencia: Fila original con ID {original_row['id']} no encontrada en el dataframe editado.")
                if updates_to_make:
                    success_count = 0; error_count = 0; errors = []
                    with st.spinner(f"Guardando {len(updates_to_make)} cambio(s)..."):
                        for update in updates_to_make:
                            try: supabase_admin_client.table("users").update({"rol": update["new_rol"]}).eq("id", update["id"]).execute(); success_count += 1
                            except Exception as e: errors.append(f"Error al actualizar rol de {update['email']} (ID: {update['id']}): {e}"); error_count += 1
                    if success_count > 0: st.success(f"{success_count} usuario(s) actualizado(s).")
                    if error_count > 0: st.error(f"{error_count} error(es) al guardar:"); [st.error(f"- {err}") for err in errors]
                    del st.session_state.original_users_df; st.rerun()
                else: st.info("No se detectaron cambios en los roles.")
        else: st.info("No hay usuarios registrados.")
    except Exception as e: st.error(f"Error en la gestión de usuarios: {e}")

# =====================================================
# FUNCIÓN PARA EL MODO USUARIO (REFACTORIZADA Y BOTÓN AJUSTADO)
# =====================================================
def run_user_mode(db_full, user_features, footer_html):
    st.sidebar.image("LogoDataStudio.png")
    st.sidebar.write(f"Usuario: {st.session_state.user}")
    if st.session_state.get("is_admin", False): st.sidebar.caption("Rol: Administrador 👑")
    st.sidebar.divider()

    db_filtered = db_full[:]

    modos_disponibles = ["Chat de Consulta Directa"]
    if user_features.get("has_report_generation"): modos_disponibles.insert(0, "Generar un reporte de reportes")
    if user_features.get("has_creative_conversation"): modos_disponibles.append("Conversaciones creativas")
    if user_features.get("has_concept_generation"): modos_disponibles.append("Generación de conceptos")
    if user_features.get("has_idea_evaluation"): modos_disponibles.append("Evaluar una idea")

    st.sidebar.header("Seleccione el modo de uso")
    modo = st.sidebar.radio("Modos:", modos_disponibles, label_visibility="collapsed", key="main_mode_selector")

    if 'current_mode' not in st.session_state: st.session_state.current_mode = modo
    if st.session_state.current_mode != modo:
        reset_chat_workflow()
        st.session_state.pop("generated_concept", None); st.session_state.pop("evaluation_result", None)
        st.session_state.pop("report", None); st.session_state.pop("last_question", None)
        st.session_state.current_mode = modo

    st.sidebar.header("Filtros de Búsqueda")
    marcas_options = sorted({doc.get("filtro", "") for doc in db_full if doc.get("filtro")})
    selected_marcas = st.sidebar.multiselect("Marca(s):", marcas_options, key="filter_marcas")
    if selected_marcas: db_filtered = [d for d in db_filtered if d.get("filtro") in selected_marcas]

    years_options = sorted({doc.get("marca", "") for doc in db_full if doc.get("marca")})
    selected_years = st.sidebar.multiselect("Año(s):", years_options, key="filter_years")
    if selected_years: db_filtered = [d for d in db_filtered if d.get("marca") in selected_years]

    brands_options = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_filtered if extract_brand(d.get("nombre_archivo", ""))})
    selected_brands = st.sidebar.multiselect("Proyecto(s):", brands_options, key="filter_projects")
    if selected_brands: db_filtered = [d for d in db_filtered if extract_brand(d.get("nombre_archivo", "")) in selected_brands]

    # --- AJUSTE AQUÍ ---
    # Botón Cerrar Sesión ajustado
    if st.sidebar.button("Cerrar Sesión", key="logout_main", use_container_width=True):
        supabase.auth.sign_out(); st.session_state.clear(); st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown(footer_html, unsafe_allow_html=True)

    selected_files = [d.get("nombre_archivo") for d in db_filtered]
    if not selected_files and modo != "Generar un reporte de reportes":
         st.warning("⚠️ No hay estudios que coincidan con los filtros seleccionados.")

    if modo == "Generar un reporte de reportes": report_mode(db_filtered, selected_files)
    elif modo == "Conversaciones creativas": ideacion_mode(db_filtered, selected_files)
    elif modo == "Generación de conceptos": concept_generation_mode(db_filtered, selected_files)
    elif modo == "Chat de Consulta Directa": grounded_chat_mode(db_filtered, selected_files)
    elif modo == "Evaluar una idea": idea_evaluator_mode(db_filtered, selected_files)

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
            st.image("LogoDataStudio.png") # Asumiendo que tienes esta imagen
            if st.session_state.page == "login": show_login_page()
            elif st.session_state.page == "signup": show_signup_page()
            elif st.session_state.page == "reset_password": show_reset_password_page()
        st.divider()
        st.markdown(footer_html, unsafe_allow_html=True)
        st.stop()

    try:
        db_full = load_database(st.session_state.cliente)
    except Exception as e:
        st.error(f"Error crítico al cargar la base de datos: {e}"); st.stop()

    user_features = st.session_state.plan_features

    if st.session_state.get("is_admin", False):
        tab_user, tab_admin = st.tabs(["[ 👤 Modo Usuario ]", "[ 👑 Modo Administrador ]"])
        with tab_user: run_user_mode(db_full, user_features, footer_html)
        with tab_admin:
            st.title("Panel de Administración 👑")
            st.write(f"Gestionando como: {st.session_state.user}")
            show_admin_dashboard()
    else:
        run_user_mode(db_full, user_features, footer_html)

if __name__ == "__main__":
    main()
