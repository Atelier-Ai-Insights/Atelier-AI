import streamlit as st
import docx
import io
import os  
import uuid
from datetime import datetime
import requests 
import re 
from services.gemini_api import call_gemini_api
# --- ¡IMPORTACIÓN MODIFICADA! ---
from services.supabase_db import log_query_event, supabase, get_daily_usage
from prompts import get_transcript_prompt, get_autocode_prompt, get_text_analysis_summary_prompt
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from utils import reset_transcript_chat_workflow

# =====================================================
# MODO: ANÁLISIS DE TEXTOS (VERSIÓN PROYECTOS)
# =====================================================

TEXT_PROJECT_BUCKET = "text_project_files"

# --- Funciones de Carga de Datos (Sin cambios) ---

@st.cache_data(ttl=600, show_spinner=False)
def load_text_project_data(storage_folder_path: str):
    """
    Descarga TODOS los archivos .docx de una carpeta en Supabase Storage
    y extrae su texto combinado.
    """
    if not storage_folder_path:
        st.error("Error: La ruta de la carpeta del proyecto está vacía.")
        return None
        
    combined_context = ""
    
    try:
        files_list = supabase.storage.from_(TEXT_PROJECT_BUCKET).list(storage_folder_path)
        
        if not files_list:
            st.warning("El proyecto no contiene archivos.")
            return "" 

        docx_files = [f for f in files_list if f['name'].endswith('.docx')]
        
        if not docx_files:
            st.warning("La carpeta del proyecto no contiene archivos .docx.")
            return ""

        st.write(f"Cargando {len(docx_files)} archivo(s) del proyecto...")

        for file_info in docx_files:
            file_name = file_info['name']
            full_file_path = f"{storage_folder_path}/{file_name}"
            
            try:
                response_file_bytes = supabase.storage.from_(TEXT_PROJECT_BUCKET).download(full_file_path)
                file_stream = io.BytesIO(response_file_bytes)
                document = docx.Document(file_stream)
                full_text = "\n".join([para.text for para in document.paragraphs if para.text.strip()])
                combined_context += f"\n\n--- INICIO DOCUMENTO: {file_name} ---\n\n{full_text}\n\n--- FIN DOCUMENTO: {file_name} ---\n"
            
            except Exception as e_file:
                st.error(f"Error al procesar el archivo '{file_name}': {e_file}")
                continue 
        
        return combined_context
        
    except Exception as e:
        st.error(f"Error al cargar los archivos del proyecto ({storage_folder_path}): {e}")
        return None

# --- ¡INICIO DE FUNCIÓN MODIFICADA! ---
def show_text_project_creator(user_id, plan_limit):
    st.subheader("Crear Nuevo Proyecto de Texto")
    
    try:
        response = supabase.table("text_projects").select("id", count='exact').eq("user_id", user_id).execute()
        project_count = response.count
    except Exception as e:
        st.error(f"Error al verificar el conteo de proyectos: {e}")
        return

    if project_count >= plan_limit and plan_limit != float('inf'):
        st.warning(f"Has alcanzado el límite de {int(plan_limit)} proyectos de texto para tu plan actual. Deberás eliminar un proyecto existente para crear uno nuevo.")
        return

    # --- ¡NUEVA LÍNEA! Leemos el límite de archivos por proyecto ---
    max_files_per_project = st.session_state.plan_features.get("text_analysis_max_files_per_project", 1)

    with st.form("new_text_project_form"):
        project_name = st.text_input("Nombre del Proyecto*", placeholder="Ej: Entrevistas NPS Q1 2024")
        project_brand = st.text_input("Marca*", placeholder="Ej: Marca X")
        project_year = st.number_input("Año*", min_value=2020, max_value=2030, value=datetime.now().year)
        
        # --- ¡MODIFICADO! ---
        uploaded_files = st.file_uploader(
            "Archivos Word (.docx)*",
            type=["docx"],
            accept_multiple_files=True,
            # --- ¡NUEVA LÍNEA! ---
            help=f"Tu plan te permite subir un máximo de {int(max_files_per_project) if max_files_per_project != float('inf') else 'ilimitados'} archivos por proyecto."
        )
        
        # --- ¡MODIFICADO! ---
        if max_files_per_project == float('inf'):
            st.caption(f"Puedes cargar uno o varios archivos .docx. (Límite: Ilimitado)")
        else:
            st.caption(f"Puedes cargar uno o varios archivos .docx. (Límite de tu plan: {int(max_files_per_project)} archivos)")

        
        submitted = st.form_submit_button("Crear Proyecto")

    if submitted:
        if not all([project_name, project_brand, project_year, uploaded_files]):
            st.warning("Por favor, completa todos los campos obligatorios (*).")
            return

        # --- ¡INICIO DEL NUEVO BLOQUE DE VALIDACIÓN! ---
        if len(uploaded_files) > max_files_per_project and max_files_per_project != float('inf'):
            st.error(f"Has intentado subir {len(uploaded_files)} archivos. Tu plan te permite un máximo de {int(max_files_per_project)} archivos por proyecto.")
            return
        # --- ¡FIN DEL NUEVO BLOQUE DE VALIDACIÓN! ---

        project_storage_folder = f"{user_id}/{uuid.uuid4()}" 
        
        spinner_text = f"Creando proyecto y subiendo {len(uploaded_files)} archivo(s)..."
        with st.spinner(spinner_text):
            try:
                uploaded_file_paths = [] 
                
                for uploaded_file in uploaded_files: 
                    base_name = uploaded_file.name.replace(' ', '_')
                    safe_name = re.sub(r'[^\w._-]', '', base_name)
                    file_ext = os.path.splitext(safe_name)[1]
                    
                    if not safe_name or safe_name.startswith('.'):
                        safe_name = f"archivo_{uuid.uuid4()}{file_ext if file_ext else '.docx'}"

                    storage_file_path = f"{project_storage_folder}/{safe_name}"
                    uploaded_file_paths.append(storage_file_path) 

                    file_bytes = uploaded_file.getvalue()
                    supabase.storage.from_(TEXT_PROJECT_BUCKET).upload(
                        path=storage_file_path,
                        file=file_bytes,
                        file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
                    )

                project_data = {
                    "project_name": project_name,
                    "project_brand": project_brand,
                    "project_year": int(project_year),
                    "storage_path": project_storage_folder, 
                    "user_id": user_id
                }
                
                supabase.table("text_projects").insert(project_data).execute()
                
                st.success(f"¡Proyecto '{project_name}' creado exitosamente!")
                st.rerun()

            except Exception as e:
                st.error(f"Error al crear el proyecto: {e}")
                try:
                    if uploaded_file_paths: 
                        supabase.storage.from_(TEXT_PROJECT_BUCKET).remove(uploaded_file_paths)
                except:
                    pass 
# --- ¡FIN DE FUNCIÓN MODIFICADA! ---

def show_text_project_list(user_id):
    st.subheader("Mis Proyectos de Texto")
    
    try:
        response = supabase.table("text_projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        projects = response.data
    except Exception as e:
        st.error(f"Error al cargar la lista de proyectos: {e}")
        return

    if not projects:
        st.info("Aún no has creado ningún proyecto de texto. Usa el formulario de arriba para empezar.")
        return

    for proj in projects:
        proj_id = proj['id']
        proj_name = proj['project_name']
        proj_brand = proj.get('project_brand', 'N/A')
        proj_year = proj.get('project_year', 'N/A')
        storage_path = proj['storage_path'] 
        
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown(f"**{proj_name}**")
                st.caption(f"Marca: {proj_brand} | Año: {proj_year}")
            
            with col2:
                if st.button("Analizar", key=f"analizar_txt_{proj_id}", use_container_width=True, type="primary"):
                    st.session_state.mode_state["ta_selected_project_id"] = proj_id
                    st.session_state.mode_state["ta_selected_project_name"] = proj_name
                    st.session_state.mode_state["ta_storage_path"] = storage_path
                    st.rerun()
            
            with col3:
                if st.button("Eliminar", key=f"eliminar_txt_{proj_id}", use_container_width=True):
                    with st.spinner("Eliminando proyecto y sus archivos..."):
                        try:
                            if storage_path:
                                files_in_project = supabase.storage.from_(TEXT_PROJECT_BUCKET).list(storage_path)
                                if files_in_project:
                                    paths_to_remove = [f"{storage_path}/{f['name']}" for f in files_in_project]
                                    supabase.storage.from_(TEXT_PROJECT_BUCKET).remove(paths_to_remove)
                            
                            supabase.table("text_projects").delete().eq("id", proj_id).execute()
                            
                            st.success(f"Proyecto '{proj_name}' eliminado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar: {e}")

# --- ¡INICIO DE FUNCIÓN MODIFICADA! ---
def show_text_project_analyzer(summary_context, project_name):
    """
    Muestra la UI de análisis (Chat y Autocode) para el proyecto cargado.
    """
    
    st.markdown(f"### Analizando: **{project_name}**")
    
    if st.button("← Volver a la lista de proyectos"):
        st.session_state.mode_state = {}
        st.rerun()
        
    st.divider()

    tab_chat, tab_autocode = st.tabs(["Análisis de Notas y Transcripciones", "Auto-Codificación"])

    with tab_chat:
        st.header("Análisis de Notas y Transcripciones")
        st.markdown("Haz preguntas específicas sobre el **resumen de hallazgos** del proyecto.")
        
        if "transcript_chat_history" not in st.session_state.mode_state: 
            st.session_state.mode_state["transcript_chat_history"] = []

        for msg in st.session_state.mode_state["transcript_chat_history"]:
            with st.chat_message(msg["role"], avatar="✨" if msg['role'] == "assistant" else "👤"):
                st.markdown(msg["content"])

        user_prompt = st.chat_input("Haz una pregunta sobre las transcripciones...")

        if user_prompt:
            st.session_state.mode_state["transcript_chat_history"].append({"role": "user", "content": user_prompt})
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_prompt)

            # --- ¡INICIO DEL NUEVO BLOQUE DE LÍMITES! ---
            question_limit = st.session_state.plan_features.get('text_analysis_questions_per_day', 5)
            # Usamos c.MODE_TEXT_ANALYSIS como el "modo" para registrar la consulta
            current_queries = get_daily_usage(st.session_state.user, c.MODE_TEXT_ANALYSIS) 

            if current_queries >= question_limit and question_limit != float('inf'):
                st.error(f"Has alcanzado tu límite de {int(question_limit)} preguntas diarias para el Análisis de Texto.")
                st.session_state.mode_state["transcript_chat_history"].pop() # Eliminar la pregunta del historial
                return # Detener la ejecución
            # --- ¡FIN DEL NUEVO BLOQUE DE LÍMITES! ---

            with st.chat_message("assistant", avatar="✨"):
                message_placeholder = st.empty(); message_placeholder.markdown("Analizando...")
                
                chat_prompt = get_transcript_prompt(summary_context, user_prompt)
                response = call_gemini_api(chat_prompt) 

                if response:
                    message_placeholder.markdown(response)
                    # --- ¡MODIFICADO! ---
                    # Registramos la consulta (usando el modo principal para la analítica)
                    log_query_event(user_prompt, mode=c.MODE_TEXT_ANALYSIS)
                    st.session_state.mode_state["transcript_chat_history"].append({
                        "role": "assistant", 
                        "content": response
                    })
                    st.rerun()
                else:
                    message_placeholder.error("Error al obtener respuesta."); 
                    st.session_state.mode_state["transcript_chat_history"].pop()

        if st.session_state.mode_state["transcript_chat_history"]:
            st.divider() 
            col1, col2 = st.columns([1,1])
            with col1:
                chat_content_raw = "\n\n".join(f"**{m['role']}:** {m['content']}" for m in st.session_state.mode_state["transcript_chat_history"])
                chat_content_for_pdf = chat_content_raw.replace("](#)", "]")
                pdf_bytes = generate_pdf_html(chat_content_for_pdf, title=f"Chat Análisis de Texto - {project_name}", banner_path=banner_file)
                
                if pdf_bytes: 
                    st.download_button(
                        "Descargar Chat PDF", 
                        data=pdf_bytes, 
                        file_name=f"chat_analisis_texto_{project_name.lower().replace(' ','_')}.pdf", 
                        mime="application/pdf", 
                        use_container_width=True
                    )
            with col2: 
                st.button(
                    "Nueva Conversación", 
                    on_click=reset_transcript_chat_workflow, 
                    key="new_transcript_chat_btn", 
                    use_container_width=True
                )

    with tab_autocode:
        st.header("Auto-Codificación")
        
        if "autocode_result" in st.session_state.mode_state:
            st.markdown("### Reporte de Temas Generado")
            st.markdown(st.session_state.mode_state["autocode_result"])
            
            col1, col2 = st.columns(2)
            with col1:
                pdf_bytes = generate_pdf_html(st.session_state.mode_state["autocode_result"], title="Reporte de Auto-Codificación", banner_path=banner_file)
                if pdf_bytes: 
                    st.download_button(
                        "Descargar Reporte PDF", 
                        data=pdf_bytes, 
                        file_name="reporte_temas.pdf", 
                        mime="application/pdf", 
                        use_container_width=True
                    )
            with col2:
                if st.button("Generar nuevo reporte", use_container_width=True, type="secondary"):
                    st.session_state.mode_state.pop("autocode_result", None)
                    st.rerun()
        
        else:
            st.markdown("Esta herramienta leerá el **resumen de hallazgos** y generará un reporte de temas clave y citas de respaldo.")
            main_topic = st.text_input(
                "¿Cuál es el tema principal de estas entrevistas?", 
                placeholder="Ej: Percepción de snacks saludables, Experiencia de compra, etc.",
                key="autocode_topic"
            )

            if st.button("Analizar Temas", use_container_width=True, type="primary"):
                if not main_topic.strip():
                    st.warning("Por favor, describe el tema principal.")
                else:
                    with st.spinner("Analizando temas emergentes..."):
                        
                        prompt = get_autocode_prompt(summary_context, main_topic)
                        response = call_gemini_api(prompt)

                        if response:
                            st.session_state.mode_state["autocode_result"] = response
                            # Nota: No contamos esto como una "pregunta" de chat
                            log_query_event(f"Auto-codificación: {main_topic}", mode=f"{c.MODE_TEXT_ANALYSIS} (Autocode)")
                            st.rerun()
                        else:
                            st.error("Error al generar el análisis de temas.")
# --- ¡FIN DE FUNCIÓN MODIFICADA! ---


def text_analysis_mode():
    st.subheader(c.MODE_TEXT_ANALYSIS)
    st.markdown("Carga, gestiona y analiza tus proyectos de transcripciones (.docx).")
    st.divider()

    user_id = st.session_state.user_id
    # --- ¡MODIFICADO! Leemos el límite de PROYECTOS ---
    plan_limit = st.session_state.plan_features.get('transcript_file_limit', 0)

    # --- LÓGICA DE CARGA Y RESUMEN (Todo con mode_state) ---
    
    # 1. Cargar el CONTEXTO COMPLETO
    if "ta_selected_project_id" in st.session_state.mode_state and "ta_combined_context" not in st.session_state.mode_state:
        with st.spinner("Cargando datos del proyecto de texto..."):
            context = load_text_project_data(st.session_state.mode_state["ta_storage_path"]) 
            if context is not None:
                st.session_state.mode_state["ta_combined_context"] = context
            else:
                st.error("No se pudieron cargar los datos del proyecto.")
                st.session_state.mode_state.pop("ta_selected_project_id", None)
                st.session_state.mode_state.pop("ta_selected_project_name", None)
                st.session_state.mode_state.pop("ta_storage_path", None)

    # 2. Generar el RESUMEN
    if "ta_combined_context" in st.session_state.mode_state and "ta_summary_context" not in st.session_state.mode_state:
        with st.spinner("Generando resumen de IA por única vez... (Esto puede tardar un minuto)"):
            
            full_ctx = st.session_state.mode_state["ta_combined_context"]
            
            MAX_SUMMARY_INPUT = 1_000_000
            if len(full_ctx) > MAX_SUMMARY_INPUT:
                 full_ctx = full_ctx[:MAX_SUMMARY_INPUT] + "\n\n...(contexto truncado para resumen)..."
                 st.warning(f"El contexto es muy grande (>{MAX_SUMMARY_INPUT} caracteres) y ha sido truncado para generar el resumen inicial.", icon="⚠️")
                 
            summary_prompt = get_text_analysis_summary_prompt(full_ctx)
            
            large_output_config = {
                "max_output_tokens": 16384 
            }
            summary = call_gemini_api(
                summary_prompt, 
                generation_config_override=large_output_config
            )
            
            if summary:
                st.session_state.mode_state["ta_summary_context"] = summary
                st.rerun() 
            else:
                st.error("No se pudo generar el resumen inicial de IA. No se puede continuar.")
                st.session_state.mode_state.pop("ta_selected_project_id", None)
                st.session_state.mode_state.pop("ta_selected_project_name", None)
                st.session_state.mode_state.pop("ta_storage_path", None)
                st.session_state.mode_state.pop("ta_combined_context", None)
                st.rerun()

    # --- LÓGICA DE VISTA (QUÉ MOSTRAR AL USUARIO) ---

    # 3. VISTA DE ANÁLISIS
    if "ta_summary_context" in st.session_state.mode_state:
        show_text_project_analyzer( 
            st.session_state.mode_state["ta_summary_context"],
            st.session_state.mode_state["ta_selected_project_name"]
        )
    
    # 4. VISTA DE CARGA
    elif "ta_selected_project_id" in st.session_state.mode_state:
        st.info("Preparando análisis... (Generando resumen de IA)")
        st.spinner("Cargando y resumiendo proyecto...") 
    
    # 5. VISTA DE GESTIÓN (PÁGINA PRINCIPAL)
    else:
        with st.expander("➕ Crear Nuevo Proyecto de Texto", expanded=True):
            # --- ¡MODIFICADO! Pasamos el límite de proyectos ---
            show_text_project_creator(user_id, plan_limit)
        
        st.divider()
        
        show_text_project_list(user_id)
