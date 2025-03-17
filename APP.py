import os
import time
import json
import streamlit as st
import google.generativeai as genai

# -------------------------------
# CONFIGURACIÓN DE LA API DE GEMINI
# -------------------------------
api_keys = [
    "AIzaSyAEaxnxgoMXwg9YVRmRH_tKVGD3pNgHKkk",  # Reemplaza con tu API Key 1
    "AIzaSyDKzApq_jz4gOJJYG_PbBwc47Lw96FxHAY",
    "AIzaSyAEaxnxgoMXwg9YVRmRH_tKVGD3pNgHKkk"
]
current_api_key_index = 0

def configure_api():
    global current_api_key_index
    genai.configure(api_key=api_keys[current_api_key_index])
    # Para producción, no mostramos la clave
    st.write(f"API configurada con clave {current_api_key_index+1}/{len(api_keys)}")

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
# Función para cargar la base de datos
# -------------------------------
@st.cache_data(show_spinner=False)
def load_database(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

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
        f"Con base en la siguiente información extraída de investigaciones (con citas y referencias), responde a la pregunta:\n"
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
# Función para iniciar el modo de Ideación (Conversar con los datos)
# -------------------------------
def ideacion_mode(db, selected_files):
    st.subheader("Modo de Ideación: Conversa con los datos")
    user_input = st.text_input("Escribe tu consulta o idea:")
    if user_input:
        relevant_info = get_relevant_info(db, user_input, selected_files)
        prompt = (
            f"Utilizando la siguiente información extraída de investigaciones, conversa creativamente y genera ideas innovadoras o soluciones basadas en estos datos.\n\n"
            f"Consulta/Idea: {user_input}\n\n"
            f"Información:\n{relevant_info}\n\n"
            "Responde de forma abierta y creativa:"
        )
        respuesta = call_gemini_api(prompt)
        st.markdown("#### Respuesta:")
        st.markdown(respuesta)

# -------------------------------
# Autenticación simple para el uso de la aplicación
# -------------------------------
def login():
    st.sidebar.title("Autenticación")
    username = st.sidebar.text_input("Usuario")
    password = st.sidebar.text_input("Contraseña", type="password")
    if username == "admin" and password == "secret":
        st.sidebar.success("Acceso autorizado")
        return True
    else:
        st.sidebar.error("Credenciales incorrectas")
        return False

# -------------------------------
# Aplicación principal de Streamlit
# -------------------------------
def main():
    st.title("Informe e Ideación de Investigaciones para Empresarios")
    st.markdown("Esta aplicación genera informes formales e interactúa creativamente con datos de investigaciones para clientes empresariales.")

    if not login():
        st.stop()

    # Selección de cliente
    cliente = st.sidebar.selectbox("Seleccione el cliente", ["Mondelez", "Postobon"])

    # Cargar la base de datos (formato JSON)
    db_path = "resultado_presentacion.json"
    try:
        db = load_database(db_path)
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        st.stop()

    # Filtrar la base de datos por cliente
    filtered_db = [doc for doc in db if doc.get("cliente") == cliente]

    # Selección de productos o categorías (ej.: "gums_and_candys", "galletas", etc.)
    productos_disponibles = list({doc.get("producto") for doc in filtered_db})
    selected_productos = st.sidebar.multiselect("Seleccione los productos a incluir", productos_disponibles, default=productos_disponibles)

    # Filtrar documentos por productos seleccionados
    filtered_db = [doc for doc in filtered_db if doc.get("producto") in selected_productos]
    selected_files = [doc.get("nombre_archivo") for doc in filtered_db]

    # Selección del modo de operación
    modo = st.sidebar.radio("Seleccione el modo", ["Informe de Informes", "Ideación (Conversar con los datos)"])

    st.markdown(f"#### Documentos seleccionados ({len(selected_files)}):")
    st.write(selected_files)

    if modo == "Informe de Informes":
        st.markdown("### Ingrese la pregunta del empresario")
        question = st.text_area("Pregunta", height=150)
        if st.button("Generar Informe"):
            if not question.strip():
                st.warning("Ingrese una pregunta para generar el informe.")
            else:
                st.info("Generando informe. Esto puede tardar unos minutos...")
                report = generate_final_report(question, filtered_db, selected_files)
                if report is None:
                    st.error("No se pudo generar el informe. Intente de nuevo más tarde.")
                else:
                    st.markdown("### Informe Final")
                    st.markdown(report, unsafe_allow_html=True)
                    with open("informe_final.html", "w", encoding="utf-8") as f:
                        f.write(report)
                    st.success("Informe generado y guardado en 'informe_final.html'.")
    else:
        # Modo de Ideación
        ideacion_mode(filtered_db, selected_files)

if __name__ == "__main__":
    main()

