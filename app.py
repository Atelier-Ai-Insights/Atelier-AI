import datetime
import html  # para el monkey patch
import json
import unicodedata
from io import BytesIO
import os
import tempfile
from bs4 import BeautifulSoup  # pip install beautifulsoup4

import boto3  # pip install boto3
import google.generativeai as genai
import markdown2
import streamlit as st
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus.doctemplate import LayoutError
from supabase import create_client  # pip install supabase
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# Registrar fuente Unicode para tildes/ñ
pdfmetrics.registerFont(
    TTFont('DejaVuSans', 'DejaVuSans.ttf')
)

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

def logout():
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()

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
        model_name="gemini-2.0-flash-lite",
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
    except Exception as e:
        st.error(f"Error en la llamada a Gemini: {e}. Intentando cambiar API Key.")
        switch_api_key()
        try:
            response = model.generate_content([prompt])
        except Exception as e2:
            st.error(f"Error GRAVE en la llamada a Gemini: {e2}")
            return None

    raw = response.text
    text = html.unescape(raw)
    try:
        text = text.encode("utf-8").decode("unicode_escape")
    except Exception:
        pass
    try:
        text = text.encode("latin-1").decode("utf-8")
    except Exception:
        pass
    return text

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

# ==============================
# Normalización de Texto
# ==============================
def normalize_text(text):
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()

def add_markdown_content(pdf, markdown_text):
    html_text = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "tables", "break-on-newline"])
    soup = BeautifulSoup(html_text, "html.parser")
    container = soup.body if soup.body else soup

    for elem in container.children:
        if elem.name:
            if elem.name.startswith("h"):
                try:
                    level = int(elem.name[1])
                except:
                    level = 1
                pdf.add_title(elem.get_text(strip=True), level=level)
            elif elem.name == "p":
                pdf.add_paragraph(elem.get_text(strip=True))
            elif elem.name == "ul":
                for li in elem.find_all("li"):
                    pdf.add_paragraph("• " + li.get_text(strip=True))
            elif elem.name == "ol":
                for idx, li in enumerate(elem.find_all("li"), 1):
                    pdf.add_paragraph(f"{idx}. {li.get_text(strip=True)}")
            else:
                pdf.add_paragraph(elem.get_text(strip=True))
        else:
            text = elem.string
            if text and text.strip():
                pdf.add_paragraph(text.strip())

# ==============================
# CARGA DEL ARCHIVO JSON DESDE S3
# ==============================
@st.cache_data(show_spinner=False)
def load_database(cliente: str):
    """
    Carga y filtra la base de datos JSON en S3 según el cliente.
    Cada cliente obtiene su propio caché de datos.
    """
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

        # Filtrar por cliente (salvo admin "nicolas"), pero siempre incluir docs de Atelier IA
        cliente_norm = unicodedata.normalize("NFD", cliente or "").lower()
        cliente_norm = "".join(c for c in cliente_norm if unicodedata.category(c) != "Mn")

        if cliente_norm != "nicolas":
            filtered_data = []
            for doc in data:
                doc_cliente = doc.get("cliente", "")
                doc_norm = unicodedata.normalize("NFD", doc_cliente).lower()
                doc_norm = "".join(c for c in doc_norm if unicodedata.category(c) != "Mn")

                # incluir siempre si es Atelier IA o coincide con el cliente
                if "atelier" in doc_norm or cliente_norm in doc_norm:
                    filtered_data.append(doc)
            data = filtered_data

    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        data = []

    return data

# ==============================
# EXTRAER MARCA DEL NOMBRE DE ARCHIVO
# ==============================
def extract_brand(filename):
    if not filename or "In-ATL_" not in filename:
        return ""
    return filename.split("In-ATL_")[1].rsplit(".", 1)[0]

# =====================================================
# FUNCIONES DE GENERACIÓN DE INFORMES Y PDF
# =====================================================
banner_file = "banner.png"

def get_relevant_info(db, question, selected_files):
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"
            for grupo in pres.get("grupos", []):
                contenido = grupo.get("contenido_texto", "")
                all_text += f"Grupo {grupo.get('grupo_index')}: {contenido}\n"
                metadatos = grupo.get("metadatos", {})
                hechos     = grupo.get("hechos", {})
                if metadatos:
                    all_text += f"Metadatos: {json.dumps(metadatos)}\n"
                if hechos:
                    if hechos.get("tipo") == "cita":
                        all_text += "[Cita]\n"
                    else:
                        all_text += f"Hechos: {json.dumps(hechos)}\n"
            all_text += "\n---\n\n"
    return all_text

def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)

   # Prompt 1: Extrae hallazgos clave y referencias.
    prompt1 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones:\n"
        "1. Identifica en la pregunta la marca y el producto exacto sobre el cual se consulta. Sé muy específico y riguroso.\n"
        "2. Reitera la pregunta del cliente: ***{question}***.\n"
        "3. Utiliza la 'Información de Contexto' (extractos de documentos de investigación) para extraer los hallazgos más relevantes que respondan directamente a la pregunta.\n"
        "4. No incluyas el texto completo de las citas, sino extractos breves que permitan identificar la fuente.\n"
        "5. Incluye metadatos relevantes (documentos, grupos, etc.) e indica en cada hallazgo si la cita sigue el estilo IEEE (ejemplo: [1]).\n"
        "6. En la sección 'Referencias', asocia cada número a la referencia completa, no escribas el nombre del archivo, sino el titulo del proyecto (ejemplo: [1] Autor, 'Título', año, etc.). Siempre provee las referencias citadas.\n"
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
    if result1 is None:
        return None
    result1 = html.unescape(result1)

    # Prompt 2: Redacta el informe principal en prosa utilizando el resumen anterior.
    prompt2 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones Generales:\n"
        "1. Identifica en la pregunta la marca y el producto exacto. Responde de manera específica y rigurosa a lo que el cliente pregunta.\n"
        "2. Recuerda que todos los estudios en la base de datos fueron realizados por Atelier. Menciónalo si es relevante, especialmente en 'Principales Hallazgos'.\n"
        "3. Actúa como un analista experto en investigación de mercados y comunicación estratégica. Enfócate en claridad, síntesis poderosa y pensamiento estructurado.\n"
        "4. El estilo de redacción debe ser claro, directo, conciso y memorable (inspirado en “Ideas que pegan” de Chip Heath y Dan Heath). Evita lenguaje técnico innecesario; prioriza lo relevante y accionable.\n\n"
        "Estructura del Informe (sé breve y preciso en cada sección):\n\n"
        "##1. **Introducción**:\n"
        "   - Preserva esta sección. Plantea el contexto y la pregunta central. Usa una historia corta, un dato inesperado o una analogía poderosa para captar la atención.\n\n"
        "##2. **Principales Hallazgos**:\n"
        "   - Presenta de forma estructurada los hechos más relevantes descubiertos, directamente desde la sección de resultados de los diferentes reportes y la información de contexto.\n"
        "   - Asegúrate de que cada hallazgo responda a la pregunta del cliente y ofrezca valor original.\n"
        "   - Utiliza solo información relevante a la marca y el producto citados. No utilices estudios de forma innecesaria.\n"
        "   - Referencia en formato IEEE (ej. [1]), usando el título del estudio o el producto del que se habla, más que el nombre del archivo.\n\n"
        "##3. **Insights**:\n"
        "   - Extrae aprendizajes y verdades profundas a partir de los hallazgos. Utiliza analogías y comparaciones que refuercen el mensaje y transformen la comprensión del problema. Sé conciso.\n\n"
        "##4. **Conclusiones**:\n"
        "   - Sintetiza la información y ofrece una dirección clara basada en los insights. Evita repetir información.\n\n"
        "##5. **Recomendaciones**:\n"
        "   - Con base en el informe, proporciona 2-3 recomendaciones concretas, creativas, precisas y accionables que sirvan como inspiración.\n"
        "   - Deben estar alineadas con los insights y conclusiones. Evita la extensión innecesaria.\n\n"
        "##6. **Referencias**:\n"
        "   - Cita el título del estudio (no el nombre del archivo), utilizando la información de la primera diapositiva o metadatos disponibles.\n\n"
        "Utiliza el siguiente resumen (Hallazgos Clave y Referencias) y la Información de Contexto para elaborar el informe:\n\n"
        f"Resumen de Hallazgos Clave y Referencias:\n{result1}\n\n"
        f"Información de Contexto Adicional (si es necesaria para complementar el resumen):\n{relevant_info}\n\n"
        "Por favor, redacta el informe completo respetando la estructura y las instrucciones, en un estilo profesional, claro, conciso y coherente, utilizando Markdown."
    )
    result2 = call_gemini_api(prompt2)
    if result2 is None:
        return None
    result2 = html.unescape(result2)
    
    fecha_actual = datetime.datetime.now().strftime("%d/%m/%Y")
    # st.session_state.cliente debe estar definido en tu aplicación Streamlit
    cliente_nombre = getattr(st.session_state, 'cliente', 'Cliente Confidencial') # Fallback
    encabezado = (
        f"# {question}\n"
        f"**Preparado por:** \nAtelier IA\n\n"
        f"**Preparado para:** \n{cliente_nombre}\n\n"
        f"**Fecha de elaboración:** \n{fecha_actual}\n\n"
    )
    informe_completo = encabezado + result2
    return informe_completo

def clean_text(text):
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

class PDFReport:
    def __init__(self, filename, banner_path=None):
        self.filename   = filename
        self.banner_path= banner_path
        self.elements   = []
        self.styles     = getSampleStyleSheet()
        self.doc        = SimpleDocTemplate(
            self.filename,
            pagesize=A4,
            rightMargin = 12 * mm,
            leftMargin  = 12 * mm,
            topMargin   = 45 * mm,
            bottomMargin= 18 * mm
        )
        # Estilos personalizados
        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Heading1'], alignment=1, spaceAfter=12))
        self.styles.add(ParagraphStyle(name='CustomHeading', parent=self.styles['Heading2'], spaceBefore=10, spaceAfter=6))
        self.styles.add(ParagraphStyle(name='CustomBodyText', parent=self.styles['Normal'], leading=12, alignment=4))
        self.styles.add(ParagraphStyle(name='CustomFooter', parent=self.styles['Normal'], alignment=2, textColor=colors.grey))
        for style_name in ['CustomTitle','CustomHeading','CustomBodyText','CustomFooter']:
            self.styles[style_name].fontName = 'DejaVuSans'

    def header(self, canvas, doc):
        canvas.saveState()
        if self.banner_path and os.path.isfile(self.banner_path):
            try:
                img_w, img_h = 210*mm, 35*mm
                y_pos = A4[1] - img_h
                canvas.drawImage(self.banner_path, 0, y_pos, width=img_w, height=img_h,
                                 preserveAspectRatio=True, anchor='n')
                line_y = y_pos - 5
                canvas.setStrokeColor(colors.lightgrey)
                canvas.line(12*mm, line_y, A4[0]-12*mm, line_y)
            except:
                pass
        else:
            canvas.setStrokeColor(colors.lightgrey)
            canvas.line(12*mm, A4[1]-40*mm, A4[0]-12*mm, A4[1]-40*mm)
        canvas.restoreState()

    def footer(self, canvas, doc):
        canvas.saveState()
        footer_text = (
            "El uso de esta información está sujeto a los términos "
            "y condiciones que rigen su suscripción a Atelier Ai. Es su responsabilidad "
            "asegurarse de que el uso de esta información no infrinja los derechos de "
            "propiedad intelectual."
        )
        p = Paragraph(clean_text(footer_text), self.styles['CustomFooter'])
        w, h = p.wrap(doc.width, doc.bottomMargin)
        p.drawOn(canvas, doc.leftMargin, h)
        canvas.restoreState()

    def header_footer(self, canvas, doc):
        self.header(canvas, doc)
        self.footer(canvas, doc)

    def add_paragraph(self, text, style='CustomBodyText'):
        p = Paragraph(clean_text(text), self.styles[style])
        self.elements += [p, Spacer(1, 6)]

    def add_title(self, text, level=1):
        style = 'CustomTitle' if level==1 else 'CustomHeading'
        p = Paragraph(clean_text(text), self.styles[style])
        self.elements += [p, Spacer(1, 12)]

    def build_pdf(self):
        self.doc.build(self.elements, onFirstPage=self.header_footer, onLaterPages=self.header_footer)

def generate_pdf_html(content, title="Documento Final", banner_path=None, output_filename=None):
    if output_filename is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        output_filename = tmp.name
        tmp.close()
    pdf = PDFReport(output_filename, banner_path=banner_path)
    pdf.add_title(title, level=1)
    add_markdown_content(pdf, content)
    pdf.build_pdf()
    with open(output_filename, "rb") as f:
        data = f.read()
    os.remove(output_filename)
    return data

def ideacion_mode(db, selected_files):
    """
    Modo Conversación: interactúa con los datos, centrado en la sección de resultados.
    """
    st.subheader("Modo Conversación: Conversa con los datos")

    # Inicializar historial
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Mostrar historial de mensajes
    for msg in st.session_state.chat_history:
        st.markdown(f"**{msg['role'].capitalize()}:** {msg['message']}")

    # Instrucciones justo debajo de la última consulta
    st.markdown(
        "Para hacer nuevas consultas, escribe tu pregunta en el cuadro de abajo "
        "y presiona **Enviar pregunta**."
    )

    # Caja de texto amplia para la consulta
    user_input = st.text_area("Pregunta algo…", height=150)

    # Botón para enviar la consulta
    if st.button("Enviar pregunta"):
        if not user_input.strip():
            st.warning("Ingrese una pregunta para continuar la conversación.")
        else:
            # Añadir mensaje del usuario al historial
            st.session_state.chat_history.append({
                "role": "Usuario",
                "message": user_input
            })

            # Construir prompt simplificado
            relevant = get_relevant_info(db, user_input, selected_files)
            conv_prompt = (
                "Historial de conversación:\n"
                + "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history)
                + "\n\nInformación de contexto:\n" + relevant
                + "\n\nInstrucciones:\n"
                "- Responde usando únicamente la sección de resultados de los reportes.\n"
                "- Incluye citas numeradas al estilo IEEE (por ejemplo, [1]).\n\n"
                "Respuesta detallada:"
            )

            # Llamada a la API
            resp = call_gemini_api(conv_prompt)
            if resp:
                st.session_state.chat_history.append({
                    "role": "Asistente",
                    "message": resp
                })
                st.markdown(f"**Asistente:** {resp}")
                log_query_event(user_input, mode="Conversación")
            else:
                st.error("Error al generar la respuesta.")

    # Oferta de descarga del historial
    if st.session_state.chat_history:
        pdf_bytes = generate_pdf_html(
            "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history),
            title="Historial de Chat"
        )
        st.download_button(
            "Descargar Chat en PDF",
            data=pdf_bytes,
            file_name="chat.pdf",
            mime="application/pdf"
        )


def main():
    if not st.session_state.get("logged_in"):
        show_login()

    st.title("Atelier Ai")
    st.markdown(
        "Atelier Ai es una herramienta de inteligencia artificial para realizar consultas\n"
        "y conversar con datos arrojados por distintos estudios de mercados\n"
        "realizados para el entendimiento del consumidor y del mercado, impulsada\n"
        "por modelos lingüísticos de vanguardia.\n\n"
        "**Modo Generación de Reportes / Modo Conversación**"
    )

    try:
        db = load_database(st.session_state.cliente)
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        st.stop()

    # Sidebar ordenado
    modo = st.sidebar.radio(
        "Seleccione el modo de uso:",
        ["Generar un reporte de reportes", "Conversar con los datos"]
    )
    years = sorted({doc.get("marca", "") for doc in db if doc.get("marca")})
    years.insert(0, "Todos")
    selected_year = st.sidebar.selectbox("Seleccione el año:", years)
    if selected_year != "Todos":
        db = [d for d in db if d.get("marca") == selected_year]

    brands = sorted({extract_brand(d.get("nombre_archivo", "")) for d in db})
    brands.insert(0, "Todas")
    selected_brand = st.sidebar.selectbox("Seleccione el proyecto:", brands)
    if selected_brand != "Todas":
        db = [d for d in db if extract_brand(d.get("nombre_archivo", "")) == selected_brand]

    # Calificación (solo en modo reporte)
    if modo == "Generar un reporte de reportes":
        rating = st.sidebar.radio(
            "Califique el informe:", [1,2,3,4,5], horizontal=True, key="rating"
        )

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()

    # Lógica principal
    if modo == "Generar un reporte de reportes":
        st.markdown("### Generar reporte")
        question = st.text_area("Escribe tu consulta…", height=150)

        if st.button("Generar reporte"):
            if not question.strip():
                st.warning("Ingrese una consulta.")
            else:
                # Verificar si cambia la pregunta
                if question != st.session_state.get('last_question'):
                    st.session_state.pop('report', None)
                    st.session_state['last_question'] = question

                if 'report' not in st.session_state:
                    st.info("Generando informe…")
                    report = generate_final_report(question, db, [d.get("nombre_archivo") for d in db])
                    if report is None:
                        st.error("No se pudo generar el informe.")
                        return
                    st.session_state['report'] = report

                # Mostrar y editar resultado
                st.markdown("### Informe Final")
                edited = st.text_area(
                    "Informe generado (puede editarlo abajo)",
                    value=st.session_state['report'],
                    height=300
                )
                # Caja de personalización debajo del informe
                additional_info = st.text_area(
                    "Personaliza el reporte…", height=150, key="personalization"
                )

                final_content = f"{edited}\n\n{additional_info}" if additional_info.strip() else edited
                pdf_bytes = generate_pdf_html(
                    final_content,
                    title="Informe Final",
                    banner_path=banner_file
                )
                st.download_button(
                    "Descargar Informe en PDF",
                    data=pdf_bytes,
                    file_name="Informe_AtelierIA.pdf",
                    mime="application/pdf"
                )
                log_query_event(question, mode="Generación", rating=rating)
    else:
        ideacion_mode(db, [d.get("nombre_archivo") for d in db])

if __name__ == "__main__":
    main()
