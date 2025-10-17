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
# Autenticación con Supabase Auth
# ==============================

### ¡NUEVO! ### - Página de Registro
def show_signup_page():
    st.header("Crear Nueva Cuenta")
    email = st.text_input("Tu Correo Electrónico")
    password = st.text_input("Crea una Contraseña", type="password")

    # Obtener la lista de clientes para el dropdown
    clients_response = supabase.table("clients").select("id, client_name").execute()
    clients_data = clients_response.data
    client_options = {client['client_name']: client['id'] for client in clients_data}
    
    selected_client_name = st.selectbox("Selecciona tu empresa", options=client_options.keys())

    if st.button("Registrarse"):
        if not email or not password or not selected_client_name:
            st.error("Por favor, completa todos los campos.")
            return
        
        try:
            # 1. Registra al usuario en el sistema de autenticación de Supabase
            auth_response = supabase.auth.sign_up({
                "email": email,
                "password": password,
            })
            
            # 2. Inserta el perfil del usuario en tu tabla 'users'
            new_user_id = auth_response.user.id
            selected_client_id = client_options[selected_client_name]

            supabase.table("users").insert({
                "id": new_user_id,
                "email": email,
                "client_id": selected_client_id
            }).execute()

            st.success("¡Registro exitoso! Revisa tu correo para confirmar tu cuenta.")
            st.info("Una vez confirmada, podrás iniciar sesión.")

        except Exception as e:
            st.error(f"Error en el registro: Es posible que el correo ya esté en uso.")

### ¡MODIFICADO! ### - Lógica de login usando Supabase Auth
def show_login_page():
    st.header("Iniciar Sesión")
    email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
    password = st.text_input("Contraseña", type="password", placeholder="****")

    if st.button("Ingresar"):
        try:
            # 1. Autentica al usuario con Supabase Auth
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            user_id = response.user.id

            # 2. Busca el perfil del usuario para obtener el cliente
            user_profile = supabase.table("users").select("*, clients(client_name, plan)").eq("id", user_id).single().execute()
            
            if user_profile.data and user_profile.data.get('clients'):
                client_info = user_profile.data['clients']
                st.session_state.logged_in = True
                st.session_state.user = user_profile.data['email']
                st.session_state.cliente = client_info['client_name'].lower()
                st.session_state.plan = client_info.get('plan', 'Explorer')
                st.session_state.plan_features = PLAN_FEATURES.get(st.session_state.plan, PLAN_FEATURES['Explorer'])
                st.rerun()
            else:
                st.error("Perfil de usuario no encontrado. Contacta al administrador.")
        except Exception as e:
            st.error("Credenciales incorrectas o cuenta no confirmada.")
    
    if st.button("¿No tienes cuenta? Regístrate", type="secondary"):
        st.session_state.page = "signup"
        st.rerun()

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

generation_config = {"temperature": 0.5, "top_p": 0.8, "top_k": 32, "max_output_tokens": 8192}
safety_settings = [
    {"category": c, "threshold": "BLOCK_ONLY_HIGH"} for c in
    ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]
]

def create_model():
    return genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=generation_config, safety_settings=safety_settings)

model = create_model()

def call_gemini_api(prompt):
    try:
        response = model.generate_content([prompt])
        return html.unescape(response.text)
    except Exception as e:
        print("----------- ERROR DETALLADO DE GEMINI -----------")
        print(e)
        print("-----------------------------------------------")
        st.error(f"Error en la llamada a Gemini: {e}.")
        return None

# ==============================
# RASTREO DE USO
# ==============================
def log_query_event(query_text, mode, rating=None):
    data = {"id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"), "user_name": st.session_state.user, "timestamp": datetime.datetime.now().isoformat(), "mode": mode, "query": query_text, "rating": rating}
    supabase.table("queries").insert(data).execute()

def get_monthly_usage(username, action_type):
    first_day_of_month = datetime.date.today().replace(day=1)
    response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", str(first_day_of_month)).execute()
    return response.count

def get_daily_usage(username, action_type):
    today_start = datetime.datetime.now().strftime("%Y-%m-%d 00:00:00")
    response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", today_start).execute()
    return response.count

# ==============================
# FUNCIONES AUXILIARES Y DE PDF
# ==============================
def normalize_text(text):
    if not text: return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()

def add_markdown_content(pdf, markdown_text):
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

@st.cache_data(show_spinner=False)
def load_database(cliente: str):
    s3 = boto3.client("s3", endpoint_url=st.secrets["S3_ENDPOINT_URL"], aws_access_key_id=st.secrets["S3_ACCESS_KEY"], aws_secret_access_key=st.secrets["S3_SECRET_KEY"])
    response = s3.get_object(Bucket=st.secrets.get("S3_BUCKET"), Key="resultado_presentacion (1).json")
    data = json.loads(response["Body"].read().decode("utf-8"))
    cliente_norm = normalize_text(cliente or "")
    if cliente_norm != "insights-atelier":
        data = [doc for doc in data if "atelier" in normalize_text(doc.get("cliente", "")) or cliente_norm in normalize_text(doc.get("cliente", ""))]
    return data

def extract_brand(filename):
    if not filename or "In-ATL_" not in filename: return ""
    return filename.split("In-ATL_")[1].rsplit(".", 1)[0]

def get_relevant_info(db, question, selected_files):
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"
            for grupo in pres.get("grupos", []):
                all_text += f"Grupo {grupo.get('grupo_index')}: {grupo.get('contenido_texto', '')}\n"
                if grupo.get("metadatos"): all_text += f"Metadatos: {json.dumps(grupo.get('metadatos'), ensure_ascii=False)}\n"
                if grupo.get("hechos"): all_text += f"Hechos: {json.dumps(grupo.get('hechos'), ensure_ascii=False)}\n"
            all_text += "\n---\n\n"
    return all_text

banner_file = "Banner (2).jpg"

def clean_text(text):
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;')

class PDFReport:
    def __init__(self, buffer_or_filename, banner_path=None):
        self.banner_path = banner_path
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.doc = SimpleDocTemplate(buffer_or_filename, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=45*mm, bottomMargin=18*mm)
        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Heading1'], alignment=1, spaceAfter=12, fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='CustomHeading', parent=self.styles['Heading2'], spaceBefore=10, spaceAfter=6, fontSize=12, leading=16))
        self.styles.add(ParagraphStyle(name='CustomBodyText', parent=self.styles['Normal'], leading=14, alignment=4, fontSize=12))
        self.styles.add(ParagraphStyle(name='CustomFooter', parent=self.styles['Normal'], alignment=2, textColor=colors.grey, fontSize=6))
        for style_name in ['CustomTitle', 'CustomHeading', 'CustomBodyText', 'CustomFooter']: self.styles[style_name].fontName = 'DejaVuSans'
    def header(self, canvas, doc):
        canvas.saveState()
        if self.banner_path and os.path.isfile(self.banner_path):
            try:
                img_w, img_h = 210*mm, 35*mm
                y_pos = A4[1] - img_h
                canvas.drawImage(self.banner_path, 0, y_pos, width=img_w, height=img_h, preserveAspectRatio=True, anchor='n')
            except: pass
        canvas.restoreState()
    def footer(self, canvas, doc):
        canvas.saveState()
        footer_text = "El uso de esta información está sujeto a términos y condiciones... Verifica las respuestas."
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
        p = Paragraph(clean_text(text), self.styles['CustomHeading'])
        self.elements += [p, Spacer(1, 12)]
    def build_pdf(self):
        self.doc.build(self.elements, onFirstPage=self.header_footer, onLaterPages=self.header_footer)

def generate_pdf_html(content, title="Documento Final", banner_path=None):
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
        st.error(f"Error al generar el PDF: {e}")
        return None

# =====================================================
# MODOS DE LA APLICACIÓN
# =====================================================

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
    return f"{question}\n\n" + result2
    
def report_mode(db, selected_files):
    st.markdown("### Generar Reporte de Reportes")
    if "report" in st.session_state and st.session_state["report"]:
        st.markdown("---")
        st.markdown("### Informe Generado")
        st.markdown(st.session_state["report"])
        st.markdown("---")
    question = st.text_area("Escribe tu consulta para el reporte…", value="", height=150, key="report_question")
    if st.button("Generar Reporte"):
        report_limit = st.session_state.plan_features['reports_per_month']
        current_reports = get_monthly_usage(st.session_state.user, "Generar un reporte de reportes")
        if current_reports >= report_limit:
            st.error(f"Has alcanzado tu límite de {int(report_limit)} reportes este mes.")
            st.warning("🚀 ¡Actualiza tu plan para generar más reportes!")
            return
        if not question.strip():
            st.warning("Por favor, ingresa una consulta para generar el reporte.")
        else:
            st.session_state["last_question"] = question
            with st.spinner("Generando informe..."):
                report = generate_final_report(question, db, selected_files)
            
            if report is None:
                st.error("No se pudo generar el informe. Revisa la terminal para ver el error detallado.")
                st.session_state.pop("report", None)
            else:
                st.session_state["report"] = report
                log_query_event(question, mode="Generar un reporte de reportes")
                st.rerun()

    if "report" in st.session_state and st.session_state["report"]:
        pdf_bytes = generate_pdf_html(st.session_state["report"], title="Informe Final", banner_path=banner_file)
        col1, col2 = st.columns(2)
        with col1:
            if pdf_bytes: st.download_button("Descargar Informe en PDF", data=pdf_bytes, file_name="Informe_AtelierIA.pdf", mime="application/pdf", use_container_width=True)
        with col2:
            st.button("Nueva consulta", on_click=reset_report_workflow, key="new_report_query_btn", use_container_width=True)

def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    st.markdown("Realiza preguntas específicas y obtén respuestas concretas basadas únicamente en los hallazgos de los informes seleccionados.")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    for msg in st.session_state.chat_history: st.markdown(f"**{msg['role'].capitalize()}:** {msg['message']}")
    user_input = st.text_area("Escribe tu pregunta...", height=150)
    if st.button("Enviar Pregunta"):
        query_limit = st.session_state.plan_features['chat_queries_per_day']
        current_queries = get_daily_usage(st.session_state.user, "Chat de Consulta Directa")
        if current_queries >= query_limit:
            st.error(f"Has alcanzado tu límite de {int(query_limit)} consultas diarias.")
            st.warning("🚀 ¡Actualiza tu plan para tener consultas ilimitadas!")
            return
        if not user_input.strip():
            st.warning("Por favor, ingresa una pregunta para continuar.")
        else:
            st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
            relevant_info = get_relevant_info(db, user_input, selected_files)
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history)
            grounded_prompt = (
                f"**Tarea:** Eres un **asistente de Inteligencia Artificial**. Tu misión es **sintetizar** y **articular** información proveniente de múltiples estudios de mercado para ofrecer una respuesta concreta a la pregunta formulada, de manera clara, completa y bien articulada. Tu única fuente de conocimiento es la 'Información documentada en los reportes' proporcionada.\n\n"
                f"**Historial de la Conversación:**\n{conversation_history}\n\n"
                f"**Información documentada en los reportes (Única fuente de verdad):**\n{relevant_info}\n\n"
                "**Instrucciones Estrictas:**\n"
                "1.  **Síntesis Integral (Instrucción Clave):** Tu objetivo principal es conectar y relacionar hallazgos de **TODOS los reportes relevantes** para construir una respuesta completa. Asegúrate de agrupar los hallazgos por temas que respondan a la pregunta del cliente y que sume valor para responder a la pregunta.\n"
                "2.  **Estructura de la Respuesta:** Redacta un parrafo corto dando una respuesta corta clara y concreta a la solicitud realizada incluyendo principalmente hallazgos que sustenten la respuesta que se da para responder la pregunta. Utiliza solo información relevante asociada a los hallazgos. NO utilices información de la metodología ni de los objetivos, solo utiliza información relacionada en los hallazgos.\n"
                "3.  **Fidelidad Absoluta:** Basa tu respuesta EXCLUSIVAMENTE en la 'Información documentada en los reportes'. NO utilices conocimiento externo ni hagas suposiciones.\n"
                "4.  **Manejo de Información Faltante:** Si la respuesta no se encuentra en el contexto, indica claramente: \"La información solicitada no se encuentra disponible en los documentos analizados.\" No intentes inventar una respuesta.\n"
                "5.  **Identificación de la marca y el producto EXACTO:** Cuando se pregunte por una marca (ejemplo: oreo) o por una categoría (ejemplo: galletas saladas) siempre traer información ÚNICAMENTE de los reportes relacionados. Identifica en la pregunta la marca y/o el producto exacto sobre el cual se hace la consulta y sé muy específico y riguroso al incluir y referenciar la información asociada a la marca y/o producto mencionado en la consulta (por ejemplo: diferenciar galletas dulces de galletas saladas).\n"
                "6.  **Referencias:** NO es necesario citar las fuentes, esto para garantizar que la lectura sea fuída.\n\n"
                "**Respuesta:**"
            )
            with st.spinner("Buscando en los reportes..."):
                response = call_gemini_api(grounded_prompt)
            if response:
                st.session_state.chat_history.append({"role": "Asistente", "message": response})
                log_query_event(user_input, mode="Chat de Consulta Directa")
                st.rerun()
            else:
                st.error("Error al generar la respuesta.")
    if st.session_state.chat_history:
        pdf_bytes = generate_pdf_html("\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial de Consulta Directa", banner_path=banner_file)
        if pdf_bytes: st.download_button("Descargar Chat en PDF", data=pdf_bytes, file_name="chat_consulta.pdf", mime="application/pdf")
        st.button("Nueva Conversación", on_click=reset_chat_workflow, key="new_grounded_chat_btn")

def ideacion_mode(db, selected_files):
    st.subheader("Conversaciones Creativas")
    st.markdown("Este es un espacio para explorar ideas novedosas. Basado en los hallazgos, el asistente te ayudará a generar conceptos creativos.")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    for msg in st.session_state.chat_history: st.markdown(f"**{msg['role'].capitalize()}:** {msg['message']}")
    user_input = st.text_area("Lanza una idea o pregunta para iniciar la conversación...", height=150)
    if st.button("Enviar"):
        if not user_input.strip():
            st.warning("Por favor, ingresa tu pregunta para continuar.")
        else:
            st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
            relevant = get_relevant_info(db, user_input, selected_files)
            conv_prompt = (
                "Historial de conversación:\n"
                + "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history)
                + "\n\nInformación de contexto:\n" + relevant
                + "\n\nInstrucciones:\n"
                "- Responde usando únicamente la sección de resultados de los reportes.\n"
                "- Responde de forma creativa, eres un experto en marketing, así que ayudarás al usuario que esta hablando contigo a conversar con sus datos para ofrecerle una solución creativa a su problema o situación, esto lo harás basado en la información y en los datos que hay sobre la temática que te está solicitando. comienza siempre dando un breve resumen de los proyectos relacionados con la solicitud\n"
                "- Escribe de forma clara, sintética y concreta\n"
                "- Incluye citas numeradas al estilo IEEE (por ejemplo, [1]).\n\n"
                "Respuesta detallada:"
            )
            with st.spinner("Generando respuesta creativa..."):
                resp = call_gemini_api(conv_prompt)
            if resp:
                st.session_state.chat_history.append({"role": "Asistente", "message": resp})
                log_query_event(user_input, mode="Conversaciones creativas")
                st.rerun()
            else:
                st.error("Error al generar la respuesta.")
    if st.session_state.chat_history:
        pdf_bytes = generate_pdf_html("\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial de Chat Creativo", banner_path=banner_file)
        if pdf_bytes: st.download_button("Descargar Chat en PDF", data=pdf_bytes, file_name="chat_creativo.pdf", mime="application/pdf")
        st.button("Nueva conversación", on_click=reset_chat_workflow, key="new_chat_btn")

def concept_generation_mode(db, selected_files):
    st.subheader("Generación de Conceptos")
    st.markdown("A partir de una idea inicial y los hallazgos, generaremos un concepto de producto o servicio.")
    product_idea = st.text_area("Describe tu idea de producto o servicio:", height=150, placeholder="Ej: Un snack saludable para niños...")
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
                    "Genera una respuesta en formato Markdown con la siguiente estructura exacta. Basa tus respuestas en los hallazgos relevantes del contexto proporcionado. Sé claro, conciso y accionable.\n\n"
                    "---\n\n"
                    "### 1. Definición de la Necesidad del Consumidor\n"
                    "* Identifica y describe las tensiones, deseos o problemas clave de los consumidores que se encuentran en el **Contexto de los estudios**. Conecta estos hallazgos con la oportunidad para la idea de producto o servicio.\n\n"
                    "### 2. Descripción del Producto\n"
                    "* Basado en la **Idea del Usuario**, describe el producto o servicio propuesto. Detalla sus características principales y cómo funcionaría. Sé creativo pero mantente anclado en la necesidad insatisfecha detectada.\n\n"
                    "### 3. Beneficios Clave\n"
                    "* Enumera 3-4 beneficios principales del producto. Cada beneficio debe responder directamente a una de las necesidades del consumidor identificadas en el punto 1 y estar sustentado por la evidencia del **Contexto**. Los beneficios pueden ser funcionales, racionales o emocionales.\n\n"
                    "### 4. Conceptos para evaluar\n"
                    "* Entrega dos opciones de concepto resumido. Estos deben ser memorables y para su redacción se deben considerar tres frases o párrafos: Insight (primero decir el dolor del consumidor y luego especificar lo que le gustaría tener como resultado), What (Caracteristicas y beneficios del producto o servicio), Reason To Belive (por qué el producto puede resolver la tensión). Cierra el resumen con un claim, este debe captar la esencia del producto o servidio y se debe redactar de manera sucinta: corto pero con con mucho significado."
                )
                response = call_gemini_api(prompt)
                if response:
                    st.session_state.generated_concept = response
                    log_query_event(product_idea, mode="Generación de conceptos")
                else:
                    st.error("No se pudo generar el concepto.")
    if "generated_concept" in st.session_state:
        st.markdown("---")
        st.markdown("### Concepto Generado")
        st.markdown(st.session_state.generated_concept)
        if st.button("Generar un nuevo concepto"):
            st.session_state.pop("generated_concept")
            st.rerun()

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
        idea_input = st.text_area("Describe la idea que quieres evaluar:", height=150, placeholder="Ej: Una línea de yogures con probióticos...")
        if st.button("Evaluar Idea"):
            if not idea_input.strip():
                st.warning("Por favor, describe una idea para continuar.")
            else:
                with st.spinner("Evaluando el potencial de la idea..."):
                    context_info = get_relevant_info(db, idea_input, selected_files)
                    prompt = (
                        f"**Tarea:** Eres un estratega de mercado y analista de innovación. Tu objetivo es evaluar el potencial de una idea de producto o servicio, basándote exclusivamente en los hallazgos de un conjunto de estudios de mercado.\n\n"
                        f'**Idea a Evaluar:**\n"{idea_input}"\n\n'
                        f'**Contexto (Hallazgos de Estudios de Mercado):**\n"{context_info}"\n\n'
                        "**Instrucciones:**\n"
                        "Genera una evaluación estructurada y razonada en formato Markdown. Sigue esta estructura exacta y basa cada punto en la información del 'Contexto'. Mencionar de manera general que la evaluación se estructura a través de estudios realizados por Atelier, no es necesario incluir citas.\n\n"
                        "---\n\n"
                        "### 1. Valoración del Potencial\n"
                        "* Resume en una frase el potencial de la idea (ej: \"Potencial Alto\", \"Potencial Moderado con Desafíos\", \"Bajo Potencial\").\n\n"
                        "### 2. Sustento de la Valoración\n"
                        "* Justifica tu valoración conectando la idea con las necesidades, tensiones o deseos clave encontrados en los reportes. Detalla los hallazgos específicos (positivos y negativos) que sustentan tu conclusión. NO es necesario citar las fuentes, esto para garantizar que la lectura sea fuída.\n\n"
                        "### 3. Sugerencias para la Evaluación con Consumidor\n"
                        "* Basado en los hallazgos y en los posibles vacíos de información, proporciona una lista de 3 a 4 hipótesis, acompañadas de una pregunta clave que se deberían validar al momento de evaluar la idea directamente con los consumidores, y luego decir en qué aporta esa pregunta."
                    )
                    response = call_gemini_api(prompt)
                    if response:
                        st.session_state.evaluation_result = response
                        log_query_event(idea_input, mode="Evaluación de Idea")
                        st.rerun()
                    else:
                        st.error("No se pudo generar la evaluación.")

# =====================================================
# FUNCIÓN PRINCIPAL DE LA APLICACIÓN
# =====================================================
def main():
    if not st.session_state.get("logged_in"):
        # Se renombra 'show_login' a 'show_login_page' para consistencia
        show_login_page() 

    # --- Lógica de la aplicación principal cuando el usuario está logueado ---
    st.sidebar.image("LogoDataStudio.png")
    st.sidebar.write(f"Usuario: {st.session_state.user}")
    st.sidebar.divider()
    
    try:
        db_full = load_database(st.session_state.cliente)
    except Exception as e:
        st.error(f"Error crítico al cargar la base de datos: {e}")
        st.stop()
    
    db_filtered = db_full[:]
    user_features = st.session_state.plan_features
    
    modos_disponibles = ["Chat de Consulta Directa"]
    if user_features.get("has_report_generation"): modos_disponibles.insert(0, "Generar un reporte de reportes")
    if user_features.get("has_creative_conversation"): modos_disponibles.append("Conversaciones creativas")
    if user_features.get("has_concept_generation"): modos_disponibles.append("Generación de conceptos")
    if user_features.get("has_idea_evaluation"): modos_disponibles.append("Evaluar una idea")

    st.sidebar.header("Seleccione el modo de uso")
    modo = st.sidebar.radio("Modos:", modos_disponibles, label_visibility="collapsed")

    if st.session_state.get('current_mode') != modo:
        st.session_state.current_mode = modo
        reset_chat_workflow()
        st.session_state.pop("generated_concept", None)
        st.session_state.pop("evaluation_result", None)

    st.sidebar.header("Filtros de Búsqueda")
    marcas_options = sorted({doc.get("filtro", "") for doc in db_full if doc.get("filtro")})
    selected_marcas = st.sidebar.multiselect("Seleccione la(s) marca(s):", marcas_options)
    if selected_marcas: db_filtered = [d for d in db_filtered if d.get("filtro") in selected_marcas]

    years_options = sorted({doc.get("marca", "") for doc in db_full if doc.get("marca")})
    selected_years = st.sidebar.multiselect("Seleccione el/los año(s):", years_options)
    if selected_years: db_filtered = [d for d in db_filtered if d.get("marca") in selected_years]

    brands_options = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_filtered})
    selected_brands = st.sidebar.multiselect("Seleccione el/los proyecto(s):", brands_options)
    if selected_brands: db_filtered = [d for d in db_filtered if extract_brand(d.get("nombre_archivo", "")) in selected_brands]

    if modo == "Generar un reporte de reportes":
        st.sidebar.radio("Califique el informe:", [1, 2, 3, 4, 5], horizontal=True, key="rating")

    if st.sidebar.button("Cerrar Sesión", key="logout_main"):
        supabase.auth.sign_out() # Se añade el logout de Supabase
        st.session_state.clear()
        st.rerun()

    selected_files = [d.get("nombre_archivo") for d in db_filtered]

    if modo == "Generar un reporte de reportes": report_mode(db_filtered, selected_files)
    elif modo == "Conversaciones creativas": ideacion_mode(db_filtered, selected_files)
    elif modo == "Generación de conceptos": concept_generation_mode(db_filtered, selected_files)
    elif modo == "Chat de Consulta Directa": grounded_chat_mode(db_filtered, selected_files)
    elif modo == "Evaluar una idea": idea_evaluator_mode(db_filtered, selected_files)

if __name__ == "__main__":
    main()
