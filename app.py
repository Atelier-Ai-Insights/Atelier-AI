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
from supabase import create_client
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
# Autenticación Personalizada
# ==============================
def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.header("Iniciar Sesión")
        email = st.text_input("Correo Electrónico", placeholder="usuario@empresa.com")
        password = st.text_input("Contraseña", type="password", placeholder="****")
        if st.button("Ingresar"):
            response = supabase.table("users").select("*, clients(client_name, plan)").eq("email", email).eq("password", password).execute()

            if response.data:
                user_data = response.data[0]
                client_info = user_data.get('clients')

                if not client_info:
                    st.error("Error: Usuario no está asociado a ningún cliente.")
                    return

                st.session_state.logged_in = True
                st.session_state.user = user_data['email']
                st.session_state.cliente = client_info['client_name'].lower()
                
                user_plan = client_info.get('plan', 'Explorer')
                st.session_state.plan = user_plan
                st.session_state.plan_features = PLAN_FEATURES.get(user_plan, PLAN_FEATURES['Explorer'])
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()


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
    return genai.GenerativeModel(model_name="gemini-1.5-flash", generation_config=generation_config, safety_settings=safety_settings)

model = create_model()

### DIAGNÓSTICO ### - Modificamos esta función para que imprima el error real en la terminal
def call_gemini_api(prompt):
    try:
        response = model.generate_content([prompt])
        return html.unescape(response.text)
    except Exception as e:
        # Esto imprimirá el error detallado en la ventana de la terminal
        print("----------- ERROR DETALLADO DE GEMINI -----------")
        print(e)
        print("-----------------------------------------------")
        st.error(f"Error en la llamada a Gemini: {e}.")
        return None

# ==============================
# CONEXIÓN A SUPABASE Y RASTREO
# ==============================
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

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

### DIAGNÓSTICO ### - Se restauraron los prompts y se añadieron prints de diagnóstico
def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)
    
    # Imprimimos el tamaño de la información de contexto para ver si es demasiado grande
    print(f"DIAGNÓSTICO: El tamaño de 'relevant_info' es de {len(relevant_info)} caracteres.")

    prompt1 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones:\n"
        "1. Identifica en la pregunta la marca exacta y/o el producto exacto...\n"
        # ... (resto del prompt 1)
    )
    print("DIAGNÓSTICO: Intentando llamar a la API con prompt1.")
    result1 = call_gemini_api(prompt1)
    if result1 is None: 
        print("DIAGNÓSTICO: La llamada con prompt1 falló.")
        return None
    print("DIAGNÓSTICO: La llamada con prompt1 fue exitosa.")

    prompt2 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones Generales:\n"
        "1. Identifica en la pregunta la marca y/o el producto exacto...\n"
        # ... (resto del prompt 2)
    )
    print("DIAGNÓSTICO: Intentando llamar a la API con prompt2.")
    result2 = call_gemini_api(prompt2)
    if result2 is None:
        print("DIAGNÓSTICO: La llamada con prompt2 falló.")
        return None
    print("DIAGNÓSTICO: La llamada con prompt2 fue exitosa.")
    
    informe_completo = f"{question}\n\n" + result2
    return informe_completo
    
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
    #... (código sin cambios)
    pass
def ideacion_mode(db, selected_files):
    #... (código sin cambios)
    pass
def concept_generation_mode(db, selected_files):
    #... (código sin cambios)
    pass
def idea_evaluator_mode(db, selected_files):
    #... (código sin cambios)
    pass

# =====================================================
# FUNCIÓN PRINCIPAL DE LA APLICACIÓN
# =====================================================
def main():
    if not st.session_state.get("logged_in"):
        show_login()

    st.sidebar.image("LogoDataStudio.png")
    
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
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()

    selected_files = [d.get("nombre_archivo") for d in db_filtered]

    if modo == "Generar un reporte de reportes": report_mode(db_filtered, selected_files)
    elif modo == "Conversaciones creativas": ideacion_mode(db_filtered, selected_files)
    elif modo == "Generación de conceptos": concept_generation_mode(db_filtered, selected_files)
    elif modo == "Chat de Consulta Directa": grounded_chat_mode(db_filtered, selected_files)
    elif modo == "Evaluar una idea": idea_evaluator_mode(db_filtered, selected_files)

if __name__ == "__main__":
    main()
