import streamlit as st
import docx
import io
import os
import uuid
from datetime import datetime
import requests # <-- ¡Necesario para descargar el archivo!
import re # <-- ¡Importación que usaremos para la corrección!
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event, supabase
from prompts import get_transcript_prompt, get_autocode_prompt
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: ANÁLISIS DE TEXTOS (VERSIÓN PROYECTOS)
# =====================================================

TEXT_PROJECT_BUCKET = "text_project_files"

# --- Funciones de Carga de Datos ---

@st.cache_data(ttl=600)
def load_text_project_data(storage_path_folder):
    """
    Descarga TODOS los archivos .docx de una carpeta de proyecto
    de Supabase Storage y extrae su texto.
    """
    try:
        # 1. Listar los archivos en la carpeta del proyecto
        files_list = supabase.storage.from_(TEXT_PROJECT_BUCKET).list(path=storage_path_folder)
        
        if not files_list:
            st.error("Error: Este proyecto no contiene archivos.")
            return None
        
        combined_context = ""
        
        # 2. Bucle para descargar y procesar CADA archivo
        st.write(f"Cargando {len(files_list)} archivo(s) del proyecto...")
        progress_bar = st.progress(0.0)
        
        for i, file_info in enumerate(files_list):
            file_name = file_info.get('name')
            # Ignorar archivos del sistema como .DS_Store
            if not file_name or not file_name.endswith(('.docx', '.DOCX')):
                continue
                
            file_path = f"{storage_path_folder}/{file_name}"
            
            try:
                # 2a. Obtener URL firmada para este archivo
                response_url = supabase.storage.from_(TEXT_PROJECT_BUCKET).create_signed_url(file_path, 60)
                signed_url = response_url['signedURL']
                
                # 2b. Descargar el archivo
                response_file = requests.get(signed_url)
                response_file.raise_for_status()
                
                # 2c. Leer el .docx
                file_stream = io.BytesIO(response_file.content)
                document = docx.Document(file_stream)
                full_text = "\n".join([para.text for para in document.paragraphs if para.text.strip()])
                
                # 2d. Añadir al contexto combinado
                combined_context += f"\n\n--- INICIO DOCUMENTO: {file_name} ---\n\n{full_text}\n\n--- FIN DOCUMENTO: {file_name} ---\n"
                
                progress_bar.progress((i + 1) / len(files_list))

            except Exception as e:
                st.warning(f"No se pudo cargar el archivo '{file_name}': {e}")
                continue
        
        progress_bar.empty()
        return combined_context
        
    except Exception as e:
        st.error(f"Error al cargar el proyecto de texto: {e}")
        return None

# --- Funciones de UI ---

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

    with st.form("new_text_project_form"):
        project_name = st.text_input("Nombre del Proyecto*", placeholder="Ej: Entrevistas NPS Q1 2024")
        project_brand = st.text_input("Marca", placeholder="Ej: Marca X")
        project_year = st.number_input("Año", min_value=2020, max_value=2030, value=datetime.now().year)
        
        uploaded_files = st.file_uploader(
            "Archivos Word (.docx)*", 
            type=["docx"],
            accept_multiple_files=True
        )
        
        submitted = st.form_submit_button("Crear Proyecto")

    if submitted:
        if not all([project_name, uploaded_files]):
            st.warning("Por favor, completa el Nombre del Proyecto y sube al menos un archivo .docx.")
            return

        storage_path_folder = f"{user_id}/{uuid.uuid4()}" # Esta es la CARPETA del proyecto
        
        with st.spinner(f"Creando proyecto y subiendo {len(uploaded_files)} archivo(s)..."):
            try:
                # Bucle para subir cada archivo a la carpeta
                for file in uploaded_files:
                    file_bytes = file.getvalue()
                    
                    # --- ¡INICIO DEL AJUSTE (SANITIZACIÓN)! ---
                    # 1. Reemplazar espacios con guiones bajos
                    base_name = file.name.replace(' ', '_')
                    # 2. Eliminar cualquier carácter que no sea letra, número, punto, guion bajo o guion
                    safe_name = re.sub(r'[^\w._-]', '', base_name)
                    # 3. Si el nombre queda vacío (ej. "().docx"), usar un genérico
                    if not safe_name or safe_name.startswith('.'):
                        safe_name = f"archivo_{uuid.uuid4()}{os.path.splitext(file.name)[1]}"
                    
                    file_name = safe_name
                    # --- ¡FIN DEL AJUSTE (SANITIZACIÓN)! ---
                    
                    full_storage_path = f"{storage_path_folder}/{file_name}" # Ruta al archivo individual
                    
                    supabase.storage.from_(TEXT_PROJECT_BUCKET).upload(
                        path=full_storage_path,
                        file=file_bytes,
                        file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
                    )

                project_data = {
                    "project_name": project_name,
                    "project_brand": project_brand if project_brand else None,
                    "project_year": int(project_year) if project_year else None,
                    "storage_path": storage_path_folder 
                }
                
                supabase.table("text_projects").insert(project_data).execute()
                
                st.success(f"¡Proyecto '{project_name}' creado exitosamente!")
                st.rerun()

            except Exception as e:
                st.error(f"Error al crear el proyecto: {e}")
                # Lógica de limpieza: eliminar archivos subidos si falla
                try:
                    files_in_folder = supabase.storage.from_(TEXT_PROJECT_BUCKET).list(path=storage_path_folder)
                    file_paths_to_remove = [f"{storage_path_folder}/{file['name']}" for file in files_in_folder]
                    if file_paths_to_remove:
                        supabase.storage.from_(TEXT_PROJECT_BUCKET).remove(file_paths_to_remove)
                except:
                    pass 

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
                    st.session_state.ta_selected_project_id = proj_id
                    st.session_state.ta_selected_project_name = proj_name
                    st.session_state.ta_storage_path = storage_path
                    st.rerun()
            
            with col3:
                if st.button("Eliminar", key=f"eliminar_txt_{proj_id}", use_container_width=True):
                    with st.spinner("Eliminando proyecto..."):
                        try:
                            # Lógica para eliminar todos los archivos de la carpeta
                            files_in_folder = supabase.storage.from_(TEXT_PROJECT_BUCKET).list(path=storage_path)
                            file_paths_to_remove = [f"{storage_path}/{file['name']}" for file in files_in_folder]
                            if file_paths_to_remove:
                                supabase.storage.from_(TEXT_PROJECT_BUCKET).remove(file_paths_to_remove)
                            
                            supabase.table("text_projects").delete().eq("id", proj_id).execute()
                            
                            st.success(f"Proyecto '{proj_name}' eliminado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar: {e}")

def show_text_project_analyzer(combined_context, project_name):
    """
    Muestra la UI de análisis (Chat y Autocode) para el proyecto cargado.
    """
    
    st.markdown(f"### Analizando: **{project_name}**")
    
    if st.button("← Volver a la lista de proyectos"):
        st.session_state.pop("ta_selected_project_id", None)
        st.session_state.pop("ta_selected_project_name", None)
        st.session_state.pop("ta_storage_path", None)
        st.session_state.pop("ta_combined_context", None)
        st.session_state.pop("transcript_chat_history", None)
        st.session_state.pop("autocode_result", None)
        st.rerun()
        
    st.divider()

    tab_chat, tab_autocode = st.tabs(["Análisis de Notas y Transcripciones", "Auto-Codificación"])

    with tab_chat:
        st.header("Análisis de Notas y Transcripciones")
        st.markdown("Haz preguntas específicas sobre el contenido de los archivos cargados.")
        
        if "transcript_chat_history" not in st.session_state: 
            st.session_state.transcript_chat_history = []

        for msg in st.session_state.transcript_chat_history:
            with st.chat_message(msg["role"], avatar="✨" if msg['role'] == "assistant" else "👤"):
                st.markdown(msg["content"])

        user_prompt = st.chat_input("Haz una pregunta sobre las transcripciones...")

        if user_prompt:
            st.session_state.transcript_chat_history.append({"role": "user", "content": user_prompt})
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_prompt)

            with st.chat_message("assistant", avatar="✨"):
                message_placeholder = st.empty(); message_placeholder.markdown("Analizando...")
                
                MAX_CONTEXT_LENGTH = 800000 
                if len(combined_context) > MAX_CONTEXT_LENGTH:
                    combined_context = combined_context[:MAX_CONTEXT_LENGTH] + "\n\n...(contexto truncado)..."
                    st.warning("Contexto truncado.", icon="⚠️")
                    
                chat_prompt = get_transcript_prompt(combined_context, user_prompt)
                response = call_gemini_api(chat_prompt) 

                if response:
                    message_placeholder.markdown(response)
                    log_query_event(user_prompt, mode=f"{c.MODE_TEXT_ANALYSIS} (Chat)")
                    st.session_state.transcript_chat_history.append({
                        "role": "assistant", 
                        "content": response
                    })
                    st.rerun()
                else:
                    message_placeholder.error("Error al obtener respuesta."); st.session_state.transcript_chat_history.pop()

    with tab_autocode:
        st.header("Auto-Codificación")
        
        if "autocode_result" in st.session_state:
            st.markdown("### Reporte de Temas Generado")
            st.markdown(st.session_state.autocode_result)
            
            col1, col2 = st.columns(2)
            with col1:
                pdf_bytes = generate_pdf_html(st.session_state.autocode_result, title="Reporte de Auto-Codificación", banner_path=banner_file)
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
                    st.session_state.pop("autocode_result", None)
                    st.rerun()
        
        else:
            st.markdown("Esta herramienta leerá todos los archivos cargados y generará un reporte de temas clave y citas de respaldo.")
            main_topic = st.text_input(
                "¿Cuál es el tema principal de estas entrevistas?", 
                placeholder="Ej: Percepción de snacks saludables, Experiencia de compra, etc.",
                key="autocode_topic"
            )

            if st.button("Analizar Temas", use_container_width=True, type="primary"):
                if not main_topic.strip():
                    st.warning("Por favor, describe el tema principal.")
                else:
                    with st.spinner("Analizando temas emergentes... (Esto puede tardar unos minutos)"):
                        
                        MAX_CONTEXT_LENGTH = 1_000_000 
                        if len(combined_context) > MAX_CONTEXT_LENGTH:
                            combined_context = combined_context[:MAX_CONTEXT_LENGTH] + "\n\n...(contexto truncado)..."
                            st.warning("El contexto de las transcripciones es muy largo y ha sido truncado.", icon="⚠️")
                        
                        prompt = get_autocode_prompt(combined_context, main_topic)
                        response = call_gemini_api(prompt)

                        if response:
                            st.session_state.autocode_result = response
                            log_query_event(f"Auto-codificación: {main_topic}", mode=f"{c.MODE_TEXT_ANALYSIS} (Autocode)")
                            st.rerun()
                        else:
                            st.error("Error al generar el análisis de temas.")

# --- FUNCIÓN PRINCIPAL DEL MODO (NUEVA ARQUITECTURA) ---

def text_analysis_mode():
    st.subheader(c.MODE_TEXT_ANALYSIS)
    st.markdown("Carga, gestiona y analiza tus proyectos de transcripciones (.docx).")
    st.divider()

    user_id = st.session_state.user_id
    plan_limit = st.session_state.plan_features.get('transcript_file_limit', 0)

    # --- VISTA DE ANÁLISIS ---
    if "ta_selected_project_id" in st.session_state and "ta_combined_context" not in st.session_state:
        with st.spinner("Cargando datos del proyecto de texto..."):
            context = load_text_project_data(st.session_state.ta_storage_path)
            if context is not None:
                st.session_state.ta_combined_context = context
            else:
                st.error("No se pudieron cargar los datos del proyecto.")
                st.session_state.pop("ta_selected_project_id")
                st.session_state.pop("ta_selected_project_name")
                st.session_state.pop("ta_storage_path")

    if "ta_combined_context" in st.session_state:
        show_text_project_analyzer(
            st.session_state.ta_combined_context,
            st.session_state.ta_selected_project_name
        )
    
    # --- VISTA DE GESTIÓN (PÁGINA PRINCIPAL) ---
    else:
        with st.expander("➕ Crear Nuevo Proyecto de Texto", expanded=True):
            show_text_project_creator(user_id, plan_limit)
        
        st.divider()
        
        show_text_project_list(user_id)
        