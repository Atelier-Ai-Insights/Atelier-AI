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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from supabase import create_client
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
        
# ====== Helper para reiniciar el flujo de reportes ======
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
        model_name="gemini-1.5-flash",
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
        text = response.text
        text = html.unescape(text)
        return text
    except Exception as e:
        st.error(f"Error en la llamada a Gemini: {e}. Intentando cambiar API Key.")
        switch_api_key()
        try:
            response = model.generate_content([prompt])
            text = response.text
            text = html.unescape(text)
            return text
        except Exception as e2:
            st.error(f"Error GRAVE en la llamada a Gemini: {e2}")
            return None

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
    html_text = markdown2.markdown(
        markdown_text,
        extras=["fenced-code-blocks", "tables", "break-on-newline"]
    )
    soup = BeautifulSoup(html_text, "html.parser")
    container = soup.body or soup

    for elem in container.children:
        if elem.name:
            if elem.name.startswith("h"):
                try:
                    level = int(elem.name[1])
                except:
                    level = 1
                pdf.add_title(elem.get_text(strip=True), level=level)
            elif elem.name == "p":
                pdf.add_paragraph(elem.decode_contents())
            elif elem.name == "ul":
                for li in elem.find_all("li"):
                    pdf.add_paragraph("• " + li.decode_contents())
            elif elem.name == "ol":
                for idx, li in enumerate(elem.find_all("li"), 1):
                    pdf.add_paragraph(f"{idx}. {li.decode_contents()}")
            else:
                pdf.add_paragraph(elem.decode_contents())
        else:
            text = elem.string
            if text and text.strip():
                pdf.add_paragraph(text)

# ==============================
# CARGA DEL ARCHIVO JSON DESDE S3
# ==============================
@st.cache_data(show_spinner=False)
def load_database(cliente: str):
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
        
        cliente_norm = normalize_text(cliente or "")

        if cliente_norm != "insights-atelier":
            filtered_data = []
            for doc in data:
                doc_cliente_norm = normalize_text(doc.get("cliente", ""))
                if "atelier" in doc_cliente_norm or cliente_norm in doc_cliente_norm:
                    filtered_data.append(doc)
            data = filtered_data
    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        data = []
    return data

# ==============================
# EXTRACCIÓN DE DATOS Y FILTROS
# ==============================
def extract_brand(filename):
    if not filename or "In-ATL_" not in filename:
        return ""
    return filename.split("In-ATL_")[1].rsplit(".", 1)[0]

def apply_filter_criteria(db, selected_filter):
    if not selected_filter or selected_filter == "Todos":
        return db
    return [doc for doc in db if doc.get("filtro") == selected_filter]

# =====================================================
# FUNCIONES DE GENERACIÓN DE INFORMES Y PDF
# =====================================================
banner_file = "Banner (2).jpg"

def get_relevant_info(db, question, selected_files):
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"
            for grupo in pres.get("grupos", []):
                contenido = grupo.get("contenido_texto", "")
                all_text += f"Grupo {grupo.get('grupo_index')}: {contenido}\n"
                metadatos = grupo.get("metadatos", {})
                hechos      = grupo.get("hechos", {})
                if metadatos:
                    all_text += f"Metadatos: {json.dumps(metadatos, ensure_ascii=False)}\n"
                if hechos:
                    if hechos.get("tipo") == "cita":
                        all_text += "[Cita]\n"
                    else:
                        all_text += f"Hechos: {json.dumps(hechos, ensure_ascii=False)}\n"
            all_text += "\n---\n\n"
    return all_text

def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)
    
    # Prompt 1: Extrae hallazgos clave y referencias.
    prompt1 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones:\n"
        "1. Identifica en la pregunta la marca exacta y/o el producto exacto sobre el cual se hace la consulta. Sé muy específico y riguroso en referenciar información asociada a la marca y/o producto consultado.\n"
        "2. Reitera la pregunta del cliente: ***{question}***.\n"
        "3. Utiliza la 'Información de Contexto' (extractos de documentos de investigación) para extraer los hallazgos más relevantes que respondan directamente a la pregunta. Cuando se pregunte por una marca (ejemplo: oreo) siempre traer información de todos los reportes relacionados.\n"
        "4. No incluyas el texto completo de las citas, sino extractos breves que permitan identificar la fuente.\n"
        "5. Incluye metadatos relevantes (documentos, grupos, etc.) e indica en cada hallazgo si la cita sigue el estilo IEEE (ejemplo: [1]).\n"
        "6. En la sección 'Referencias', asocia cada número a la referencia completa, no escribas el nombre del archivo, sino el titulo del proyecto (ejemplo: [1] 'Título del Proyecto', año, etc.). Siempre provee las referencias citadas.\n"
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

    # Prompt 2: Redacta el informe principal en prosa utilizando el resumen anterior.
    prompt2 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        "Instrucciones Generales:\n"
        "1. Identifica en la pregunta la marca y/o el producto exacto. Responde de manera específica y rigurosa a lo que el cliente pregunta.\n"
        "2. Recuerda que todos los estudios en la base de datos fueron realizados por Atelier. Menciónalo si es relevante, especialmente en 'Principales Hallazgos'.\n"
        "3. Actúa como un analista experto en ciencias del comportamiento, en investigación de mercados, en marketing y en comunicación estratégica. Enfócate en claridad, síntesis poderosa y pensamiento estructurado.\n"
        "4. El estilo de redacción debe ser claro, directo, conciso y memorable (inspirado en “Ideas que pegan” de Chip Heath y Dan Heath). Evita lenguaje técnico innecesario; prioriza lo relevante y accionable.\n\n"
        "Estructura del Informe (sé breve y preciso en cada sección):\n\n"
        "##1. **Introducción**:\n"
        "   - Preserva esta sección. Plantea el contexto y la pregunta central. Usa un un dato inesperado para captar la atención.\n\n"
        "##2. **Principales Hallazgos**:\n"
        "   - Presenta de forma estructurada los hechos más relevantes descubiertos, directamente desde la sección de resultados de los diferentes reportes y la información de contexto.\n"
        "   - Asegúrate de que cada hallazgo responda a la pregunta del cliente y ofrezca valor original y que sume valor para responder a la pregunta.\n"
        "   - Utiliza solo información relevante y que haga referencia a la marca y al producto citados. No utilices estudios de forma innecesaria.\n"
        "   - Referencia en formato IEEE (ej. [1]), usando el título del estudio o el producto del que se habla, más que el nombre del archivo.\n\n"
        "##3. **Insights**:\n"
        "   - Extrae aprendizajes y verdades profundas a partir de los hallazgos. Utiliza analogías y comparaciones que refuercen el mensaje y transformen la comprensión del problema. Sé conciso. Utiliza frases suscitantas, es decir, frase cortas con mucho significado\n\n"
        "##4. **Conclusiones**:\n"
        "   - Sintetiza la información y ofrece una dirección clara basada en los insights. Evita repetir información.\n\n"
        "##5. **Recomendaciones**:\n"
        "   - Con base en el informe, proporciona 3-4 recomendaciones concretas, creativas, precisas y accionables que sirvan como inspiración para la toma de decisiones.\n"
        "   - Deben estar alineadas con los insights y conclusiones. Evita la extensión innecesaria.\n\n"
        "##6. **Referencias**:\n"
        "   - Cita el título del estudio (no el nombre del archivo), utilizando la información de la primera diapositiva o metadatos disponibles.\n\n"
        "Utiliza el siguiente resumen (Hallazgos Clave y Referencias) y la Información de Contexto para elaborar el informe:\n\n"
        "5. MUY IMPORTANTE: Asegúrate de que los nombres de marcas y productos estén correctamente espaciados del texto circundante. Por ejemplo, escribe 'la marca Crem Helado debe...' en lugar de 'lamarcaCrem Heladodebe...'. Presta especial atención a este detalle de formato para asegurar la legibilidad.\n\n"
        f"Resumen de Hallazgos Clave y Referencias:\n{result1}\n\n"
        f"Información de Contexto Adicional (si es necesaria para complementar el resumen):\n{relevant_info}\n\n"
        "Por favor, redacta el informe completo respetando la estructura y las instrucciones, en un estilo profesional, claro, conciso y coherente, utilizando Markdown."
    )
    result2 = call_gemini_api(prompt2)
    if result2 is None: return None
    
    fecha_actual = datetime.datetime.now().strftime("%d/%m/%Y")
    cliente_nombre = st.session_state.get('cliente', 'Cliente Confidencial').capitalize()
    encabezado = (
        f"# {question}\n\n"
        f"**Preparado por:**\n\nAtelier Data Studio\n\n"
        f"**Preparado para:**\n\n{cliente_nombre}\n\n"
        f"**Fecha de elaboración:**\n\n{fecha_actual}\n\n"
    )
    informe_completo = encabezado + result2
    return informe_completo

def clean_text(text):
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;')

class PDFReport:
    # ... (El código de la clase PDFReport no ha cambiado, se mantiene igual)
    pass 

def generate_pdf_html(content, title="Documento Final", banner_path=None, output_filename=None):
    # ... (El código de la función generate_pdf_html no ha cambiado, se mantiene igual)
    pass

def ideacion_mode(db, selected_files):
    st.subheader("Modo Conversación: Conversa con los datos")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        st.markdown(f"**{msg['role'].capitalize()}:** {msg['message']}")

    st.markdown(
        "Para hacer nuevas consultas, escribe tu pregunta en el cuadro de abajo "
        "y presiona **Enviar pregunta**."
    )
    user_input = st.text_area("Pregunta algo…", height=150)

    if st.button("Enviar pregunta"):
        if not user_input.strip():
            st.warning("Ingrese una pregunta para continuar la conversación.")
        else:
            st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
            relevant = get_relevant_info(db, user_input, selected_files)
            conv_prompt = (
                "Historial de conversación:\n"
                + "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history)
                + "\n\nInformación de contexto:\n" + relevant
                + "\n\nInstrucciones:\n"
                "- Responde usando únicamente la sección de resultados de los reportes.\n"
                "- Responde de forma creativa, eres un experto en las áreas de la psicología del consumidor y en innovación y creativiadad, así que ayudarás al usuario que esta hablando contigo a conversar con sus datos para ofrecerle ideas novedosas basadas en la información y en los datos que hay sobre la temática que te está solicitando. comienza siempre dando un breve resumen de los proyectos relacionados con la solicitud\n"
                "- Escribe de forma clara, sintética y concreta\n"
                "- Incluye citas numeradas al estilo IEEE (por ejemplo, [1]).\n\n"
                "Respuesta detallada:"
            )
            resp = call_gemini_api(conv_prompt)
            if resp:
                st.session_state.chat_history.append({"role": "Asistente", "message": resp})
                log_query_event(user_input, mode="Conversación")
                st.rerun() # Para mostrar el nuevo mensaje inmediatamente
            else:
                st.error("Error al generar la respuesta.")

    if st.session_state.chat_history:
        pdf_bytes = generate_pdf_html(
            "\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history),
            title="Historial de Chat",
            banner_path=banner_file
        )
        st.download_button("Descargar Chat en PDF", data=pdf_bytes, file_name="chat.pdf", mime="application/pdf")
        st.button("Nueva conversación", on_click=reset_chat_workflow, key="new_chat_btn")


def report_mode(db, selected_files):
    st.markdown("### Generar reporte")
    question = st.text_area("Escribe tu consulta…", value=st.session_state.get("last_question", ""), height=150, key="report_question")
    personalization = st.text_area("Personaliza el reporte…", value=st.session_state.get("personalization", ""), height=150, key="personalization")

    if st.button("Generar Reporte"):
        if not question.strip():
            st.warning("Ingrese una consulta.")
        else:
            if question != st.session_state.get("last_question"):
                st.session_state.pop("report", None)
                st.session_state["last_question"] = question

            if "report" not in st.session_state:
                with st.spinner("Generando informe... Este proceso puede tardar un momento."):
                    report = generate_final_report(question, db, selected_files)
                if report is None:
                    st.error("No se pudo generar el informe.")
                    return
                st.session_state["report"] = report

    if "report" in st.session_state:
        st.markdown("### Informe Final")
        edited = st.text_area("Informe generado (puedes editar el texto aquí antes de descargar):", value=st.session_state["report"], height=400, key="report_edit")
        
        final_content = edited
        if personalization.strip():
            final_content += "\n\n---\n\n## Notas Adicionales\n\n" + personalization

        pdf_bytes = generate_pdf_html(final_content, title="Informe Final", banner_path=banner_file)
        st.download_button("Descargar Informe en PDF", data=pdf_bytes, file_name="Informe_AtelierIA.pdf", mime="application/pdf")
        
        st.button("Nueva consulta", on_click=reset_report_workflow, key="new_report_query_btn")
        
        rating = st.session_state.get("rating", None)
        log_query_event(question, mode="Generación", rating=rating)

# === NUEVA FUNCIÓN ===
def concept_generation_mode(db, selected_files):
    """
    Modo de Generación de Conceptos:
    Crea un concepto de producto a partir de una idea inicial
    y los hallazgos de los estudios seleccionados.
    """
    st.subheader("Modo Generación de Conceptos")
    st.markdown("A partir de una idea inicial y los hallazgos de los estudios seleccionados, generaremos un concepto de producto sólido y estructurado.")

    product_idea = st.text_area(
        "Describe tu idea de producto o servicio:",
        height=150,
        placeholder="Ej: Un snack saludable para niños basado en frutas locales y sin azúcar añadida."
    )

    if st.button("Generar Concepto"):
        if not product_idea.strip():
            st.warning("Por favor, describe tu idea de producto para continuar.")
        else:
            with st.spinner("Analizando hallazgos y generando el concepto..."):
                # 1. Obtener contexto relevante de los documentos seleccionados
                context_info = get_relevant_info(db, product_idea, selected_files)
                
                # 2. Crear el prompt específico para la generación de conceptos
                prompt = f"""
                **Tarea:** Eres un estratega de innovación y marketing. A partir de una idea de producto y un contexto de estudios de mercado, debes desarrollar un concepto de producto estructurado.

                **Idea de Producto del Usuario:**
                "{product_idea}"

                **Contexto (Hallazgos de Estudios de Mercado):**
                "{context_info}"

                **Instrucciones:**
                Genera una respuesta en formato Markdown con la siguiente estructura exacta. Basa tus respuestas en los hallazgos del contexto proporcionado. Sé claro, conciso y accionable.

                ---

                ### 1. Definición de la Necesidad del Consumidor
                * Identifica y describe las tensiones, deseos o problemas clave de los consumidores que se encuentran en el **Contexto de los estudios**. Conecta estos hallazgos con la oportunidad para la idea de producto.

                ### 2. Descripción del Producto
                * Basado en la **Idea del Usuario**, describe el producto o servicio propuesto. Detalla sus características principales y cómo funcionaría. Sé creativo pero mantente anclado en la necesidad detectada.

                ### 3. Beneficios Clave
                * Enumera 3-4 beneficios principales del producto. Cada beneficio debe responder directamente a una de las necesidades del consumidor identificadas en el punto 1 y estar sustentado por la evidencia del **Contexto**.

                ### 4. Frase Resumen (Claim)
                * Crea una frase corta, memorable y poderosa que resuma la esencia y la principal promesa de valor del producto. Debe ser sucinta y con mucho significado.
                """

                # 3. Llamar a la API y mostrar la respuesta
                response = call_gemini_api(prompt)

                if response:
                    st.markdown("---")
                    st.markdown("### Concepto Generado")
                    st.markdown(response)
                    log_query_event(product_idea, mode="Generación de Conceptos")
                else:
                    st.error("No se pudo generar el concepto. Inténtalo de nuevo.")

def main():
    if not st.session_state.get("logged_in"):
        show_login()

    st.title("Atelier Data Studio")
    st.markdown(
        "Atelier Data Studio es una herramienta impulsada "
        "por modelos lingüísticos de vanguardia para realizar consultas "
        "y conversar con datos arrojados por los distintos estudios de mercados "
        "realizados para el entendimiento del consumidor y del mercado.\n\n"
    )

    try:
        db = load_database(st.session_state.cliente)
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        st.stop()

    # === MODIFICADO ===
    # Se añade la nueva opción "Generación de conceptos"
    modo = st.sidebar.radio(
        "Seleccione el modo de uso:",
        ["Generar un reporte de reportes", "Conversaciones creativas", "Generación de conceptos"]
    )

    # Filtros en la sidebar
    filtros = sorted({doc.get("filtro", "") for doc in db if doc.get("filtro")})
    filtros.insert(0, "Todos")
    selected_filter = st.sidebar.selectbox("Seleccione la marca:", filtros)
    db = apply_filter_criteria(db, selected_filter)
    
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
        st.sidebar.radio("Califique el informe:", [1, 2, 3, 4, 5], horizontal=True, key="rating")

    # Botón Cerrar Sesión
    if st.sidebar.button("Cerrar Sesión", key="logout_main"):
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()

    selected_files = [d.get("nombre_archivo") for d in db]

    # === MODIFICADO ===
    # Lógica para llamar a la función del modo seleccionado
    if modo == "Generar un reporte de reportes":
        report_mode(db, selected_files)
    elif modo == "Conversaciones creativas":
        ideacion_mode(db, selected_files)
    else: # Este es el nuevo modo
        concept_generation_mode(db, selected_files)

if __name__ == "__main__":
    main()
