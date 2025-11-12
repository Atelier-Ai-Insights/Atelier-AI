import streamlit as st
import docx
import io
import os  
import uuid
from datetime import datetime
import re 
from PIL import Image
import fitz # PyMuPDF

from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event, supabase, get_daily_usage
from prompts import get_etnochat_prompt
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from utils import reset_etnochat_chat_workflow

# =====================================================
# MODO: ANÁLISIS DE ETNOCHAT
# =====================================================

ETNOCHAT_BUCKET = "etnochat_projects"

# Diccionario de Mime types para la carga
MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/m4a",
    ".wav": "audio/wav",
    ".mp4": "video/mp4", # Soportado por Gemini
    ".mov": "video/quicktime" # Soportado por Gemini
}
# Lista de extensiones permitidas para el file_uploader
ALLOWED_EXTENSIONS = list(MIME_TYPES.keys())

# --- Funciones de Carga de Datos ---

@st.cache_data(ttl=600, show_spinner=False)
def load_etnochat_project_data(storage_folder_path: str):
    """
    Descarga TODOS los archivos (texto, audio, imagen) de una carpeta 
    en Supabase Storage y los prepara para la API multimodal.
    
    Devuelve: (context_string, file_parts)
    - context_string: Un solo string con todo el texto extraído.
    - file_parts: Una lista de dicts {mime_type, data} para archivos de imagen/audio/video.
    """
    if not storage_folder_path:
        st.error("Error: La ruta de la carpeta del proyecto está vacía.")
        return None, None
        
    text_context_parts = []
    file_parts = []
    
    try:
        files_list = supabase.storage.from_(ETNOCHAT_BUCKET).list(storage_folder_path)
        
        if not files_list:
            st.warning("El proyecto no contiene archivos.")
            return "", []

        st.write(f"Cargando {len(files_list)} archivo(s) del proyecto...")

        for file_info in files_list:
            file_name = file_info['name']
            full_file_path = f"{storage_folder_path}/{file_name}"
            file_ext = os.path.splitext(file_name)[1].lower()
            
            try:
                response_bytes = supabase.storage.from_(ETNOCHAT_BUCKET).download(full_file_path)
                file_stream = io.BytesIO(response_bytes)
                
                header = f"\n\n--- INICIO DOCUMENTO: {file_name} ---\n\n"
                footer = f"\n\n--- FIN DOCUMENTO: {file_name} ---\n"
                
                # 1. Procesar Archivos de Texto
                if file_ext == ".txt":
                    text = file_stream.read().decode('utf-8')
                    text_context_parts.append(f"{header}{text}{footer}")
                
                elif file_ext == ".pdf":
                    pdf_doc = fitz.open(stream=file_stream, filetype="pdf")
                    text = "".join(page.get_text() for page in pdf_doc)
                    pdf_doc.close()
                    text_context_parts.append(f"{header}{text}{footer}")

                elif file_ext == ".docx":
                    document = docx.Document(file_stream)
                    text = "\n".join([para.text for para in document.paragraphs if para.text.strip()])
                    text_context_parts.append(f"{header}{text}{footer}")

                # 2. Procesar Imágenes (Guardar como objeto PIL Image)
                elif file_ext in [".jpg", ".jpeg", ".png"]:
                    # Pasamos el objeto Image directamente a Gemini
                    img = Image.open(file_stream)
                    file_parts.append(img)
                    # Añadimos una referencia en el texto para que la IA sepa que existe
                    text_context_parts.append(f"[Archivo de Imagen Cargado: {file_name}]")

                # 3. Procesar Audio/Video (Guardar como dict mime/data)
                elif file_ext in MIME_TYPES:
                    mime_type = MIME_TYPES[file_ext]
                    file_parts.append({"mime_type": mime_type, "data": response_bytes})
                    # Añadimos una referencia en el texto
                    text_context_parts.append(f"[Archivo Multimedia Cargado: {file_name}]")
            
            except Exception as e_file:
                st.error(f"Error al procesar el archivo '{file_name}': {e_file}")
                continue 
        
        combined_text_context = "\n".join(text_context_parts)
        return combined_text_context, file_parts
        
    except Exception as e:
        st.error(f"Error al cargar los archivos del proyecto ({storage_folder_path}): {e}")
        return None, None

# --- Funciones de UI ---

def show_etnochat_project_creator(user_id, project_limit, files_per_project_limit):
    st.subheader("Crear Nuevo Proyecto EtnoChat")
    
    try:
        response = supabase.table("etnochat_projects").select("id", count='exact').eq("user_id", user_id).execute()
        project_count = response.count
    except Exception as e:
        st.error(f"Error al verificar el conteo de proyectos: {e}")
        return

    if project_count >= project_limit and project_limit != float('inf'):
        st.warning(f"Has alcanzado el límite de {int(project_limit)} proyectos EtnoChat para tu plan actual. Deberás eliminar un proyecto existente para crear uno nuevo.")
        return

    with st.form("new_etnochat_project_form"):
        project_name = st.text_input("Nombre del Proyecto*", placeholder="Ej: Etnografía Cocinas Cali")
        project_brand = st.text_input("Marca*", placeholder="Ej: Marca Y")
        project_year = st.number_input("Año*", min_value=2020, max_value=2030, value=datetime.now().year)
        
        uploaded_files = st.file_uploader(
            "Cargar Archivos (txt, docx, pdf, jpg, png, mp3, m4a, mp4, mov)*",
            type=[ext.lstrip('.') for ext in ALLOWED_EXTENSIONS],
            accept_multiple_files=True
        )
        
        if files_per_project_limit == float('inf'):
            st.caption(f"Puedes cargar múltiples archivos. (Límite: Ilimitado)")
        else:
            st.caption(f"Puedes cargar múltiples archivos. (Límite de tu plan: {int(files_per_project_limit)} archivos)")

        
        submitted = st.form_submit_button("Crear Proyecto")

    if submitted:
        if not all([project_name, project_brand, project_year, uploaded_files]):
            st.warning("Por favor, completa todos los campos obligatorios (*).")
            return

        if len(uploaded_files) > files_per_project_limit and files_per_project_limit != float('inf'):
            st.error(f"Has intentado subir {len(uploaded_files)} archivos. Tu plan te permite un máximo de {int(files_per_project_limit)} archivos por proyecto.")
            return

        project_storage_folder = f"{user_id}/{uuid.uuid4()}" 
        
        spinner_text = f"Creando proyecto y subiendo {len(uploaded_files)} archivo(s)..."
        with st.spinner(spinner_text):
            try:
                uploaded_file_paths = [] 
                
                for uploaded_file in uploaded_files: 
                    base_name = uploaded_file.name.replace(' ', '_')
                    safe_name = re.sub(r'[^\w._-]', '', base_name)
                    file_ext = os.path.splitext(safe_name)[1].lower()
                    
                    if not safe_name or safe_name.startswith('.'):
                        safe_name = f"archivo_{uuid.uuid4()}{file_ext}"
                    
                    if file_ext not in MIME_TYPES:
                        st.warning(f"Archivo '{safe_name}' omitido: tipo no soportado.")
                        continue

                    storage_file_path = f"{project_storage_folder}/{safe_name}"
                    uploaded_file_paths.append(storage_file_path) 

                    file_bytes = uploaded_file.getvalue()
                    supabase.storage.from_(ETNOCHAT_BUCKET).upload(
                        path=storage_file_path,
                        file=file_bytes,
                        file_options={"content-type": MIME_TYPES[file_ext]}
                    )

                project_data = {
                    "project_name": project_name,
                    "project_brand": project_brand,
                    "project_year": int(project_year),
                    "storage_path": project_storage_folder, 
                    "user_id": user_id
                }
                
                supabase.table("etnochat_projects").insert(project_data).execute()
                
                st.success(f"¡Proyecto '{project_name}' creado exitosamente!")
                st.rerun()

            except Exception as e:
                st.error(f"Error al crear el proyecto: {e}")
                try:
                    if uploaded_file_paths: 
                        supabase.storage.from_(ETNOCHAT_BUCKET).remove(uploaded_file_paths)
                except:
                    pass 

def show_etnochat_project_list(user_id):
    st.subheader("Mis Proyectos EtnoChat")
    
    try:
        response = supabase.table("etnochat_projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        projects = response.data
    except Exception as e:
        st.error(f"Error al cargar la lista de proyectos: {e}")
        return

    if not projects:
        st.info("Aún no has creado ningún proyecto EtnoChat. Usa el formulario de arriba para empezar.")
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
                if st.button("Analizar", key=f"analizar_etno_{proj_id}", use_container_width=True, type="primary"):
                    st.session_state.mode_state["etno_selected_project_id"] = proj_id
                    st.session_state.mode_state["etno_selected_project_name"] = proj_name
                    st.session_state.mode_state["etno_storage_path"] = storage_path
                    st.rerun()
            
            with col3:
                if st.button("Eliminar", key=f"eliminar_etno_{proj_id}", use_container_width=True):
                    with st.spinner("Eliminando proyecto y sus archivos..."):
                        try:
                            if storage_path:
                                files_in_project = supabase.storage.from_(ETNOCHAT_BUCKET).list(storage_path)
                                if files_in_project:
                                    paths_to_remove = [f"{storage_path}/{f['name']}" for f in files_in_project]
                                    supabase.storage.from_(ETNOCHAT_BUCKET).remove(paths_to_remove)
                            
                            supabase.table("etnochat_projects").delete().eq("id", proj_id).execute()
                            
                            st.success(f"Proyecto '{proj_name}' eliminado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar: {e}")

def show_etnochat_project_analyzer(text_context, file_parts, project_name):
    """
    Muestra la UI de chat multimodal.
    """
    
    st.markdown(f"### Analizando: **{project_name}**")
    
    if st.button("← Volver a la lista de proyectos"):
        st.session_state.mode_state = {}
        st.rerun()
        
    st.divider()

    st.header("Chat Etnográfico Multimodal")
    st.markdown("Conversa con todos los datos de tu proyecto (textos, audios, imágenes y videos).")
    
    if "etno_chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["etno_chat_history"] = []

    for msg in st.session_state.mode_state["etno_chat_history"]:
        with st.chat_message(msg["role"], avatar="✨" if msg['role'] == "assistant" else "👤"):
            st.markdown(msg["content"])

    user_prompt = st.chat_input("Haz una pregunta sobre los archivos (ej. 'Resume el audio 1 y compáralo con la foto 3')...")

    if user_prompt:
        st.session_state.mode_state["etno_chat_history"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        # Verificar límites de preguntas
        question_limit = st.session_state.plan_features.get('etnochat_questions_per_day', 5)
        current_queries = get_daily_usage(st.session_state.user, c.MODE_ETNOCHAT) 

        if current_queries >= question_limit and question_limit != float('inf'):
            st.error(f"Has alcanzado tu límite de {int(question_limit)} preguntas diarias para el Análisis EtnoChat.")
            st.session_state.mode_state["etno_chat_history"].pop()
            return

        with st.chat_message("assistant", avatar="✨"):
            message_placeholder = st.empty(); message_placeholder.markdown("Analizando todos los archivos...")
            
            history_str = "\n".join(f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["etno_chat_history"][-10:])
            
            # 1. Crear el prompt de texto
            prompt_text = get_etnochat_prompt(history_str, text_context)
            
            # 2. Crear la lista final para la API
            #    El prompt de texto DEBE ir primero
            final_prompt_list = [prompt_text] + file_parts
            
            response = call_gemini_api(final_prompt_list) 

            if response:
                message_placeholder.markdown(response)
                log_query_event(user_prompt, mode=c.MODE_ETNOCHAT)
                st.session_state.mode_state["etno_chat_history"].append({
                    "role": "assistant", 
                    "content": response
                })
                st.rerun()
            else:
                message_placeholder.error("Error al obtener respuesta multimodal."); 
                st.session_state.mode_state["etno_chat_history"].pop()

    # Añadir botones de descarga y nueva conversación
    if st.session_state.mode_state["etno_chat_history"]:
        st.divider() 
        col1, col2 = st.columns([1,1])
        with col1:
            chat_content_raw = "\n\n".join(f"**{m['role']}:** {m['content']}" for m in st.session_state.mode_state["etno_chat_history"])
            chat_content_for_pdf = chat_content_raw.replace("](#)", "]")
            pdf_bytes = generate_pdf_html(chat_content_for_pdf, title=f"Chat EtnoChat - {project_name}", banner_path=banner_file)
            
            if pdf_bytes: 
                st.download_button(
                    "Descargar Chat PDF", 
                    data=pdf_bytes, 
                    file_name=f"chat_etnochat_{project_name.lower().replace(' ','_')}.pdf", 
                    mime="application/pdf", 
                    use_container_width=True
                )
        with col2: 
            st.button(
                "Nueva Conversación", 
                on_click=reset_etnochat_chat_workflow, # <-- Usar la nueva función de reseteo
                key="new_etno_chat_btn", 
                use_container_width=True
            )

# --- FUNCIÓN PRINCIPAL DEL MODO ---

def etnochat_mode():
    st.subheader(c.MODE_ETNOCHAT)
    st.markdown("Carga y analiza conversaciones de WhatsApp, incluyendo textos, audios, imágenes y videos.")
    st.divider()

    user_id = st.session_state.user_id
    plan_features = st.session_state.plan_features
    project_limit = plan_features.get('etnochat_project_limit', 0)
    files_per_project_limit = plan_features.get('etnochat_max_files_per_project', 0)

    # --- Lógica de Carga de Datos (una sola vez por proyecto) ---
    
    # 1. Cargar los datos del proyecto si está seleccionado pero no cargado
    if "etno_selected_project_id" in st.session_state.mode_state and "etno_file_parts" not in st.session_state.mode_state:
        with st.spinner("Cargando y procesando archivos del proyecto..."):
            text_ctx, file_parts = load_etnochat_project_data(st.session_state.mode_state["etno_storage_path"]) 
            
            if text_ctx is not None and file_parts is not None:
                st.session_state.mode_state["etno_context_str"] = text_ctx
                st.session_state.mode_state["etno_file_parts"] = file_parts
            else:
                st.error("No se pudieron cargar los datos del proyecto.")
                st.session_state.mode_state.pop("etno_selected_project_id", None)
                st.session_state.mode_state.pop("etno_selected_project_name", None)
                st.session_state.mode_state.pop("etno_storage_path", None)

    # --- Lógica de Vistas ---

    # 1. VISTA DE ANÁLISIS (Si los datos del proyecto ya están cargados)
    if "etno_file_parts" in st.session_state.mode_state:
        show_etnochat_project_analyzer( 
            st.session_state.mode_state["etno_context_str"],
            st.session_state.mode_state["etno_file_parts"],
            st.session_state.mode_state["etno_selected_project_name"]
        )
    
    # 2. VISTA DE CARGA (Si está seleccionado pero cargando)
    elif "etno_selected_project_id" in st.session_state.mode_state:
        st.info("Preparando análisis...")
        st.spinner("Cargando y procesando archivos del proyecto...") 
    
    # 3. VISTA DE GESTIÓN (Página principal del modo)
    else:
        with st.expander("➕ Crear Nuevo Proyecto EtnoChat", expanded=True):
            show_etnochat_project_creator(user_id, project_limit, files_per_project_limit)
        
        st.divider()
        
        show_etnochat_project_list(user_id)
