import datetime
import html  # para el monkey patch
import json
import os
import tempfile
import unicodedata
from io import BytesIO

import boto3  # pip install boto3
import google.generativeai as genai
import markdown2
import streamlit as st
from fpdf import FPDF, HTMLMixin  # pip install fpdf2

# --- Monkey patch para HTML2FPDF ---
from fpdf.html import HTML2FPDF
from supabase import create_client  # pip install supabase

if not hasattr(HTML2FPDF, "unescape"):
    HTML2FPDF.unescape = staticmethod(html.unescape)

# ==============================
# Autenticación Personalizada
# ==============================
ALLOWED_USERS = {
    "Nicolas": "1234",
    "Postobon": "2345",
    "Mondelez": "3456",
    "Meals": "6789",  # Nuevo cliente
    "Placeholder_1": "4567",
    "Placeholder_2": "5678",
}


def show_login():
    st.markdown(
        "<div style='display: flex; flex-direction: column; justify-content: center; align-items: center;'>",
        unsafe_allow_html=True,
    )
    st.header("Iniciar Sesión")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña (4 dígitos)", type="password")
    if st.button("Ingresar"):
        if username in ALLOWED_USERS and password == ALLOWED_USERS[username]:
            st.session_state.logged_in = True
            st.session_state.user = username
            st.session_state.cliente = username  # Se deduce el cliente según el usuario
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


def logout():
    if st.sidebar.button("Cerrar Sesión"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
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
    "temperature": 0.4,
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
    return response.text


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


# ==============================
# CARGA DEL ARCHIVO JSON DESDE S3 (para alimentar al modelo)
# ==============================
@st.cache_data(show_spinner=False)
def load_database():
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key = st.secrets["S3_SECRET_KEY"]
    bucket_name = st.secrets.get("S3_BUCKET")
    object_key = "resultado_presentacion (1).json"

    s3_client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint_url,
        aws_access_key_id=s3_access_key,
        aws_secret_access_key=s3_secret_key,
    )
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        # Filtrar por cliente solo si el usuario NO es "Nicolas" (admin)
        if (
            "cliente" in st.session_state
            and normalize_text(st.session_state.cliente) != "nicolas"
        ):
            data = [
                doc
                for doc in data
                if normalize_text(doc.get("cliente", ""))
                == normalize_text(st.session_state.cliente)
            ]
        # Sino, se usan todos los documentos
    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        data = []
    return data


# =====================================================
# FUNCION PARA OBTENER IMAGEN DE S3 (Para la plantilla/banner)
# =====================================================
@st.cache_data
def load_template_from_s3():
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key = st.secrets["S3_SECRET_KEY"]
    bucket_name = st.secrets.get("S3_BUCKET")
    object_key_template = "Banner.png"

    try:
        template_buffer = BytesIO()
        boto3.client(
            "s3",
            endpoint_url=s3_endpoint_url,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
        ).download_fileobj(
            Bucket=bucket_name, Key=object_key_template, Fileobj=template_buffer
        )
        if template_buffer.getbuffer().nbytes > 0:
            return template_buffer
        else:
            st.warning("La plantilla descargada está vacía.")
            return None
    except Exception as e:
        st.error(f"Error al descargar la plantilla: {e}")
        return None


# ==============================
# Función para obtener la información relevante
# ==============================
def get_relevant_info(db, question, selected_files):
    all_text = ""
    # Se construye el texto de contexto que se entregará a Gemini.
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

    prompt1 = (
        f"Pregunta del Cliente: ***{question}***\n\n"
        f"Repite la pregunta: ***{question}***. Asegúrate de que la respuesta esté completamente alineada con ella. "
        f"Utiliza la siguiente información de contexto (extractos de documentos de investigación) para elaborar un resumen estructurado. "
        f"Incluye metadatos relevantes (documentos, grupos, etc.) e indica en cada caso si proviene de una cita (solo el indicador '[Cita]'). "
        f"No incluyas el texto completo de las citas.\n\n"
        f"Información de Contexto:\n{relevant_info}\n\n"
        f"Respuesta (Resumen Estructurado y Metadatos):"
    )
    result1 = call_gemini_api(prompt1)
    if result1 is None:
        return None

    prompt2 = (
        f"Redacta la sección principal del informe en prosa, en un tono formal y profesional, dirigido a un cliente empresarial. "
        f"Repite la pregunta: ***{question}***. La respuesta debe estar completamente alineada con la pregunta del cliente. "
        f"Utiliza el siguiente resumen estructurado y metadatos como base. Al final, agrega una sección titulada 'Fuentes', "
        f"donde cada línea comience con '[Cita X] - ' seguido del texto de la cita. En el cuerpo del informe, las citas deben aparecer como call-out, precedidas por '>>'.\n\n"
        f"Resumen Estructurado y Metadatos:\n{result1}\n\n"
        f"Sección Principal del Informe (en prosa) con Fuentes:"
    )
    result2 = call_gemini_api(prompt2)
    if result2 is None:
        return None

    fecha_actual = datetime.datetime.now().strftime("%d/%m/%Y")
    encabezado = (
        f"# {question}\n"
        f"**Preparado por:** Atelier IA\n"
        f"**Preparado para:** {st.session_state.cliente}\n"
        f"**Fecha de elaboración:** {fecha_actual}\n\n"
    )
    informe_completo = (
        encabezado + result2
    )  # Se asume que Gemini ya incluye la sección "Fuentes"
    return informe_completo


# ==============================
# Clase para PDF con soporte HTML
# ==============================
class MyFPDF(FPDF, HTMLMixin):
    pass


def encode_latin1_with_space(text):
    # Recorre cada carácter y verifica si puede codificarse en latin1.
    # Si no puede, lo reemplaza por un espacio en blanco.
    result = []
    for char in text:
        try:
            char.encode("latin1")
            result.append(char)
        except UnicodeEncodeError:
            result.append(" ")
    return "".join(result)


def generate_pdf_html(content, title="Documento", template_buffer=None):
    # Convertir Markdown a HTML con extras para preservar saltos de línea y otros formatos importantes
    html_content = markdown2.markdown(
        content, extras=["break-on-newline", "fenced-code-blocks", "tables"]
    )
    # Reemplazar caracteres problemáticos específicos
    html_content = html_content.replace("\u201c", " ")
    html_content = html_content.replace("\u2013", " ")
    html_content = html_content.replace("\u201d", " ")

    pdf = MyFPDF()
    # Agregar banner si existe
    if template_buffer:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(template_buffer.getvalue())
                tmp_path = tmp.name
            pdf.add_page()
            pdf.image(tmp_path, x=10, y=8, w=pdf.w - 20)
            os.remove(tmp_path)
            pdf.ln(20)
        except Exception as e:
            st.warning(f"Error al agregar el banner: {e}")
            pdf.add_page()
    else:
        pdf.add_page()

    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=title, ln=True, align="C")
    pdf.ln(10)

    # Asegurarse de que el contenido HTML esté encapsulado en párrafos
    if not html_content.startswith("<p>"):
        html_content = f"<p>{html_content}</p>"

    pdf.write_html(html_content)
    # Obtener el contenido PDF generado en una cadena
    pdf_output = pdf.output(dest="S")
    # Reemplazar los caracteres que no se pueden codificar por espacios en blanco
    safe_pdf_output = encode_latin1_with_space(pdf_output)
    pdf_bytes = safe_pdf_output.encode("latin1")
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
            st.session_state.chat_history.append(
                {"role": "Usuario", "message": user_input}
            )
            relevant_info = get_relevant_info(db, user_input, selected_files)
            conversation_prompt = "Historial de conversación:\n"
            for msg in st.session_state.chat_history:
                conversation_prompt += f"{msg['role']}: {msg['message']}\n"
            conversation_prompt += (
                "\nInformación de contexto:\n"
                + relevant_info
                + "\n\nGenera una respuesta detallada y coherente."
            )
            respuesta = call_gemini_api(conversation_prompt)
            if respuesta is None:
                st.error("Error al generar la respuesta.")
            else:
                st.session_state.chat_history.append(
                    {"role": "Asistente", "message": respuesta}
                )
                st.markdown(f"**Asistente:** {respuesta}")
                log_query_event(user_input, mode="Ideacion")
    if st.session_state.chat_history:
        pdf_bytes = generate_pdf_html(
            "\n".join(
                [f"{m['role']}: {m['message']}" for m in st.session_state.chat_history]
            ),
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
        Bienvenido a **Atelier IA**.

        - **Informe de Informes:** Genera un informe formal.
        - **Ideación:** Permite interactuar con los datos.
        """
    )
    template_buffer = load_template_from_s3()
    if template_buffer is None:
        st.warning("No se pudo cargar el banner. Se generarán PDFs sin banner.")

    try:
        db = load_database()
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        st.stop()

    st.write(f"DEBUG: Documentos cargados: {len(db)}")
    selected_files = [doc.get("nombre_archivo") for doc in db]

    # Filtrado por marcas en la barra lateral
    marcas = sorted(
        {doc.get("marca", "").strip() for doc in db if doc.get("marca", "").strip()}
    )
    marcas.insert(0, "Todas")
    selected_marca = st.sidebar.selectbox("Seleccione la marca", marcas)
    if selected_marca != "Todas":
        db = [
            doc
            for doc in db
            if normalize_text(doc.get("marca", "")) == normalize_text(selected_marca)
        ]
        selected_files = [doc.get("nombre_archivo") for doc in db]
    st.write(f"DEBUG: Documentos tras filtrar por marca: {len(db)}")

    modo = st.sidebar.radio(
        "Seleccione el modo",
        ["Informe de Informes", "Ideación (Conversar con los datos)"],
    )
    if modo == "Informe de Informes":
        st.markdown("### Ingrese una pregunta para generar el informe")
        question = st.text_area(
            "Pregunta", height=150, help="Escriba la pregunta o tema para el informe."
        )
        # Widgets siempre visibles en la barra lateral para información adicional y rating
        additional_info = st.sidebar.text_area(
            "Agregar Información Adicional (Opcional)",
            key="additional_info",
            height=150,
        )
        rating = st.sidebar.radio(
            "Calificar el Informe",
            options=[1, 2, 3, 4, 5],
            horizontal=True,
            key="rating",
        )
        if st.button("Generar Informe"):
            if not question.strip():
                st.warning("Ingrese una pregunta para generar el informe.")
            else:
                if "report" not in st.session_state:
                    st.info("Generando informe...")
                    report = generate_final_report(question, db, selected_files)
                    if report is None:
                        st.error("No se pudo generar el informe. Intente de nuevo.")
                        return
                    st.session_state.report = report
                st.markdown("### Informe Final")
                edited_report = st.text_area(
                    "Editar Informe (Opcional)",
                    value=st.session_state.report,
                    key="edited_report",
                    height=300,
                )
                final_report_content = edited_report + "\n\n" + additional_info
                pdf_bytes = generate_pdf_html(
                    final_report_content,
                    title="Informe Final",
                    template_buffer=template_buffer,
                )
                st.download_button(
                    "Descargar Informe en PDF",
                    data=pdf_bytes,
                    file_name="informe_final.pdf",
                    mime="application/pdf",
                )
                log_query_event(question, mode="Informe", rating=rating)
    else:
        ideacion_mode(db, selected_files)


if __name__ == "__main__":
    main()
