import os
import time
import json
import datetime
import streamlit as st
import google.generativeai as genai
import boto3  # pip install boto3
from fpdf import FPDF  # pip install fpdf
from supabase import create_client  # pip install supabase

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
    # No se muestra la clave en producción

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
        model_name="gemini-2.0-flash",  # Verifica que el modelo esté disponible
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

def log_query_event(query_text, mode):
    """Registra la consulta en la tabla 'queries' de Supabase."""
    data = {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "user_name": st.session_state.user,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,         # 'Informe' o 'Ideacion'
        "query": query_text
    }
    supabase.table("queries").insert(data).execute()

# ==============================
# CARGA DEL ARCHIVO JSON DESDE S3 (para alimentar al modelo)
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
    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        data = []
    return data

def get_relevant_info(db, question, selected_files):
    """Concatena la información de la DB filtrada por archivos seleccionados."""
    all_text = ""
    for pres in db:
        if pres.get("nombre_archivo") in selected_files:
            all_text += f"Documento: {pres.get('nombre_archivo', 'Sin nombre')}\n"
            for grupo in pres.get("grupos", []):
                all_text += f"Grupo {grupo.get('grupo_index')}: {grupo.get('contenido_texto', '')}\n"
                metadatos = grupo.get("metadatos", {})
                hechos = grupo.get("hechos", {})
                if metadatos:
                    all_text += f"Cita (metadatos): {json.dumps(metadatos)}\n"
                if hechos:
                    all_text += f"Cita (hechos): {json.dumps(hechos)}\n"
            all_text += "\n---\n\n"
    return all_text

def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)
    prompt1 = (
        f"Con base en la siguiente información extraída de investigaciones (con citas y referencias), responde a la siguiente pregunta:\n"
        f"'{question}'\n\n"
        "Organiza la información en un resumen estructurado y extrae metadatos relevantes que permitan identificar documentos y hechos concretos.\n\n"
        "Información:\n" + relevant_info
    )
    result1 = call_gemini_api(prompt1)
    if result1 is None:
        return None
    prompt2 = (
        f"Utilizando el resumen y los metadatos que se muestran a continuación, redacta un informe formal en prosa dirigido a un cliente empresarial. "
        "El informe debe incluir citas concretas, referencias a los documentos de origen y describir hechos relevantes de la investigación.\n\n"
        "Resumen y Metadatos:\n" + result1 + "\n\n"
        "Informe:"
    )
    result2 = call_gemini_api(prompt2)
    return result2

# ==============================
# Función para generar PDF a partir de texto
# ==============================
def generate_pdf(content, title="Documento"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=title, ln=True, align="C")
    pdf.ln(10)
    for line in content.split("\n"):
        pdf.multi_cell(0, 10, line)
    return pdf.output(dest="S").encode("latin1")

# ==============================
# MODO DE IDEACIÓN (CHAT INTERACTIVO)
# ==============================
def ideacion_mode(db, selected_files):
    st.subheader("Modo de Ideación: Conversa con los datos")
    st.markdown("Utiliza este espacio para realizar consultas interactivas. Escribe tu pregunta y el sistema responderá basándose en el historial y la información de investigación disponible.")
    
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
            conversation_prompt += "\nInformación de contexto:\n" + relevant_info + "\n\nGenera una respuesta detallada y coherente."
            respuesta = call_gemini_api(conversation_prompt)
            if respuesta is None:
                st.error("Error al generar la respuesta.")
            else:
                st.session_state.chat_history.append({"role": "Asistente", "message": respuesta})
                st.markdown(f"**Asistente:** {respuesta}")
                # Registrar la consulta en Supabase
                log_query_event(user_input, mode="Ideacion")
    
    if st.session_state.chat_history:
        pdf_bytes = generate_pdf("\n".join([f"{m['role']}: {m['message']}" for m in st.session_state.chat_history]), title="Historial de Chat")
        st.download_button("Descargar Chat en PDF", data=pdf_bytes, file_name="chat.pdf", mime="application/pdf")

# ==============================
# Autenticación Personalizada
# ==============================
ALLOWED_USERS = {"Nicolas", "Postobon", "Mondelez", "Placeholder_1", "Placeholder_2"}

def show_login():
    st.markdown("<div style='display: flex; justify-content: center; align-items: center; height: 80vh;'>", unsafe_allow_html=True)
    st.header("Iniciar Sesión")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if username in ALLOWED_USERS and password == "secret":  # Contraseña fija para este ejemplo
            st.session_state.logged_in = True
            st.session_state.user = username
            st.experimental_set_query_params(user=username)  # Opcional: para persistir la info
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
# Aplicación Principal
# ==============================
def main():
    st.title("Atelier IA")
    
    # La autenticación se realiza primero
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        show_login()
    
    logout()  # Opción de cerrar sesión en la barra lateral

    st.markdown(
        """
        Bienvenido a **Atelier IA**, la herramienta inteligente para generar informes y consultas sobre investigaciones empresariales.
        
        Funcionalidades:
        - **Informe de Informes:** Genera un informe formal basado en información extraída de investigaciones (usando datos desde S3).
        - **Ideación (Conversar con los datos):** Permite interactuar y aclarar dudas a través de un chat interactivo.
        
        Cada consulta se registra para mejorar el servicio.
        """
    )
    
    # Cargar la base de datos (archivo JSON desde S3)
    try:
        db = load_database()
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        st.stop()
    
    # Se usa la lista de archivos filtrados para alimentar al modelo (no se muestra al usuario)
    selected_files = [doc.get("nombre_archivo") for doc in db]
    
    modo = st.sidebar.radio("Seleccione el modo", ["Informe de Informes", "Ideación (Conversar con los datos)"])
    
    if modo == "Informe de Informes":
        st.markdown("### Ingrese una pregunta para generar el informe")
        question = st.text_area("Pregunta", height=150, help="Escriba la pregunta o tema para el informe.")
        if st.button("Generar Informe"):
            if not question.strip():
                st.warning("Ingrese una pregunta para generar el informe.")
            else:
                st.info("Generando informe. Esto puede tardar unos minutos...")
                report = generate_final_report(question, db, selected_files)
                if report is None:
                    st.error("No se pudo generar el informe. Intente de nuevo más tarde.")
                else:
                    st.markdown("### Informe Final")
                    st.markdown(report, unsafe_allow_html=True)
                    pdf_bytes = generate_pdf(report, title="Informe Final")
                    st.download_button("Descargar Informe en PDF", data=pdf_bytes, file_name="informe_final.pdf", mime="application/pdf")
                    # Registrar la consulta
                    log_query_event(question, mode="Informe")
    else:
        ideacion_mode(db, selected_files)

if __name__ == "__main__":
    main()
