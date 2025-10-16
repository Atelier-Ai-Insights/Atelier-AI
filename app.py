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
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
except Exception as e:
    st.sidebar.warning(f"Advertencia: No se encontró la fuente DejaVuSans.ttf. {e}")

# ==============================
# DEFINICIÓN DE PLANES Y PERMISOS
# ==============================
PLAN_FEATURES = {
    "Explorer": {
        "reports_per_month": 2,
        "chat_queries_per_day": 4,
        "projects_per_year": 2,
        "has_creative_conversation": False,
        "has_concept_generation": False,
        "has_idea_evaluation": False,
    },
    "Strategist": {
        "reports_per_month": 25,
        "chat_queries_per_day": float('inf'),
        "projects_per_year": 10,
        "has_creative_conversation": True,
        "has_concept_generation": True,
        "has_idea_evaluation": False,
    },
    "Enterprise": {
        "reports_per_month": float('inf'),
        "chat_queries_per_day": float('inf'),
        "projects_per_year": float('inf'),
        "has_creative_conversation": True,
        "has_concept_generation": True,
        "has_idea_evaluation": True,
    }
}

# ==============================
# Autenticación Personalizada
# ==============================
def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.header("Iniciar Sesión")
        username = st.text_input("Usuario", placeholder="Apple")
        password = st.text_input("Contraseña", type="password", placeholder="****")

        if st.button("Ingresar"):
            response = supabase.table("users").select("*").eq("username", username).eq("password", password).execute()

            if response.data:
                user_data = response.data[0]
                st.session_state.logged_in = True
                st.session_state.user = user_data['username']
                st.session_state.cliente = user_data['username'].lower()
                user_plan = user_data.get('plan', 'Explorer')
                st.session_state.plan = user_plan
                st.session_state.plan_features = PLAN_FEATURES.get(user_plan, PLAN_FEATURES['Explorer'])
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

def logout():
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()

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
        return html.unescape(response.text)
    except Exception as e:
        st.error(f"Error en la llamada a Gemini: {e}. Intentando cambiar API Key.")
        switch_api_key()
        try:
            response = model.generate_content([prompt])
            return html.unescape(response.text)
        except Exception as e2:
            st.error(f"Error GRAVE en la llamada a Gemini: {e2}")
            return None

# ==============================
# CONEXIÓN A SUPABASE Y RASTREO
# ==============================
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def log_query_event(query_text, mode, rating=None):
    data = {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "user_name": st.session_state.user,
        "timestamp": datetime.datetime.now().isoformat(),
        "mode": mode, "query": query_text, "rating": rating,
    }
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
# FUNCIONES AUXILIARES
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

# =====================================================
# CLASE PDF Y GENERACIÓN DE REPORTES
# =====================================================
banner_file = "Banner (2).jpg"

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

def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)
    prompt1 = f"Pregunta del Cliente: ***{question}***\n\nInstrucciones:\n1. Identifica en la pregunta la marca exacta...\nInformación de Contexto:\n{relevant_info}\n\nRespuesta (Hallazgos Clave y Referencias):..."
    result1 = call_gemini_api(prompt1)
    if result1 is None: return None
    prompt2 = f"Pregunta del Cliente: ***{question}***\n\nInstrucciones Generales:\n1. Identifica en la pregunta la marca...\nResumen de Hallazgos Clave y Referencias:\n{result1}\n\nInformación de Contexto Adicional:\n{relevant_info}\n\nPor favor, redacta el informe completo..."
    result2 = call_gemini_api(prompt2)
    if result2 is None: return None
    return f"{question}\n\n" + result2

class PDFReport:
    # ... (El código de la clase PDFReport va aquí, sin cambios)
    pass

def generate_pdf_html(content, title="Documento Final", banner_path=None, output_filename=None):
    # ... (El código de la función generate_pdf_html va aquí, sin cambios)
    pass

# =====================================================
# MODOS DE LA APLICACIÓN
# =====================================================

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
                st.error("No se pudo generar el informe.")
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
    st.subheader("Chat de Consulta Directa")
    st.markdown("Realiza preguntas específicas y obtén respuestas concretas basadas únicamente en los hallazgos de los informes seleccionados.")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    for msg in st.session_state.chat_history: st.markdown(f"**{msg['role'].capitalize()}:** {msg['message']}")
    user_input = st.text_area("Escribe tu pregunta...", height=150)
    if st.button("Enviar Pregunta"):
        query_limit = st.session_state.plan_features['chat_queries_per_day']
        current_queries = get_daily_usage(st.session_state.user, "Chat de Consulta Directa")
        if current_queries >= query_limit:
            st.error(f"Has alcanzado tu límite de {int(query_limit)} consultas diarias.")
            st.warning("🚀 ¡Actualiza tu plan para tener consultas ilimitadas!")
            return
        if not user_input.strip():
            st.warning("Por favor, ingresa una pregunta para continuar.")
        else:
            st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
            relevant_info = get_relevant_info(db, user_input, selected_files)
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history)
            grounded_prompt = f"**Tarea:** Eres un **asistente de Inteligencia Artificial**...\n**Historial de la Conversación:**\n{conversation_history}\n**Información documentada en los reportes:**\n{relevant_info}\n**Instrucciones Estrictas:**..."
            with st.spinner("Buscando en los reportes..."):
                response = call_gemini_api(grounded_prompt)
            if response:
                st.session_state.chat_history.append({"role": "Asistente", "message": response})
                log_query_event(user_input, mode="Chat de Consulta Directa")
                st.rerun()
            else:
                st.error("Error al generar la respuesta.")
    if st.session_state.chat_history:
        pdf_bytes = generate_pdf_html("\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial de Consulta Directa", banner_path=banner_file)
        if pdf_bytes: st.download_button("Descargar Chat en PDF", data=pdf_bytes, file_name="chat_consulta.pdf", mime="application/pdf")
        st.button("Nueva Conversación", on_click=reset_chat_workflow, key="new_grounded_chat_btn")

def ideacion_mode(db, selected_files):
    st.subheader("Conversaciones Creativas")
    st.markdown("Este es un espacio para explorar ideas novedosas. Basado en los hallazgos, el asistente te ayudará a generar conceptos creativos.")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    for msg in st.session_state.chat_history: st.markdown(f"**{msg['role'].capitalize()}:** {msg['message']}")
    user_input = st.text_area("Lanza una idea o pregunta para iniciar la conversación...", height=150)
    if st.button("Enviar"):
        if not user_input.strip():
            st.warning("Por favor, ingresa tu pregunta para continuar.")
        else:
            st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
            relevant = get_relevant_info(db, user_input, selected_files)
            conv_prompt = f"Historial de conversación:\n" + "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history) + f"\n\nInformación de contexto:\n{relevant}\n\nInstrucciones:\n- Responde de forma creativa..."
            with st.spinner("Generando respuesta creativa..."):
                resp = call_gemini_api(conv_prompt)
            if resp:
                st.session_state.chat_history.append({"role": "Asistente", "message": resp})
                log_query_event(user_input, mode="Conversaciones creativas")
                st.rerun()
            else:
                st.error("Error al generar la respuesta.")
    if st.session_state.chat_history:
        pdf_bytes = generate_pdf_html("\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial de Chat Creativo", banner_path=banner_file)
        if pdf_bytes: st.download_button("Descargar Chat en PDF", data=pdf_bytes, file_name="chat_creativo.pdf", mime="application/pdf")
        st.button("Nueva conversación", on_click=reset_chat_workflow, key="new_chat_btn")

def concept_generation_mode(db, selected_files):
    st.subheader("Generación de Conceptos")
    st.markdown("A partir de una idea inicial y los hallazgos, generaremos un concepto de producto o servicio.")
    product_idea = st.text_area("Describe tu idea de producto o servicio:", height=150, placeholder="Ej: Un snack saludable para niños...")
    if st.button("Generar Concepto"):
        if not product_idea.strip():
            st.warning("Por favor, describe tu idea para continuar.")
        else:
            with st.spinner("Analizando hallazgos y generando el concepto..."):
                context_info = get_relevant_info(db, product_idea, selected_files)
                prompt = f"**Tarea:** Eres un estratega de innovación...\n**Idea de Producto del Usuario:**\n\"{product_idea}\"\n**Contexto:**\n\"{context_info}\"\n**Instrucciones:**..."
                response = call_gemini_api(prompt)
                if response:
                    st.session_state.generated_concept = response
                    log_query_event(product_idea, mode="Generación de conceptos")
                else:
                    st.error("No se pudo generar el concepto.")
    if "generated_concept" in st.session_state:
        st.markdown("---")
        st.markdown("### Concepto Generado")
        st.markdown(st.session_state.generated_concept)
        if st.button("Generar un nuevo concepto"):
            st.session_state.pop("generated_concept")
            st.rerun()

def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluación de Pre-Ideas")
    st.markdown("Presenta una idea y el asistente la evaluará contra los hallazgos, indicando su potencial.")
    if "evaluation_result" in st.session_state:
        st.markdown("---")
        st.markdown("### Evaluación de la Idea")
        st.markdown(st.session_state.evaluation_result)
        if st.button("Evaluar otra idea"):
            del st.session_state["evaluation_result"]
            st.rerun()
    else:
        idea_input = st.text_area("Describe la idea que quieres evaluar:", height=150, placeholder="Ej: Una línea de yogures con probióticos...")
        if st.button("Evaluar Idea"):
            if not idea_input.strip():
                st.warning("Por favor, describe una idea para continuar.")
            else:
                with st.spinner("Evaluando el potencial de la idea..."):
                    context_info = get_relevant_info(db, idea_input, selected_files)
                    prompt = f"**Tarea:** Eres un estratega de mercado...\n**Idea a Evaluar:**\n\"{idea_input}\"\n**Contexto:**\n\"{context_info}\"\n**Instrucciones:**..."
                    response = call_gemini_api(prompt)
                    if response:
                        st.session_state.evaluation_result = response
                        log_query_event(idea_input, mode="Evaluación de Idea")
                        st.rerun()
                    else:
                        st.error("No se pudo generar la evaluación.")

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
    
    modos_disponibles = ["Generar un reporte de reportes", "Chat de Consulta Directa"]
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
