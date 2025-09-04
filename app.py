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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus.doctemplate import LayoutError
from supabase import create_client
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# Registrar fuente Unicode para tildes/ñ
# Asegúrate de tener el archivo 'DejaVuSans.ttf' en el mismo directorio o proporciona la ruta correcta.
if os.path.exists('DejaVuSans.ttf'):
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    FONT_NAME = 'DejaVuSans'
else:
    # Si no se encuentra DejaVuSans, ReportLab usará una fuente predeterminada.
    # Esto puede causar problemas con caracteres especiales en el PDF.
    FONT_NAME = 'Helvetica'


# ==============================
# Autenticación Personalizada
# ==============================
ALLOWED_USERS = st.secrets.get("ALLOWED_USERS", {})

def show_login():
    st.markdown(
        "<div style='display: flex; flex-direction: column; justify-content: center; align-items: center;'>",
        unsafe_allow_html=True,
    )
    st.header("Iniciar Sesión")
    username = st.text_input("Usuario", placeholder="Apple")
    password = st.text_input("Contraseña (4 dígitos)", type="password", placeholder="0000")
    if st.button("Ingresar"):
        if username in ALLOWED_USERS and password == ALLOWED_USERS[username]:
            st.session_state.logged_in = True
            st.session_state.user = username
            st.session_state.cliente = username.lower()
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# ==============================
# Helpers para Reiniciar Flujos
# ==============================
def reset_report_workflow():
    """Limpia el estado del flujo de 'Generar un reporte'."""
    keys_to_pop = ["report", "last_question", "report_question", "personalization", "rating"]
    for k in keys_to_pop:
        st.session_state.pop(k, None)

def reset_chat_workflow():
    """Limpia el estado del flujo de 'Conversaciones creativas'."""
    st.session_state.pop("chat_history", None)

def reset_concept_workflow():
    """Limpia el estado del flujo de 'Generación de conceptos'."""
    keys_to_pop = ["generated_concept", "concept_idea"]
    for k in keys_to_pop:
        st.session_state.pop(k, None)


# ==============================
# Configuración de la API de Gemini
# ==============================
api_keys = [st.secrets["API_KEY_1"], st.secrets["API_KEY_2"], st.secrets["API_KEY_3"]]
current_api_key_index = 0

def configure_api():
    global current_api_key_index
    genai.configure(api_key=api_keys[current_api_key_index])

configure_api()

generation_config = {
    "temperature": 0.5, "top_p": 0.8, "top_k": 32, "max_output_tokens": 8192,
}
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
]

def create_model():
    return genai.GenerativeModel(
        model_name="gemini-1.5-flash", # Modelo actualizado recomendado
        generation_config=generation_config,
        safety_settings=safety_settings,
    )

model = create_model()

def switch_api_key():
    global current_api_key_index, model
    current_api_key_index = (current_api_key_index + 1) % len(api_keys)
    configure_api()
    model = create_model()
    st.toast(f"Cambiando a API Key #{current_api_key_index + 1}")

def call_gemini_api(prompt):
    try:
        response = model.generate_content([prompt])
        text = response.text
        return html.unescape(text)
    except Exception as e:
        st.error(f"Error en la llamada a Gemini: {e}. Intentando con otra API Key.")
        switch_api_key()
        try:
            response = model.generate_content([prompt])
            text = response.text
            return html.unescape(text)
        except Exception as e2:
            st.error(f"Error grave en la llamada a Gemini tras reintento: {e2}")
            return None


# ==============================
# Conexión a Supabase para Guardar Consultas
# ==============================
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def log_query_event(query_text, mode, rating=None):
    try:
        data = {
            "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "user_name": st.session_state.get("user", "desconocido"),
            "timestamp": datetime.datetime.now().isoformat(),
            "mode": mode,
            "query": query_text,
            "rating": rating,
        }
        supabase.table("queries").insert(data).execute()
    except Exception as e:
        st.warning(f"No se pudo registrar el evento: {e}")


# ==============================
# Normalización y Carga de Datos
# ==============================
def normalize_text(text):
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()

@st.cache_data(show_spinner="Cargando base de conocimiento...")
def load_database(cliente: str):
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key = st.secrets["S3_SECRET_KEY"]
    bucket_name = st.secrets.get("S3_BUCKET")
    object_key = "resultado_presentacion (1).json"
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=s3_endpoint_url,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
        )
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        cliente_norm = normalize_text(cliente)
        if cliente_norm != "insights-atelier":
            data = [
                doc for doc in data
                if "atelier" in normalize_text(doc.get("cliente", "")) or
                   cliente_norm in normalize_text(doc.get("cliente", ""))
            ]
        return data
    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        return []


# ==============================
# Clases y Funciones para PDF
# ==============================
def clean_text_for_pdf(text):
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;')

class PDFReport:
    def __init__(self, filename, banner_path=None):
        self.filename = filename
        self.banner_path = banner_path
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.doc = SimpleDocTemplate(
            self.filename, pagesize=A4,
            rightMargin=12*mm, leftMargin=12*mm,
            topMargin=45*mm, bottomMargin=18*mm
        )
        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Heading1'], alignment=1, spaceAfter=12, fontName=FONT_NAME))
        self.styles.add(ParagraphStyle(name='CustomHeading', parent=self.styles['Heading2'], spaceBefore=10, spaceAfter=6, fontName=FONT_NAME))
        self.styles.add(ParagraphStyle(name='CustomBodyText', parent=self.styles['Normal'], leading=14, alignment=4, fontName=FONT_NAME))
        self.styles.add(ParagraphStyle(name='CustomFooter', parent=self.styles['Normal'], alignment=1, textColor=colors.grey, fontSize=8, fontName=FONT_NAME))

    def header(self, canvas, doc):
        canvas.saveState()
        if self.banner_path and os.path.exists(self.banner_path):
            img_w, img_h = 210*mm, 35*mm
            y_pos = A4[1] - img_h
            canvas.drawImage(self.banner_path, 0, y_pos, width=img_w, height=img_h, preserveAspectRatio=True, anchor='n')
            line_y = y_pos - 5*mm
            canvas.setStrokeColor(colors.lightgrey)
            canvas.line(12*mm, line_y, A4[0]-12*mm, line_y)
        canvas.restoreState()

    def footer(self, canvas, doc):
        canvas.saveState()
        footer_text = (
            "El uso de esta información está sujeto a los términos y condiciones que rigen su suscripción. "
            "Es su responsabilidad asegurarse que el uso de esta información no infrinja los derechos de propiedad intelectual."
        )
        p = Paragraph(footer_text, self.styles['CustomFooter'])
        w, h = p.wrap(doc.width, doc.bottomMargin)
        p.drawOn(canvas, doc.leftMargin, 10*mm)
        page_num_text = f"Página {doc.page}"
        canvas.setFont(FONT_NAME, 9)
        canvas.drawRightString(A4[0] - 12*mm, 10*mm, page_num_text)
        canvas.restoreState()

    def add_paragraph(self, text, style='CustomBodyText'):
        p = Paragraph(clean_text_for_pdf(text), self.styles[style])
        self.elements.extend([p, Spacer(1, 6)])

    def add_title(self, text, level=1):
        style = 'CustomTitle' if level == 1 else 'CustomHeading'
        p = Paragraph(clean_text_for_pdf(text), self.styles[style])
        self.elements.extend([p, Spacer(1, 12)])

    def build_pdf(self):
        try:
            self.doc.build(self.elements, onFirstPage=lambda c, d: [self.header(c, d), self.footer(c, d)], onLaterPages=lambda c, d: [self.header(c, d), self.footer(c, d)])
        except LayoutError as e:
            st.error(f"Error al generar el PDF: {e}")

def add_markdown_to_pdf(pdf, markdown_text):
    html_text = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "tables", "break-on-newline", "smarty-pants"])
    soup = BeautifulSoup(html_text.replace('\n', '<br/>'), "html.parser")
    for elem in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'li']):
        if elem.name in ['h1', 'h2', 'h3', 'h4']:
            pdf.add_title(elem.get_text(strip=True), level=int(elem.name[1]))
        elif elem.name == 'p':
            pdf.add_paragraph(elem.decode_contents())
        elif elem.name == 'ul':
            for li in elem.find_all("li", recursive=False):
                pdf.add_paragraph(f"• {li.decode_contents().strip()}")
        elif elem.name == 'ol':
            for i, li in enumerate(elem.find_all("li", recursive=False), 1):
                pdf.add_paragraph(f"{i}. {li.decode_contents().strip()}")

def generate_pdf_from_markdown(content, title, banner_path=None):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf = PDFReport(tmp.name, banner_path=banner_path)
        add_markdown_to_pdf(pdf, content)
        pdf.build_pdf()
        tmp.seek(0)
        pdf_bytes = tmp.read()
    os.unlink(tmp.name)
    return pdf_bytes

# ==============================
# Lógica de los Modos de la App
# ==============================
def get_relevant_info(db, selected_files):
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'N/A'))}\n"
            for grupo in pres.get("grupos", []):
                contenido = grupo.get("contenido_texto", "")
                all_text += f"Contenido: {contenido}\n"
            all_text += "\n---\n\n"
    return all_text

def report_mode(db, selected_files):
    st.markdown("### Generar un Reporte de Reportes")
    question = st.text_area("Escribe tu consulta...", height=150, key="report_question")
    if st.button("Generar Reporte"):
        if not question.strip():
            st.warning("Por favor, ingresa una consulta.")
        else:
            with st.spinner("Generando informe... Este proceso puede tardar un momento."):
                relevant_info = get_relevant_info(db, selected_files)
                prompt = (
                    f"Pregunta del Cliente: '{question}'\n\n"
                    "Eres un analista experto en ciencias del comportamiento e investigación de mercados. Tu estilo es claro, directo y memorable (inspirado en 'Ideas que Pegan').\n"
                    "Usa la siguiente 'Información de Contexto' para redactar un informe profesional en Markdown con la siguiente estructura:\n"
                    "1. **Introducción**: Contexto y pregunta central.\n"
                    "2. **Principales Hallazgos**: Hechos relevantes que responden a la pregunta, con citas en formato IEEE (ej. [1]).\n"
                    "3. **Insights**: Aprendizajes profundos y verdades reveladoras a partir de los hallazgos.\n"
                    "4. **Conclusiones**: Síntesis y dirección clara.\n"
                    "5. **Recomendaciones**: 3-4 acciones concretas y creativas.\n"
                    "6. **Referencias**: Lista de estudios citados (usa el título, no el nombre de archivo).\n\n"
                    f"Información de Contexto:\n{relevant_info}"
                )
                report = call_gemini_api(prompt)
                if report:
                    cliente_nombre = st.session_state.get('cliente', 'Cliente Confidencial').title()
                    fecha_actual = datetime.datetime.now().strftime("%d/%m/%Y")
                    encabezado = (
                        f"# {question}\n\n"
                        f"**Preparado para:** {cliente_nombre}\n"
                        f"**Fecha de elaboración:** {fecha_actual}\n\n---\n\n"
                    )
                    st.session_state["report"] = encabezado + report
                    log_query_event(question, mode="Generación de Reportes")
                else:
                    st.error("No se pudo generar el informe.")

    if "report" in st.session_state:
        st.markdown("---")
        st.markdown("### Informe Generado")
        edited_report = st.text_area("Puedes editar el informe aquí antes de descargarlo:", value=st.session_state["report"], height=400, key="report_edit")
        pdf_bytes = generate_pdf_from_markdown(edited_report, "Informe Final", banner_path="Banner (2).jpg")
        st.download_button(
            "⬇️ Descargar Informe en PDF", data=pdf_bytes, file_name="Informe_AtelierIA.pdf", mime="application/pdf"
        )
        st.button("Nueva Consulta", on_click=reset_report_workflow)

def ideacion_mode(db, selected_files):
    st.markdown("### Conversaciones Creativas")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg['role']):
            st.markdown(msg['content'])

    if prompt := st.chat_input("Pregunta algo sobre los datos..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                relevant_info = get_relevant_info(db, selected_files)
                conversation_history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history])
                full_prompt = (
                    "Eres un experto en psicología del consumidor, innovación y creatividad. Tu objetivo es ayudar al usuario a conversar con sus datos para generar ideas novedosas.\n"
                    "Comienza siempre con un breve resumen de los proyectos relacionados con la solicitud. Responde de forma clara, sintética y creativa, usando la información de contexto y el historial de la conversación.\n\n"
                    f"Historial de conversación:\n{conversation_history}\n\n"
                    f"Información de contexto:\n{relevant_info}\n\n"
                    "Respuesta:"
                )
                response = call_gemini_api(full_prompt)
                st.markdown(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})
        log_query_event(prompt, mode="Conversación")

    if st.session_state.chat_history:
        st.button("Nueva Conversación", on_click=reset_chat_workflow)

def concept_generation_mode(db, selected_files):
    """
    Modo de Generación de Conceptos: a partir de una idea de producto,
    desarrolla un concepto basado en los hallazgos de los estudios.
    """
    st.markdown("### Generación de Conceptos")
    st.markdown(
        "Introduce una idea o un punto de partida para un nuevo producto. "
        "La IA utilizará los hallazgos de los estudios seleccionados para "
        "desarrollar un concepto completo."
    )
    product_idea = st.text_area("Escribe tu idea para un nuevo producto...", height=150, key="concept_idea")

    if st.button("Generar Concepto"):
        if not product_idea.strip():
            st.warning("Por favor, introduce una idea para generar el concepto.")
        else:
            with st.spinner("🧠 Desarrollando el concepto..."):
                relevant_info = get_relevant_info(db, selected_files)
                prompt = (
                    "Actúa como un estratega de innovación y marketing experto en bienes de consumo. "
                    "Tu tarea es desarrollar un concepto de producto completo a partir de una idea inicial "
                    "y los hallazgos de varios estudios de consumidor.\n\n"
                    f"**Idea de Producto del Usuario:**\n'{product_idea}'\n\n"
                    f"**Información de Contexto (Hallazgos de Estudios):**\n{relevant_info}\n\n---\n"
                    "**Instrucciones:**\n"
                    "Genera una respuesta estructurada en los siguientes cuatro puntos exactos. "
                    "Usa un tono creativo, estratégico y orientado al consumidor.\n\n"
                    "## 1. Definición de la Necesidad del Consumidor\n"
                    "Analiza la 'Información de Contexto' y sintetiza los hallazgos más potentes que revelen "
                    "una tensión, un deseo o una necesidad no satisfecha del consumidor que el nuevo producto podría resolver.\n\n"
                    "## 2. Descripción del Producto a Entregar\n"
                    "Tomando como base la 'Idea de Producto del Usuario', describe de forma atractiva y clara cómo sería este nuevo producto.\n\n"
                    "## 3. Beneficios Clave\n"
                    "Enumera 3 o 4 beneficios que conecten directamente el producto (punto 2) con la necesidad (punto 1).\n\n"
                    "## 4. Claim Propuesto\n"
                    "Crea un claim o eslogan para el producto: una frase corta, memorable y que encapsule la esencia del concepto."
                )
                concept_response = call_gemini_api(prompt)
                if concept_response:
                    st.session_state['generated_concept'] = concept_response
                    log_query_event(product_idea, mode="Generación de Conceptos")
                else:
                    st.error("No se pudo generar el concepto. Inténtalo de nuevo.")

    if 'generated_concept' in st.session_state:
        st.markdown("---")
        st.markdown("### ✨ Tu Concepto está Listo")
        st.markdown(st.session_state['generated_concept'])
        pdf_bytes = generate_pdf_from_markdown(st.session_state['generated_concept'], "Concepto de Producto")
        st.download_button("⬇️ Descargar Concepto en PDF", data=pdf_bytes, file_name="Concepto_AtelierIA.pdf", mime="application/pdf")
        if st.button("Crear Nuevo Concepto"):
            reset_concept_workflow()
            st.rerun()

# ==============================
# Función Principal de la App
# ==============================
def main():
    st.set_page_config(page_title="Atelier Data Studio", layout="wide")
    if not st.session_state.get("logged_in"):
        show_login()
        return

    st.title("Atelier Data Studio")
    st.markdown("Herramienta de IA para realizar consultas y conversar con datos de estudios de mercado.")

    db_full = load_database(st.session_state.cliente)
    if not db_full:
        st.error("La base de conocimiento está vacía o no se pudo cargar. La aplicación no puede continuar.")
        st.stop()
    
    # --- BARRA LATERAL (SIDEBAR) ---
    with st.sidebar:
        st.header("Panel de Control")
        if st.button("Cerrar Sesión"):
            st.session_state.clear()
            st.cache_data.clear()
            st.rerun()

        # MODIFICADO: Añadir nueva opción al radio
        modo = st.radio(
            "Seleccione el modo de uso:",
            ["Generar un reporte de reportes", "Conversaciones creativas", "Generación de conceptos"],
            key="app_mode"
        )
        st.markdown("---")
        st.header("Filtros de Datos")
        
        # Filtro por Marca
        marcas = sorted({doc.get("filtro", "") for doc in db_full if doc.get("filtro")})
        marcas.insert(0, "Todos")
        selected_marca = st.selectbox("Seleccione la marca:", marcas)
        db_filtered = apply_filter_criteria(db_full, selected_marca)
        
        # Filtro por Año
        years = sorted({doc.get("marca", "") for doc in db_filtered if doc.get("marca")})
        years.insert(0, "Todos")
        selected_year = st.selectbox("Seleccione el año:", years)
        if selected_year != "Todos":
            db_filtered = [d for d in db_filtered if d.get("marca") == selected_year]
        
        # Filtro por Proyecto
        proyectos = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db_filtered if extract_brand(d.get("nombre_archivo", ""))})
        proyectos.insert(0, "Todas")
        selected_proyecto = st.selectbox("Seleccione el proyecto:", proyectos)
        if selected_proyecto != "Todas":
            db_filtered = [d for d in db_filtered if extract_brand(d.get("nombre_archivo", "")) == selected_proyecto]
        
        st.markdown("---")

    # --- ÁREA PRINCIPAL ---
    # NUEVO: Mostrar los documentos que se usarán en la consulta
    if not db_filtered:
        st.warning("⚠️ No se han encontrado documentos con los filtros actuales. Por favor, ajusta tu selección.")
        st.stop()
    else:
        with st.expander(f"📖 Se usarán {len(db_filtered)} documentos como contexto. Haz clic para ver los títulos."):
            for doc in db_filtered:
                titulo = doc.get("titulo_estudio", "Título no disponible")
                st.caption(f"- {titulo}")

    selected_files = [d.get("nombre_archivo") for d in db_filtered]
    
    # MODIFICADO: Lógica para llamar al modo correcto
    if modo == "Generar un reporte de reportes":
        report_mode(db_filtered, selected_files)
    elif modo == "Conversaciones creativas":
        ideacion_mode(db_filtered, selected_files)
    elif modo == "Generación de conceptos":
        concept_generation_mode(db_filtered, selected_files)

if __name__ == "__main__":
    main()
