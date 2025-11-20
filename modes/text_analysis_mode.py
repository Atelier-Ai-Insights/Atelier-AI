import streamlit as st
import docx
import io
import os  
import uuid
from datetime import datetime
import requests 
import re 
# --- IMPORTACIÓN DE STREAM ---
from services.gemini_api import call_gemini_api, call_gemini_stream 
from services.supabase_db import log_query_event, supabase, get_daily_usage
from prompts import get_transcript_prompt, get_autocode_prompt, get_text_analysis_summary_prompt
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from utils import reset_transcript_chat_workflow, build_rag_context

# =====================================================
# MODO: ANÁLISIS DE TEXTOS (OPTIMIZADO CON RAG)
# =====================================================

TEXT_PROJECT_BUCKET = "text_project_files"

# --- Funciones de Carga de Datos (MODIFICADA) ---

@st.cache_data(ttl=600, show_spinner=False)
def load_text_project_data(storage_folder_path: str):
    """
    Descarga los archivos y los devuelve como una LISTA DE DOCUMENTOS
    estructurada para permitir RAG (Búsqueda fragmentada).
    """
    if not storage_folder_path:
        st.error("Error: La ruta de la carpeta del proyecto está vacía.")
        return []
        
    documents_list = [] # Lista de dicts: {'source': nombre, 'content': texto}
    
    try:
        files_list = supabase.storage.from_(TEXT_PROJECT_BUCKET).list(storage_folder_path)
        
        if not files_list:
            st.warning("El proyecto no contiene archivos.")
            return []

        docx_files = [f for f in files_list if f['name'].endswith('.docx')]
        
        if not docx_files:
            st.warning("La carpeta del proyecto no contiene archivos .docx.")
            return []

        st.write(f"Cargando {len(docx_files)} archivo(s) del proyecto...")

        for file_info in docx_files:
            file_name = file_info['name']
            full_file_path = f"{storage_folder_path}/{file_name}"
            
            try:
                response_file_bytes = supabase.storage.from_(TEXT_PROJECT_BUCKET).download(full_file_path)
                file_stream = io.BytesIO(response_file_bytes)
                document = docx.Document(file_stream)
                
                # Extraer texto limpio
                full_text = "\n".join([para.text for para in document.paragraphs if para.text.strip()])
                
                if full_text:
                    documents_list.append({
                        'source': file_name,
                        'content': full_text
                    })
            
            except Exception as e_file:
                st.error(f"Error al procesar el archivo '{file_name}': {e_file}")
                continue 
        
        return documents_list
        
    except Exception as e:
        st.error(f"Error al cargar los archivos del proyecto ({storage_folder_path}): {e}")
        return []

# --- Funciones de UI ---

def show_text_project_creator(user_id, plan_limit):
    # (Esta función no cambia su lógica interna, solo la mostramos por completitud)
    st.subheader("Crear Nuevo Proyecto de Texto")
    
    try:
        response = supabase.table("text_projects").select("id", count='exact').eq("user_id", user_id).execute()
        project_count = response.count
    except Exception as e:
        st.error(f"Error al verificar el conteo de proyectos: {e}")
        return

    if project_count >= plan_limit and plan_limit != float('inf'):
        st.warning(f"Has alcanzado el límite de {int(plan_limit)} proyectos de texto para tu plan actual.")
        return

    max_files_per_project = st.session_state.plan_features.get("text_analysis_max_files_per_project", 1)

    with st.form("new_text_project_form"):
        project_name = st.text_input("Nombre del Proyecto*", placeholder="Ej: Entrevistas NPS Q1 2024")
        project_brand = st.text_input("Marca*", placeholder="Ej: Marca X")
        project_year = st.number_input("Año*", min_value=2020, max_value=2030, value=datetime.now().year)
        uploaded_files = st.file_uploader("Archivos Word (.docx)*", type=["docx"], accept_multiple_files=True)
        
        submitted = st.form_submit_button("Crear Proyecto")

    if submitted:
        if not all([project_name, project_brand, project_year, uploaded_files]):
            st.warning("Por favor, completa todos los campos obligatorios (*).")
            return

        if len(uploaded_files) > max_files_per_project and max_files_per_project != float('inf'):
            st.error(f"Has intentado subir {len(uploaded_files)} archivos. Tu plan permite máx {int(max_files_per_project)}.")
            return

        project_storage_folder = f"{user_id}/{uuid.uuid4()}" 
        
        with st.spinner(f"Creando proyecto y subiendo {len(uploaded_files)} archivo(s)..."):
            try:
                uploaded_file_paths = []
                for uploaded_file in uploaded_files: 
                    base_name = uploaded_file.name.replace(' ', '_')
                    safe_name = re.sub(r'[^\w._-]', '', base_name)
                    storage_file_path = f"{project_storage_folder}/{safe_name}"
                    uploaded_file_paths.append(storage_file_path) 

                    file_bytes = uploaded_file.getvalue()
                    supabase.storage.from_(TEXT_PROJECT_BUCKET).upload(
                        path=storage_file_path,
                        file=file_bytes,
                        file_options={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
                    )

                project_data = {
                    "project_name": project_name, "project_brand": project_brand,
                    "project_year": int(project_year), "storage_path": project_storage_folder, 
                    "user_id": user_id
                }
                supabase.table("text_projects").insert(project_data).execute()
                st.success(f"¡Proyecto '{project_name}' creado exitosamente!")
                st.rerun()

            except Exception as e:
                st.error(f"Error al crear el proyecto: {e}")

def show_text_project_list(user_id):
    st.subheader("Mis Proyectos de Texto")
    try:
        response = supabase.table("text_projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        projects = response.data
    except Exception as e: st.error(f"Error al cargar lista: {e}"); return

    if not projects: st.info("Aún no has creado ningún proyecto de texto."); return

    for proj in projects:
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown(f"**{proj['project_name']}**")
                st.caption(f"Marca: {proj.get('project_brand')} | Año: {proj.get('project_year')}")
            with col2:
                if st.button("Analizar", key=f"analizar_txt_{proj['id']}", width='stretch', type="primary"):
                    st.session_state.mode_state["ta_selected_project_id"] = proj['id']
                    st.session_state.mode_state["ta_selected_project_name"] = proj['project_name']
                    st.session_state.mode_state["ta_storage_path"] = proj['storage_path']
                    st.rerun()
            with col3:
                if st.button("Eliminar", key=f"eliminar_txt_{proj['id']}", width='stretch'):
                    try:
                        # Lógica de borrado simplificada para brevedad
                        files = supabase.storage.from_(TEXT_PROJECT_BUCKET).list(proj['storage_path'])
                        if files: supabase.storage.from_(TEXT_PROJECT_BUCKET).remove([f"{proj['storage_path']}/{f['name']}" for f in files])
                        supabase.table("text_projects").delete().eq("id", proj['id']).execute()
                        st.success("Proyecto eliminado."); st.rerun()
                    except Exception as e: st.error(f"Error al eliminar: {e}")

# --- Función de Análisis (MODIFICADA PARA RAG) ---

def show_text_project_analyzer(summary_context, project_name, documents_list):
    
    st.markdown(f"### Analizando: **{project_name}**")
    
    if st.button("← Volver a la lista de proyectos"):
        st.session_state.mode_state = {}
        st.rerun()
        
    st.divider()
    tab_chat, tab_autocode = st.tabs(["Análisis de Notas y Transcripciones", "Auto-Codificación"])

    # --- Pestaña Chat (RAG IMPLEMENTADO) ---
    with tab_chat:
        st.header("Análisis de Notas y Transcripciones")
        st.markdown("Haz preguntas específicas. **El sistema buscará automáticamente los fragmentos más relevantes en tus documentos.**")
        
        if "transcript_chat_history" not in st.session_state.mode_state: 
            st.session_state.mode_state["transcript_chat_history"] = []

        for msg in st.session_state.mode_state["transcript_chat_history"]:
            with st.chat_message(msg["role"], avatar="✨" if msg['role'] == "assistant" else "👤"):
                st.markdown(msg["content"])

        user_prompt = st.chat_input("Ej: ¿Qué opinan los usuarios sobre el precio?")

        if user_prompt:
            st.session_state.mode_state["transcript_chat_history"].append({"role": "user", "content": user_prompt})
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_prompt)

            question_limit = st.session_state.plan_features.get('text_analysis_questions_per_day', 5)
            current_queries = get_daily_usage(st.session_state.user, c.MODE_TEXT_ANALYSIS) 

            if current_queries >= question_limit and question_limit != float('inf'):
                st.error(f"Límite diario alcanzado ({int(question_limit)} preguntas).")
            else:
                with st.chat_message("assistant", avatar="✨"):
                    # --- PASO CRÍTICO: RAG ---
                    # En lugar de enviar TODO el contexto, filtramos lo relevante.
                    with st.status("Buscando información relevante en los documentos...", expanded=False) as status:
                        # Usamos la función que creamos en utils.py
                        # Limitamos a ~60,000 caracteres (aprox 15k tokens) para ser rápidos y precisos
                        rag_context = build_rag_context(user_prompt, documents_list, max_chars=60000)
                        status.update(label="Información encontrada. Generando respuesta...", state="complete")
                    
                    # Si no hay contexto relevante del RAG, usamos el resumen general como fallback
                    final_context_for_ai = rag_context if rag_context else summary_context
                    
                    chat_prompt = get_transcript_prompt(final_context_for_ai, user_prompt)
                    stream = call_gemini_stream(chat_prompt) 

                    if stream:
                        response_text = st.write_stream(stream)
                        log_query_event(user_prompt, mode=f"{c.MODE_TEXT_ANALYSIS} (Chat)")
                        st.session_state.mode_state["transcript_chat_history"].append({
                            "role": "assistant", "content": response_text
                        })
                    else:
                        st.error("Error al obtener respuesta.")

        if st.session_state.mode_state["transcript_chat_history"]:
            # (Botones de descarga PDF igual que antes)
            st.divider() 
            col1, col2 = st.columns([1,1])
            with col1:
                chat_raw = "\n\n".join(f"**{m['role']}:** {m['content']}" for m in st.session_state.mode_state["transcript_chat_history"])
                pdf_bytes = generate_pdf_html(chat_raw.replace("](#)", "]"), title=f"Chat - {project_name}", banner_path=banner_file)
                if pdf_bytes: st.download_button("Descargar Chat PDF", data=pdf_bytes, file_name="chat.pdf", mime="application/pdf", width='stretch')
            with col2: 
                st.button("Nueva Conversación", on_click=reset_transcript_chat_workflow, key="new_transcript_chat_btn", width='stretch')

    # --- Pestaña Auto-Codificación (Usa Resumen Global) ---
    with tab_autocode:
        st.header("Auto-Codificación")
        if "autocode_result" in st.session_state.mode_state:
            st.markdown("### Reporte de Temas"); st.markdown(st.session_state.mode_state["autocode_result"])
            col1, col2 = st.columns(2)
            with col1:
                pdf_bytes = generate_pdf_html(st.session_state.mode_state["autocode_result"], title="Reporte Temas", banner_path=banner_file)
                if pdf_bytes: st.download_button("Descargar PDF", data=pdf_bytes, file_name="reporte.pdf", mime="application/pdf", width='stretch')
            with col2:
                if st.button("Nuevo reporte", width='stretch', type="secondary"):
                    st.session_state.mode_state.pop("autocode_result", None); st.rerun()
        else:
            st.markdown("Esta herramienta analizará el **resumen global** para detectar temas.")
            main_topic = st.text_input("¿Cuál es el tema principal?", placeholder="Ej: Percepción de marca")
            if st.button("Analizar Temas", width='stretch', type="primary"):
                if not main_topic.strip(): st.warning("Describe el tema.")
                else:
                    with st.spinner("Analizando..."):
                        # Para temas macro, usamos el resumen general, no el RAG
                        prompt = get_autocode_prompt(summary_context, main_topic)
                        stream = call_gemini_stream(prompt)
                        if stream:
                            response = st.write_stream(stream)
                            st.session_state.mode_state["autocode_result"] = response
                            log_query_event(f"Autocode: {main_topic}", mode=f"{c.MODE_TEXT_ANALYSIS} (Autocode)")
                            st.rerun()

# --- Función Principal ---

def text_analysis_mode():
    st.subheader(c.MODE_TEXT_ANALYSIS)
    st.markdown("Carga, gestiona y analiza tus proyectos de transcripciones (.docx).")
    st.divider()

    user_id = st.session_state.user_id
    plan_limit = st.session_state.plan_features.get('transcript_file_limit', 0)

    # 1. Cargar DOCUMENTOS ESTRUCTURADOS
    if "ta_selected_project_id" in st.session_state.mode_state and "ta_documents_list" not in st.session_state.mode_state:
        with st.spinner("Cargando documentos del proyecto..."):
            docs = load_text_project_data(st.session_state.mode_state["ta_storage_path"]) 
            if docs:
                st.session_state.mode_state["ta_documents_list"] = docs
            else:
                st.error("No se pudieron cargar los datos.")
                st.session_state.mode_state = {} # Reset si falla

    # 2. Generar el RESUMEN INICIAL (Solo una vez)
    if "ta_documents_list" in st.session_state.mode_state and "ta_summary_context" not in st.session_state.mode_state:
        with st.spinner("Generando resumen ejecutivo inicial..."):
            docs = st.session_state.mode_state["ta_documents_list"]
            
            # Estrategia: Unir los primeros 2000 caracteres de cada documento para el resumen general
            # Esto evita desbordar tokens pero da una idea general a la IA
            summary_input = ""
            for d in docs:
                summary_input += f"\nDocumento: {d['source']}\n{d['content'][:2500]}\n...\n"
            
            summary_prompt = get_text_analysis_summary_prompt(summary_input)
            summary = call_gemini_api(summary_prompt, generation_config_override={"max_output_tokens": 8192})
            
            if summary:
                st.session_state.mode_state["ta_summary_context"] = summary
                st.rerun() 
            else:
                st.error("Error generando resumen inicial.")

    # 3. VISTA DE ANÁLISIS
    if "ta_summary_context" in st.session_state.mode_state:
        show_text_project_analyzer( 
            st.session_state.mode_state["ta_summary_context"],
            st.session_state.mode_state["ta_selected_project_name"],
            st.session_state.mode_state["ta_documents_list"] # Pasamos la lista para el RAG
        )
    
    # 4. VISTA DE CARGA
    elif "ta_selected_project_id" in st.session_state.mode_state:
        st.info("Cargando proyecto...") 
    
    # 5. VISTA DE GESTIÓN
    else:
        with st.expander("➕ Crear Nuevo Proyecto de Texto", expanded=True):
            show_text_project_creator(user_id, plan_limit)
        st.divider()
        show_text_project_list(user_id)
