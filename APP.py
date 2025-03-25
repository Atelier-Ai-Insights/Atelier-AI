import os
import json
import datetime
import streamlit as st
import google.generativeai as genai
import boto3
from fpdf import FPDF
from supabase import create_client
from io import BytesIO
import PyPDF2  


# ==============================
# Autenticación Personalizada
# ==============================
ALLOWED_USERS = {
    "Nicolas": "1234",
    "Postobon": "2345",
    "Mondelez": "3456",
    "Meals": "6789",  # Agregamos el nuevo cliente
    "Placeholder_1": "4567",
    "Placeholder_2": "5678",
}

def show_login():
    st.markdown("<div style='display: flex; flex-direction: column; justify-content: center; align-items: center; height: 80vh;'>", unsafe_allow_html=True)
    st.header("Iniciar Sesión")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña (4 dígitos)", type="password")
    if st.button("Ingresar"):
        if username in ALLOWED_USERS and password == ALLOWED_USERS[username]:
            st.session_state.logged_in = True
            st.session_state.user = username
            st.session_state.cliente = username  #  Deduce el cliente del usuario.
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
api_keys = [
    st.secrets["API_KEY_1"],
    st.secrets["API_KEY_2"],
    st.secrets["API_KEY_3"]
]
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
        model_name="gemini-2.0-flash-lite",  # Modelo más potente
        generation_config=generation_config,
        safety_settings=safety_settings
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

def log_query_event(query_text, mode, rating=None):  # Agregamos rating
    data = {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "user_name": st.session_state.user,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "query": query_text,
        "rating": rating  # Guardamos la calificación
    }
    supabase.table("queries").insert(data).execute()


# ==============================
# CARGA DEL ARCHIVO JSON DESDE S3
# ==============================
@st.cache_data(show_spinner=False)
def load_database():
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key = st.secrets["S3_SECRET_KEY"]
    bucket_name = st.secrets.get("S3_BUCKET", "default-bucket")
    object_key = "resultado_presentacion.json"

    s3_client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint_url,
        aws_access_key_id=s3_access_key,
        aws_secret_access_key=s3_secret_key
    )
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        data = json.loads(response['Body'].read().decode("utf-8"))
         # Filtrar por cliente
        if "cliente" in st.session_state:
            data = [doc for doc in data if doc.get("cliente") == st.session_state.cliente]
    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        data = []
    return data


# =====================================================
#  FUNCION PARA OBTENER IMAGEN DE S3 (Para la plantilla)
# =====================================================
@st.cache_data
def load_template_from_s3():
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key = st.secrets["S3_SECRET_KEY"]
    bucket_name = st.secrets.get("S3_BUCKET", "default-bucket")
    object_key_template = "Banner.png" #Nombre del banner

    s3 = boto3.client('s3',
                      endpoint_url=s3_endpoint_url,
                      aws_access_key_id=s3_access_key,
                      aws_secret_access_key=s3_secret_key)

    try:
        # Descarga el archivo a un BytesIO buffer
        template_buffer = BytesIO()
        s3.download_fileobj(Bucket=bucket_name, Key=object_key_template, Fileobj=template_buffer)
        return template_buffer

    except Exception as e:
        st.error(f"Error al descargar la plantilla: {e}")
        return None




def get_relevant_info(db, question, selected_files):
    all_text = ""
    cita_counter = 1  # Contador de citas
    cita_mapping = {}  # Mapa de citas

    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('titulo_estudio', pres.get('nombre_archivo', 'Sin nombre'))}\n"  # Usar título
            for grupo in pres.get("grupos", []):
                contenido = grupo.get('contenido_texto', '')
                all_text += f"Grupo {grupo.get('grupo_index')}: {contenido}\n"

                # Manejo de citas y metadatos
                metadatos = grupo.get("metadatos", {})
                hechos = grupo.get("hechos", {})
                if metadatos:
                    all_text += f"Metadatos: {json.dumps(metadatos)}\n"
                if hechos:
                    #  Citas con formato y numeración
                    if "tipo" in hechos and hechos["tipo"] == "cita":
                        cita_id = f"cita_{cita_counter}"
                        cita_mapping[cita_id] = {
                            "texto": contenido,  # Texto completo de la cita
                             "documento": pres.get('titulo_estudio', pres.get('nombre_archivo')),
                            "grupo": grupo.get('grupo_index')
                        }
                        all_text += f"[Cita {cita_counter}]: {contenido}\n" #formato cita
                        cita_counter += 1
                    else:
                         all_text += f"Hechos: {json.dumps(hechos)}\n"
            all_text += "\n---\n\n"
    return all_text, cita_mapping



def generate_final_report(question, db, selected_files):
    relevant_info, cita_mapping = get_relevant_info(db, question, selected_files)

    # --- PROMPT 1: Resumen Estructurado y Metadatos (Para el Informe Final) ---
    prompt1 = (
        f"Responde la siguiente pregunta: ***{question}***\n\n"
        f"Utiliza la siguiente información de contexto (extractos de documentos de investigación) para elaborar tu respuesta. "
        f"Organiza la información en un resumen estructurado. Extrae metadatos relevantes que permitan identificar la fuente de la información "
        f"(documentos, grupos, etc.). Incluye identificadores de citas (ej. [Cita 1], [Cita 2]) para cualquier información que provenga directamente "
        f"de una cita en los documentos.  NO INCLUYAS EL TEXTO COMPLETO DE LAS CITAS, solo el identificador.\n"
        f"Si la información no es suficiente para responder completamente la pregunta, indica qué información adicional se necesitaría, "
        f"pero intenta dar la mejor respuesta posible con la información disponible.\n"
        f"Prioriza la información que sea más RELEVANTE para responder a la pregunta.  No incluyas detalles irrelevantes o tangenciales.\n"
        f"Si encuentras información contradictoria o ambigua, indícalo.\n\n"
        f"Información de Contexto:\n{relevant_info}\n\n"
        f"Respuesta (Resumen Estructurado y Metadatos):"
    )
    result1 = call_gemini_api(prompt1)
    if result1 is None:
        return None, None

    # --- PROMPT 2: Informe en Prosa (Parte Principal del Informe Final) ---
    prompt2 = (
        f"Redacta la sección principal del informe en prosa, en un tono formal y profesional, dirigido a un cliente empresarial. "
        f"Esta sección debe responder a la pregunta: ***{question}***\n\n"
        f"Utiliza la siguiente información (Resumen Estructurado y Metadatos) como base. Incluye referencias a las citas "
        f"usando los identificadores proporcionados (ej., [Cita 1], [Cita 2]).\n\n"
        f"Resumen Estructurado y Metadatos:\n{result1}\n\n"
        f"Sección Principal del Informe (en prosa):"
    )
    result2 = call_gemini_api(prompt2)
    if result2 is None:
        return None, None

    # --- PROMPT 3: Metodología (Para el Informe Final) ---
    prompt_metodologia = (
        f"Describe detalladamente la metodología utilizada para generar este informe. "
        f"Explica cómo se extrajo y organizó la información de los documentos de investigación originales, "
        f"cómo se identificaron y referenciaron las citas, y cómo se estructuró el informe final. "
        f"Si se utilizaron técnicas o herramientas específicas (como procesamiento del lenguaje natural, modelos de lenguaje, etc.), menciónalas.\n\n"
        f"Sección de Metodología (para el informe final):"
    )
    metodologia = call_gemini_api(prompt_metodologia)
    if metodologia is None:
        metodologia = "No se pudo generar la descripción de la metodología."

    # --- Construcción del Informe Final (Ahora *sin* roles de Gemini) ---
    fecha_actual = datetime.datetime.now().strftime("%d/%m/%Y")
    encabezado = (
        f"# {question}\n"
        f"**Preparado por:** Atelier IA\n"
        f"**Preparado para:** {st.session_state.cliente}\n"
        f"**Fecha de elaboración:** {fecha_actual}\n\n"
    )
    informe_completo = encabezado + "## Metodología\n\n" + metodologia + "\n\n## Informe\n\n" + result2

    # --- Sección de Fuentes (con Callouts) ---
    informe_completo += "\n\n## Fuentes\n\n"
    for cita_id, cita_info in cita_mapping.items():
        informe_completo += f"**{cita_id}**: {cita_info['documento']}, Grupo {cita_info['grupo']}\n"
        informe_completo += f"> {cita_info['texto']}\n\n"

    return informe_completo, cita_mapping  # Devuelve el informe y el mapa


# ==============================
# Función para generar PDF a partir de texto
# ==============================
def generate_pdf(content, title="Documento", template_buffer=None):
    pdf_buffer = BytesIO()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=title, ln=True, align="C")
    pdf.ln(10)

     # Dividir el contenido en secciones si es necesario (para el manejo del footer).
    sections = content.split("\n\n## ") #Separador

    for section in sections:
      if section.startswith("Fuentes"):
        pdf.set_font("Arial", size=10)  # Fuentes más pequeñas
      else:
        pdf.set_font("Arial", size=12)

      for line in section.split("\n"):
          if line.startswith(">"):  # Formato para citas (callouts)
            pdf.set_fill_color(230, 230, 230)  # Fondo gris claro
            pdf.cell(0, 10, line[1:].strip(), ln=True, fill=True) #[1:] para el >
          else:
            pdf.multi_cell(0, 10, line.encode("latin1", errors="replace").decode("latin1"))
      pdf.ln(5)

    pdf.output(pdf_buffer)

     # Combinar PDF con plantilla
    if template_buffer:
        template_buffer.seek(0)  # Reset
        template_pdf = PyPDF2.PdfReader(template_buffer)
        merger = PyPDF2.PdfMerger()
        merger.append(template_pdf)
        merger.append(BytesIO(pdf_buffer.getvalue()))
        output_buffer = BytesIO()
        merger.write(output_buffer)
        return output_buffer.getvalue()

    return pdf_buffer.getvalue()


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
            st.warning("Ingrese un mensaje")
        else:
            st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
            relevant_info, _ = get_relevant_info(db, user_input, selected_files)  # No necesitamos el mapa aquí
            conversation_prompt = "Historial de conversación:\n"
            for msg in st.session_state.chat_history:
                conversation_prompt += f"{msg['role']}: {msg['message']}\n"
            conversation_prompt += "\nInformación de contexto:\n" + relevant_info + "\n\nGenera una respuesta detallada y coherente."

            respuesta = call_gemini_api(conversation_prompt)
            if respuesta is None:
                st.error("Error al generar la respuesta.")
            else:
                st.session_state.chat_history.append({"role": "Asistente", "message": respuesta})
                st.markdown(f"**Asistente:** {respuesta}")
                log_query_event(user_input, mode="Ideacion")

    if st.session_state.chat_history:
        pdf_bytes = generate_pdf("\n".join([f"{m['role']}: {m['message']}" for m in st.session_state.chat_history]), title="Historial de Chat")
        st.download_button("Descargar Chat en PDF", data=pdf_bytes, file_name="chat.pdf", mime="application/pdf")



# ==============================
# Aplicación Principal
# ==============================
def main():
    # La autenticación se realiza primero
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        show_login()

    logout()  # Opción de cerrar sesión

    st.title("Atelier IA")

    st.markdown(
        """
        Bienvenido a **Atelier IA**.
        
        - **Informe de Informes:** Genera un informe formal.
        - **Ideación:** Permite interactuar con los datos.
        """
    )

     # Cargar plantilla
    template_buffer = load_template_from_s3()
    if template_buffer is None:
      st.warning("No se pudo cargar la plantilla. Se generarán PDFs sin plantilla.")


    # Cargar la base de datos
    try:
        db = load_database()
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        st.stop()

    # Filtrar documentos para el modelo
    selected_files = [doc.get("nombre_archivo") for doc in db]

    # Filtrado por marcas en la barra lateral
    marcas = sorted({doc.get("marca", "").strip() for doc in db if doc.get("marca", "").strip()})
    marcas.insert(0, "Todas")
    selected_marca = st.sidebar.selectbox("Seleccione la marca", marcas)
    if selected_marca != "Todas":
        db = [doc for doc in db if doc.get("marca", "").strip().lower() == selected_marca.lower()]
        selected_files = [doc.get("nombre_archivo") for doc in db]  # Actualizar archivos

    modo = st.sidebar.radio("Seleccione el modo", ["Informe de Informes", "Ideación (Conversar con los datos)"])

    if modo == "Informe de Informes":
        st.markdown("### Ingrese una pregunta para generar el informe")
        question = st.text_area("Pregunta", height=150, help="Escriba la pregunta.")
        if st.button("Generar Informe"):
            if not question.strip():
                st.warning("Ingrese una pregunta.")
            else:
                st.info("Generando informe...")
                report, cita_mapping = generate_final_report(question, db, selected_files) #
                if report is None:
                    st.error("No se pudo generar el informe. Intente de nuevo.")
                else:
                    # --- Edición y Adiciones (Opcional) ---
                    st.markdown("### Informe Final")
                    edited_report = st.text_area("Editar Informe (Opcional)", value=report, height=300) #para editar
                    additional_info = st.text_area("Agregar Información Adicional (Opcional)", height=150) #Agregar info

                    #Calificacion
                    rating = st.radio("Calificar el Informe", options=[1, 2, 3, 4, 5], horizontal=True)

                    final_report_content = edited_report + "\n\n" + additional_info #Se unen las ediciones

                    # --- Descarga del PDF ---
                    pdf_bytes = generate_pdf(final_report_content, title="Informe Final", template_buffer=template_buffer)
                    st.download_button("Descargar Informe en PDF", data=pdf_bytes, file_name="informe_final.pdf", mime="application/pdf")

                    log_query_event(question, mode="Informe", rating=rating)  # Guarda la calificación

    else:
        ideacion_mode(db, selected_files)

if __name__ == "__main__":
    main()
