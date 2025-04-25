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
# ======== Fragmento 2: Registrar fuente Unicode para tildes/ñ ========
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# Ajusta la ruta al .ttf según tu entorno
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
    username = st.text_input("Usuario",placeholder="Apple")
    password = st.text_input("Contraseña (4 dígitos)", type="password", placeholder="0000")
    if st.button("Ingresar"):
        if username in ALLOWED_USERS and password == ALLOWED_USERS[username]:
            st.session_state.logged_in = True
            st.session_state.user = username
            # Convertir a minúsculas para normalización posterior
            st.session_state.cliente = username.lower()
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

def logout():
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.clear()          # limpia todo session_state de un plumazo
        st.cache_data.clear()             # limpia todos los @st.cache_data
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

    # 1) Des-escapa entidades HTML (&ntilde; → ñ; &aacute; → á; etc.)
    text = html.unescape(raw)

    # 2) Convierte literales "\u00e1" → "á"
    try:
        text = text.encode("utf-8").decode("unicode_escape")
    except Exception:
        pass

    # 3) Corrige mojibake: si "ó" salió como "Ã³", recompónlo:
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
    """
    Convierte un texto en Markdown a HTML y lo procesa para agregar al PDF.
    Se reconocen encabezados (h1, h2, …), párrafos y listas (ordenadas y desordenadas).
    """
    # Convertir Markdown a HTML
    html_text = markdown2.markdown(markdown_text, extras=["fenced-code-blocks", "tables", "break-on-newline"])
    soup = BeautifulSoup(html_text, "html.parser")
    
    # Si el contenido tiene un <body> (algunos conversores lo agregan) usamos su contenido,
    # de lo contrario, iteramos sobre el soup entero.
    container = soup.body if soup.body else soup

    for elem in container.children:
        if elem.name:
            if elem.name.startswith("h"):
                # Extraer el nivel del encabezado; h1 => level 1, etc.
                try:
                    level = int(elem.name[1])
                except:
                    level = 1
                pdf.add_title(elem.get_text(strip=True), level=level)
            elif elem.name == "p":
                pdf.add_paragraph(elem.get_text(strip=True))
            elif elem.name == "ul":
                # Listas sin ordenar
                for li in elem.find_all("li"):
                    pdf.add_paragraph("• " + li.get_text(strip=True))
            elif elem.name == "ol":
                # Listas ordenadas: Agregar número de ítem
                for idx, li in enumerate(elem.find_all("li"), 1):
                    pdf.add_paragraph(f"{idx}. {li.get_text(strip=True)}")
            else:
                # Otros elementos se tratan como párrafos
                pdf.add_paragraph(elem.get_text(strip=True))
        else:
            # Texto plano fuera de etiquetas
            text = elem.string
            if text and text.strip():
                pdf.add_paragraph(text.strip())


# ==============================
# CARGA DEL ARCHIVO JSON DESDE S3 (para alimentar al modelo)
# ==============================
@st.cache_data(show_spinner=False)
def load_database():
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key   = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key   = st.secrets["S3_SECRET_KEY"]
    bucket_name     = st.secrets.get("S3_BUCKET")
    object_key      = "resultado_presentacion (1).json"

    try:
        response = boto3.client(
            "s3",
            endpoint_url          = s3_endpoint_url,
            aws_access_key_id     = s3_access_key,
            aws_secret_access_key = s3_secret_key,
        ).get_object(Bucket=bucket_name, Key=object_key)
        data = json.loads(response["Body"].read().decode("utf-8"))

        # Si no es Nicolas, filtramos por su cliente y por Atelier (siempre)
        if "cliente" in st.session_state and normalize_text(st.session_state.cliente) != "nicolas":
            usuario_cliente = normalize_text(st.session_state.cliente)
            filtered_data   = []

            for doc in data:
                doc_cliente = normalize_text(doc.get("cliente", ""))

                # Incluye siempre todo lo de Atelier, en cualquiera de sus formas
                if "atelier" in doc_cliente:
                    filtered_data.append(doc)
                # Incluye si el nombre de usuario está dentro del campo cliente
                elif usuario_cliente and usuario_cliente in doc_cliente:
                    filtered_data.append(doc)

            data = filtered_data

    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        data = []

    return data


# =====================================================
# FUNCION PARA OBTENER IMAGEN DE S3 (Para la plantilla/banner)
# =====================================================
banner_file = "banner.png"

# ==============================
# Función para obtener la información relevante
# ==============================
def get_relevant_info(db, question, selected_files):
    all_text = ""
    # Se construye el texto de contexto a entregar a Gemini.
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"
            for grupo in pres.get("grupos", []):
                contenido = grupo.get("contenido_texto", "")
                all_text += f"Grupo {grupo.get('grupo_index')}: {contenido}\n"
                metadatos = grupo.get("metadatos", {})
                hechos = grupo.get("hechos", {})
                if metadatos:
                    all_text += f"Metadatos: {json.dumps(metadatos)}\n"
                if hechos:
                    if "tipo" in hechos and hechos["tipo"] == "cita":
                        all_text += "[Cita]\n"
                    else:
                        all_text += f"Hechos: {json.dumps(hechos)}\n"
            all_text += "\n---\n\n"
    return all_text

# ==============================
# Generación del Informe Final
# ==============================
def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)

    # Prompt 1: Genera el resumen estructurado con metadatos.
    prompt1 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones:\n"
        "Busca en la pregunta la marca de la ue se hace la pregunta y el producto exacto del que se está haciendo la pregunta, debes ser muy especifico y riguroso en responder exactamente lo que el cliente esta preguntando."
        "- Reitera la pregunta del cliente: ***{question}*** y asegúrate de que la respuesta esté alineada con ella.\n"
        "- El informe se organizará en cinco secciones: \n"
        "   1. Introducción\n"
        "   2. Enfoque metodológico\n"
        "   3. Principales hallazgos\n"
        "   4. Planteamiento estratégico (conclusiones)\n"
        "   5. Referencias\n\n"
        "- Utiliza la siguiente información de contexto (extractos de documentos de investigación) para elaborar un resumen estructurado.\n"
        "- No incluyas el texto completo de las citas, sino extractos que permitan identificar la fuente.\n"
        "- Incluye metadatos relevantes (documentos, grupos, etc.) e indica en cada caso si la cita sigue el estilo IEEE: al final de la frase se incluye un número (por ejemplo, [1]). "
        "- Posteriormente, en la sección de Referencias, asocia dicho número a la referencia completa (por ejemplo, [1] Autor, 'Título', año, etc.). Siempre provee las referencias citadas.\n"
        "- Supón que todas las preguntas se basan en estudios realizados. Resalta y enfatiza los aportes y hallazgos positivos de dichos estudios.\n\n"
        f"Información de Contexto:\n{relevant_info}\n\n"
        "Respuesta (Resumen Estructurado y Metadatos):"
    )
    result1 = call_gemini_api(prompt1)
    if result1 is None:
        return None
    result1 = html.unescape(result1)
    # Prompt 2: Redacta la sección principal del informe en prosa utilizando el resumen anterior.
    prompt2 = (
    f"Pregunta del Cliente: ***{question}***\n\n"
    "Instrucciones:\n"
    "Busca en la pregunta la marca de la ue se hace la pregunta y el producto exacto del que se está haciendo la pregunta, debes ser muy especifico y riguroso en responder exactamente lo que el cliente esta preguntando."
    "Recuerda que todos los estudios en la base de datos que usamos fueron realizados por Atelier. Referencía especialmente en principales hayazgos." 
    "Actúa como un analista experto en investigación de mercados y en comunicación estratégica, con enfoque en claridad, síntesis poderosa y pensamiento estructurado. Tu tarea es generar un reporte de alto impacto dividido en cinco secciones:\n"
    "- **Introducción**\n"
    "- **Metodología**\n"
    "- **Principales hallazgos**\n"
    "- **Insights**\n"
    "- **Conclusiones**\n\n"
    "El estilo de redacción debe estar inspirado en “Ideas que pegan” de Chip Heath y Dan Heath: usa un lenguaje claro, directo, con ejemplos concretos, metáforas memorables y estructuras que ayuden a fijar la información en la mente del lector. Evita el lenguaje técnico innecesario y prioriza lo emocional, lo inesperado y lo relevante.\n\n"
    "Estructura esperada:\n\n"
    "##1. **Introducción**:\n"
    "- Plantea el contexto y el problema o pregunta central. Usa una historia corta, un dato inesperado o una analogía poderosa para captar la atención desde el inicio.\n\n"
    "##2. **Metodología**:\n"
    "- Describe brevemente cómo se obtuvo la información, asegurando claridad sobre las fuentes consultadas y enfatizando en la diversidad (evitando fuentes redundantes o repetitivas). Explica por qué el enfoque elegido aporta un valor diferencial al análisis.\n\n"
    "##3. **Principales Hallazgos**:\n"
    "- Presenta de forma estructurada los hechos más relevantes descubiertos (por temas, niveles, fuentes, etc.), garantizando que cada hallazgo ofrezca un valor original y no simplemente repita lugares comunes. Receurda siempre referenciar estudios si hay disponibles relacionados con la marca y producto citado, utiliza solo información relevante a la marca y el producto, no utilices estudios de forma innecesaria. Referencia en formato IEEE, mas que el nombre del documento el titulo o el producto del que se habla.\n\n"
    "##4. **Insights**:\n"
    "- Extrae aprendizajes y verdades profundas a partir de los hallazgos. Utiliza analogías y comparaciones que refuercen el mensaje y transformen la comprensión del problema.\n\n"
    "##5. **Conclusiones**:\n"
    "- Sintetiza la información y ofrece una dirección clara sobre cómo actuar con base en los insights obtenidos. Incluye recomendaciones breves que estén alineadas con los aprendizajes, sin repetir lo anterior.\n\n"
    "Utiliza a continuación el siguiente resumen estructurado y metadatos, obtenido de los estudios e información contextual proporcionada:\n\n"
    "##6. **Recomendaciones**\n"
    "Con base en el informe realizado, que se le puede recomendar al cliente, deben ser recomendaciones interesantes, creativas, precisas y accionables. Estructura las recomendaciones utilizando referentes contextuales (matrices o estructuras) y teóricos del marketing o de psicologia o de innovación que se hayan publicado entre 2015 y 2025.\n\n"
    "##7. **Referencias**\n"
    "Cita el titulo del estudio, no el nombre del archivo, usa la información de la primera diapositiva que se reporta en la base de datos\n\n"
    f"Resumen Estructurado y Metadatos:\n{result1}\n\n"
    "Información de Contexto:\n"
    f"{relevant_info}\n\n"
    "Por favor, redacta el informe completo respetando lo solicitado en los puntos anteriores, en un estilo profesional, claro y coherente, utilizando Markdown."
    )
    result2 = call_gemini_api(prompt2)
    if result2 is None:
        return None
    result2 = html.unescape(result2)
    
    fecha_actual = datetime.datetime.now().strftime("%d/%m/%Y")
    encabezado = (
        f"# {question}\n"
        f"**Preparado por:**  Atelier IA\n\n"
        f"**Preparado para:**  {st.session_state.cliente}\n\n"
        f"**Fecha de elaboración:**  {fecha_actual}\n\n"
    )
    informe_completo = encabezado + result2  # Se asume que Gemini ya incluye la sección "Fuentes"
    return informe_completo

# ==============================
# NUEVA IMPLEMENTACIÓN DEL PDF CON REPORTLAB
# ==============================
# Función única para limpiar el texto (duplicada se ha unificado)
def clean_text(text):
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

class PDFReport:
    def __init__(self, filename, banner_path=None):
        self.filename = filename
        self.banner_path = banner_path  # Guardamos el path del banner
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.doc = SimpleDocTemplate(
            self.filename,
            pagesize=A4,
            rightMargin=12 * mm,
            leftMargin=12 * mm,
            topMargin=45 * mm,
            bottomMargin=18 * mm
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
                img_width, img_height = 210 * mm, 35 * mm
                # Calcular y_pos para que la imagen esté pegada al borde superior
                y_pos = A4[1] - img_height
                canvas.drawImage(self.banner_path, 0, y_pos, width=img_width, height=img_height,
                                preserveAspectRatio=True, anchor='n')
                # Línea de separación debajo del banner
                line_y = y_pos - 5
                canvas.setStrokeColor(colors.lightgrey)
                canvas.line(12 * mm, line_y, A4[0] - 12 * mm, line_y)
            except Exception as e:
                # En caso de error, no se dibuja el banner
                pass
        else:
            canvas.setStrokeColor(colors.lightgrey)
            canvas.line(12 * mm, A4[1] - 40 * mm, A4[0] - 12 * mm, A4[1] - 40 * mm)
        canvas.restoreState()

    def footer(self, canvas, doc):
        canvas.saveState()
        footer_text = f"Generado por Atelier IA el {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | Página {doc.page}"
        p = Paragraph(footer_text, self.styles['CustomFooter'])
        w, h = p.wrap(doc.width, doc.bottomMargin)
        p.drawOn(canvas, doc.leftMargin, h)
        canvas.restoreState()

    def header_footer(self, canvas, doc):
        self.header(canvas, doc)
        self.footer(canvas, doc)

    def add_paragraph(self, text, style='CustomBodyText'):
        text = clean_text(text)
        p = Paragraph(text, self.styles[style])
        self.elements.append(p)
        self.elements.append(Spacer(1, 6))

    def add_title(self, text, level=1):
        text = clean_text(text)
        style = 'CustomTitle' if level == 1 else 'CustomHeading'
        p = Paragraph(text, self.styles[style])
        self.elements.append(p)
        self.elements.append(Spacer(1, 12))

    def insert_banner(self, banner_path, max_width_mm=210, max_height_mm=35):
        if os.path.isfile(banner_path):
            try:
                rl_img = RLImage(banner_path, width=max_width_mm * mm, height=max_height_mm * mm)
                rl_img.hAlign = 'CENTER'
                self.elements.append(rl_img)
                self.elements.append(Spacer(1, 10))
            except Exception as e:
                self.add_paragraph(f"Error al insertar el banner: {e}")
        else:
            self.add_paragraph("Banner no encontrado.")

    def build_pdf(self):
        try:
            self.doc.build(self.elements, onFirstPage=self.header_footer, onLaterPages=self.header_footer)
        except LayoutError as e:
            raise Exception(f"Error en el layout del PDF: {e}")
        except Exception as e:
            raise Exception(f"Error inesperado al generar el PDF: {e}")

def generate_pdf_html(content, title="Documento Final", banner_path=None, output_filename=None):
    import tempfile
    if output_filename is None:
        tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        output_filename = tmp_file.name
        tmp_file.close()
    # Pasamos el banner_path al crear el PDFReport
    pdf = PDFReport(output_filename, banner_path=banner_path)
    
    # Se omite la inserción del banner en el contenido, ya que se muestra en el header
    pdf.add_title(title, level=1)
    add_markdown_content(pdf, content)
    
    pdf.build_pdf()
    
    with open(output_filename, "rb") as f:
        pdf_bytes = f.read()
    
    os.remove(output_filename)
    return pdf_bytes

# ==============================
# MODO DE IDEACIÓN (CHAT INTERACTIVO)
# ==============================
def ideacion_mode(db, selected_files):
    st.subheader("Modo de Ideación: Conversa con los datos")
    st.markdown("Utiliza este espacio para realizar consultas interactivas.")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    for msg in st.session_state.chat_history:
        st.markdown(f"**{msg['role'].capitalize()}:** {msg['message']}")
    user_input = st.text_input("Escribe tu consulta o idea:")
    if st.button("Enviar consulta"):
        if not user_input.strip():
            st.warning("Ingrese un mensaje para continuar la conversación.")
        else:
            st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
            relevant_info = get_relevant_info(db, user_input, selected_files)
            conversation_prompt = "Historial de conversación:\n"
            for msg in st.session_state.chat_history:
                conversation_prompt += f"{msg['role']}: {msg['message']}\n"
            conversation_prompt += (
                "\nInformación de contexto:\n" + relevant_info + "\n\nGenera una respuesta detallada y coherente. Responde de forma creativa, cita los hechos que puedan ser relevantes, eres un modelo de ideación que busca la innovación y la creatividad"
            )
            respuesta = call_gemini_api(conversation_prompt)
            if respuesta is None:
                st.error("Error al generar la respuesta.")
            else:
                st.session_state.chat_history.append({"role": "Asistente", "message": respuesta})
                st.markdown(f"**Asistente:** {respuesta}")
                log_query_event(user_input, mode="Ideacion")
    if st.session_state.chat_history:
        pdf_bytes = generate_pdf_html(
            "\n".join([f"{m['role']}: {m['message']}" for m in st.session_state.chat_history]),
            title="Historial de Chat",
        )
        st.download_button(
            "Descargar Chat en PDF",
            data=pdf_bytes,
            file_name="chat.pdf",
            mime="application/pdf",
        )

# ==============================
# Aplicación Principal
# ==============================
def main():
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        show_login()
    logout()  # Opción de cerrar sesión en la barra lateral

    st.title("Atelier IA")
    st.markdown(
        """
        Bienvenido a **Atelier IA**. Es una plataforma intuitiva y eficiente que te ayuda a generar informes y a interactuar con tus datos de forma creativa. Con herramientas de inteligencia artificial, puedes resumir estudios y obtener insights para mejorar tus estrategias de marca, todo en un entorno fácil de usar y con resultados profesionales.

        - **Informe de Informes:** Genera un informe formal resumiendo los estudios realizados para tus marcas.
        - **Ideación:** Permite interactuar con los datos de forma abierta y creativa, aprovechalo para poder encontrar nuevas ideas.
        """
    )

    try:
        db = load_database()
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        st.stop()

    #st.write(f"Documentos cargados para el análisis: {len(db)}")
    selected_files = [doc.get("nombre_archivo") for doc in db]

    # Filtrado por marcas en la barra lateral
    marcas = sorted({doc.get("marca", "").strip() for doc in db if doc.get("marca", "").strip()})
    marcas.insert(0, "Todas")
    selected_marca = st.sidebar.selectbox("Seleccione la marca que quiera incluir en su consulta", marcas)
    if selected_marca != "Todas":
        db = [doc for doc in db if normalize_text(doc.get("marca", "")) == normalize_text(selected_marca)]
        selected_files = [doc.get("nombre_archivo") for doc in db]

    modo = st.sidebar.radio(
        "Seleccione el modo", ["Informe de Informes", "Ideación (Conversar con los datos)"]
    )
    if modo == "Informe de Informes":
        st.markdown("### Ingrese una pregunta para generar el informe")
        question = st.text_area(
            "Pregunta",
            height=150,
            help="Escriba la pregunta o tema para el informe. Ejemplo: '¿Cuál es la percepción de los consumidores sobre nuestra marca?'",
            placeholder="Ejemplo: ¿Cuál es la percepción de los consumidores sobre nuestra marca?"
        )
        additional_info = st.text_area(
            "Personaliza tu informe (esté fragmento va al final de lo generado por Atelier IA)",
            placeholder="Ejemplo: Agrega una nota final, firma o escribe comentarios adicionales que desees incluir en el informe final.",
            key="additional_info",
            height=150
        )
        rating = st.sidebar.radio("Calificar el Informe", options=[1, 2, 3, 4, 5], horizontal=True, key="rating")

        if 'last_question' not in st.session_state:
            st.session_state['last_question'] = ''
        
        # --- Bloque completo para Generar Informe, con regeneración dinámica ---
        if st.button("Generar Informe"):
            if not question.strip():
                st.warning("Ingrese una pregunta para generar el informe.")
            else:
                # Regenerar si la pregunta cambió
                if question != st.session_state['last_question']:
                    st.session_state.pop('report', None)
                    st.session_state['last_question'] = question
        
                # Sólo llamar a Gemini si no hay reporte en el estado
                if 'report' not in st.session_state:
                    st.info("Generando informe...")
                    report = generate_final_report(question, db, selected_files)
                    if report is None:
                        st.error("No se pudo generar el informe. Intente de nuevo.")
                        return
                    st.session_state['report'] = report
        
                # Mostrar y permitir edición del informe
                st.markdown("### Informe Final")
                edited_report = st.text_area(
                    "Puedes copiar aquí el texto del informe",
                    value=st.session_state['report'],
                    key="edited_report",
                    height=300
                )
        
                # Generar PDF con el contenido editado y el footer adicional
                final_report_content = edited_report + "\n\n" + additional_info
                pdf_bytes = generate_pdf_html(
                    final_report_content,
                    title="Informe Final",
                    banner_path=banner_file
                )
                st.download_button(
                    "Descargar Informe en PDF",
                    data=pdf_bytes,
                    file_name="Informe_AtelierIA.pdf",
                    mime="application/pdf",
                )
        
                # Registrar el evento en la base de datos
                log_query_event(question, mode="Informe", rating=rating)
                
if __name__ == "__main__":
    main()
