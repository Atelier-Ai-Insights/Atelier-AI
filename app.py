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

    # --- AJUSTE: Línea divisoria eliminada ---
    # st.divider()

    # Apilar botones verticalmente
    if st.button("¿No tienes cuenta? Regístrate", type="secondary", use_container_width=True):
        st.session_state.page = "signup"
        st.rerun()

    if st.button("¿Olvidaste tu contraseña?", type="secondary", use_container_width=True):
        st.session_state.page = "reset_password"
        st.rerun()
    # --- FIN AJUSTE ---


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
                for idx, li in enumerate(elem.find_all("li", recursive=False), 1): pdf.add_paragraph(f"{idx}. {li.decode_contents(formatter="html")}")
            elif tag_name == "pre":
                 # --- AJUSTE: Usar estilo 'Code' con fallback ---
                 code_content = elem.get_text()
                 try:
                     pdf.add_paragraph(code_content, style='Code') # Intenta usar 'Code'
                 except KeyError:
                     print("Advertencia: Estilo 'Code' no encontrado en PDF stylesheet, usando 'CustomBodyText'.")
                     pdf.add_paragraph(code_content, style='CustomBodyText') # Fallback
                 # --- FIN AJUSTE ---
            elif tag_name == "blockquote": pdf.add_paragraph(">" + elem.decode_contents(formatter="html"))
            else:
                 try: pdf.add_paragraph(elem.decode_contents(formatter="html"))
                 except: pdf.add_paragraph(elem.get_text(strip=True))
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
    return text.replace('&', '&amp;')

class PDFReport:
    def __init__(self, buffer_or_filename, banner_path=None):
        self.banner_path = banner_path
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.doc = SimpleDocTemplate(buffer_or_filename, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=45*mm, bottomMargin=18*mm)
        font_name = 'DejaVuSans' if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Heading1'], fontName=font_name, alignment=1, spaceAfter=12, fontSize=14, leading=18))
        self.styles.add(ParagraphStyle(name='CustomHeading', parent=self.styles['Heading2'], fontName=font_name, spaceBefore=10, spaceAfter=6, fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='CustomBodyText', parent=self.styles['Normal'], fontName=font_name, leading=14, alignment=4, fontSize=11))
        self.styles.add(ParagraphStyle(name='CustomFooter', parent=self.styles['Normal'], fontName=font_name, alignment=2, textColor=colors.grey, fontSize=8))
        # --- AJUSTE: No añadir 'Code' si ya existe ---
        # La línea self.styles.add(ParagraphStyle(name='Code', ...)) fue eliminada.
        # Se usará el estilo 'Code' predeterminado si existe.
        # --- FIN AJUSTE ---

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
        page_num = canvas.getPageNumber(); page_text = f"Página {page_num}"; p_page = Paragraph(page_text, self.styles['CustomFooter'])
        w_page, h_page = p_page.wrap(doc.width, doc.bottomMargin); p_page.drawOn(canvas, doc.width + doc.leftMargin - w_page, 5 * mm)
        canvas.restoreState()
    def header_footer(self, canvas, doc): self.header(canvas, doc); self.footer(canvas, doc)
    def add_paragraph(self, text, style='CustomBodyText'):
        try:
             cleaned_text = text.replace('<br>', '<br/>').replace('<br />', '<br/>').replace('<strong>', '<b>').replace('</strong>', '</b>').replace('<em>', '<i>').replace('</em>', '</i>')
             # Intenta usar el estilo, si falla usa el body text
             try:
                 style_obj = self.styles[style]
             except KeyError:
                 print(f"Advertencia: Estilo '{style}' no encontrado, usando 'CustomBodyText'.")
                 style_obj = self.styles['CustomBodyText']
             p = Paragraph(clean_text(cleaned_text), style_obj)
             self.elements.append(p)
             self.elements.append(Spacer(1, 4))
        except Exception as e:
            print(f"Error adding paragraph: {e}. Text was: {text[:100]}...")
            # Fallback seguro con estilo predeterminado si todo falla
            try:
                self.elements.append(Paragraph(f"Error rendering: {text[:100]}...", self.styles['Normal']))
            except: pass # Evita error si incluso 'Normal' falla

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
        buffer = BytesIO(); pdf = PDFReport(buffer, banner_path=banner_path); pdf.add_title(title, level=1)
        add_markdown_content(pdf, content); pdf.build_pdf(); pdf_data = buffer.getvalue(); buffer.close()
        return pdf_data
    except Exception as e: st.error(f"Error crítico al generar el PDF: {e}"); return None

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
                else: st.error
