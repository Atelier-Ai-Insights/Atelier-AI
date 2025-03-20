import os
import time
import json
import streamlit as st
import google.generativeai as genai
import boto3  # Asegúrate de instalar boto3: pip install boto3

# -------------------------------
# Estilos personalizados: fondo blanco y textos azules
# -------------------------------
st.markdown(
    """
    <style>
    body {
        background-color: white;
        color: blue;
    }
    .stMarkdown p {
        color: blue;
    }
    .centered {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 80vh;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# -------------------------------
# CONFIGURACIÓN DE LA API DE GEMINI
# -------------------------------
# Cargar las API keys desde st.secrets con los nombres definidos
api_keys = [
    st.secrets["API_KEY_1"],
    st.secrets["API_KEY_2"],
    st.secrets["API_KEY_3"]
]
current_api_key_index = 0

def configure_api():
    global current_api_key_index
    genai.configure(api_key=api_keys[current_api_key_index])
    # En producción se evita mostrar la clave

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

# -------------------------------
# Función para llamar a Gemini
# -------------------------------
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

# -------------------------------
# Función para cargar la base de datos desde S3 de Supabase
# -------------------------------
@st.cache_data(show_spinner=False)
def load_database():
    # Obtener los parámetros de conexión desde los secretos de Streamlit
    s3_endpoint_url = st.secrets["S3_ENDPOINT_URL"]
    s3_access_key = st.secrets["S3_ACCESS_KEY"]
    s3_secret_key = st.secrets["S3_SECRET_KEY"]
    bucket_name = st.secrets.get("S3_BUCKET", "default-bucket")
    object_key = "resultado_presentacion.json"  # Nombre del archivo en el bucket

    # Crear el cliente S3 con boto3
    s3_client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint_url,
        aws_access_key_id=s3_access_key,
        aws_secret_access_key=s3_secret_key
    )

    # Descargar y cargar el archivo JSON
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        data = json.loads(response['Body'].read().decode("utf-8"))
    except Exception as e:
        st.error(f"Error al descargar la base de datos desde S3: {e}")
        data = []
    return data

def get_relevant_info(db, question, selected_files):
    """
    Concatena la información de la DB filtrada por archivos seleccionados.
    """
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

# -------------------------------
# Función para generar el informe final
# -------------------------------
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

# -------------------------------
# Función para iniciar el modo de Ideación (chat interactivo)
# -------------------------------
def ideacion_mode(db, selected_files):
    st.subheader("Modo de Ideación: Conversa con los datos")
    st.markdown("Utiliza este espacio para realizar consultas interactivas. Escribe tu pregunta y el sistema responderá basándose en el historial de la conversación y la información de investigación disponible.")
    
    # Botón para reiniciar la conversación
    if st.button("Reiniciar conversación"):
        st.session_state.chat_history = []
    
    # Inicializar el historial de conversación si no existe
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    # Mostrar el historial de conversación
    st.markdown("#### Historial de conversación:")
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f"**Usuario:** {msg['message']}")
        else:
            st.markdown(f"**Asistente:** {msg['message']}")
    
    # Entrada del usuario
    user_input = st.text_input("Escribe tu consulta o idea:")
    if st.button("Enviar"):
        if not user_input.strip():
            st.warning("Ingrese un mensaje para continuar la conversación.")
        else:
            # Agregar el mensaje del usuario al historial
            st.session_state.chat_history.append({"role": "user", "message": user_input})
            relevant_info = get_relevant_info(db, user_input, selected_files)
            
            # Construir el prompt incluyendo el historial de la conversación
            conversation_prompt = "Historial de conversación:\n"
            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    conversation_prompt += f"Usuario: {msg['message']}\n"
                else:
                    conversation_prompt += f"Asistente: {msg['message']}\n"
            conversation_prompt += "\nInformación de contexto de investigaciones:\n" + relevant_info + "\n\n"
            conversation_prompt += "Genera una respuesta coherente, creativa y detallada que continúe la conversación basándote en el historial y la información de contexto."
            
            respuesta = call_gemini_api(conversation_prompt)
            if respuesta is None:
                st.error("Error al generar la respuesta.")
            else:
                st.session_state.chat_history.append({"role": "assistant", "message": respuesta})
                st.markdown(f"**Asistente:** {respuesta}")

# -------------------------------
# Funciones de autenticación
# -------------------------------
def show_login():
    """Muestra el formulario de login centrado en la pantalla."""
    with st.container():
        st.markdown("<div class='centered'>", unsafe_allow_html=True)
        st.header("Iniciar Sesión")
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            if username == "admin" and password == "secret":
                st.session_state.logged_in = True
                st.session_state.user = username
                st.session_state.allowed_client = None
                st.experimental_rerun()
            elif username.lower() == "postobon" and password == "postobon":
                st.session_state.logged_in = True
                st.session_state.user = username
                st.session_state.allowed_client = "Postobon"
                st.experimental_rerun()
            elif username.lower() == "mondelez" and password == "mondelez":
                st.session_state.logged_in = True
                st.session_state.user = username
                st.session_state.allowed_client = "Mondelez"
                st.experimental_rerun()
            else:
                st.error("Credenciales incorrectas")
        st.markdown("</div>", unsafe_allow_html=True)

def logout():
    if st.sidebar.button("Cerrar Sesión"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.experimental_rerun()

# -------------------------------
# Aplicación principal de Streamlit
# -------------------------------
def main():
    st.title("Atelier IA")
    
    # Explicación para el usuario empresario
    st.markdown(
        """
        Bienvenido a **Atelier IA**, la herramienta inteligente para generar informes y consultas sobre investigaciones empresariales.  
        En esta aplicación podrás:
        - **Generar informes formales:** Basados en información extraída de investigaciones, con citas y referencias concretas.
        - **Interactuar mediante ideación:** Conversar y aclarar dudas con base en los datos disponibles.
        
        Utiliza el menú lateral para filtrar la información según el cliente, marca o producto. Una vez autenticado, tendrás acceso a todas las funcionalidades sin que el formulario de inicio interfiera en tu experiencia.
        """
    )
    
    # Si no se ha iniciado sesión, mostrar el formulario de autenticación en el centro
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        show_login()
        return
    else:
        logout()  # Mostrar la opción de cerrar sesión en la barra lateral
    
    # Cargar la base de datos desde S3 de Supabase
    try:
        db = load_database()
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        st.stop()
    
    allowed_client = st.session_state.get("allowed_client", None)
    
    # Filtrado por cliente según autenticación
    if allowed_client:
        db = [doc for doc in db if doc.get("cliente", "").strip().lower() == allowed_client.lower()]
        st.sidebar.markdown(f"Filtrado automático para el cliente: {allowed_client}")
    else:
        # Si es admin, permite filtrar manualmente por cliente
        clientes = sorted({doc.get("cliente", "").strip() for doc in db if doc.get("cliente", "").strip()})
        clientes = ["Todas"] + list(clientes)
        selected_cliente = st.sidebar.selectbox("Seleccione el cliente", clientes)
        if selected_cliente != "Todas":
            db = [doc for doc in db if doc.get("cliente", "").strip().lower() == selected_cliente.lower()]
    
    # Filtrado por marca (se corrige la identificación de marcas)
    marcas_set = {doc.get("marca", "").strip() for doc in db if doc.get("marca", "").strip() != ""}
    if not marcas_set:
        marcas = ["Sin marca"]
    else:
        marcas = sorted(list(marcas_set))
    marcas.insert(0, "Todas")
    selected_marca = st.sidebar.selectbox("Seleccione la marca", marcas)
    if selected_marca != "Todas":
        db = [doc for doc in db if doc.get("marca", "").strip().lower() == selected_marca.lower()]
    
    # Filtrado opcional por producto (si existe)
    if all("producto" in doc for doc in db):
        productos_disponibles = sorted({doc.get("producto", "").strip() for doc in db if doc.get("producto", "").strip()})
        selected_productos = st.sidebar.multiselect("Seleccione los productos a incluir", productos_disponibles, default=productos_disponibles)
        db = [doc for doc in db if doc.get("producto", "").strip() in selected_productos]
    
    # Se obtiene la lista de archivos filtrados, pero NO se muestra al usuario
    selected_files = [doc.get("nombre_archivo") for doc in db]
    
    # Selección del modo de operación
    modo = st.sidebar.radio("Seleccione el modo", ["Informe de Informes", "Ideación (Conversar con los datos)"])
    
    if modo == "Informe de Informes":
        st.markdown("### Ingrese una pregunta para generar el informe")
        question = st.text_area("Pregunta", height=150, help="Escriba aquí la pregunta o el tema sobre el que desea obtener el informe.")
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
                    with open("informe_final.html", "w", encoding="utf-8") as f:
                        f.write(report)
                    st.success("Informe generado y guardado en 'informe_final.html'.")
    else:
        # Modo de Ideación (chat interactivo)
        ideacion_mode(db, selected_files)

if __name__ == "__main__":
    main()

