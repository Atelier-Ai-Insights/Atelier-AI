import streamlit as st
import docx
import io
import os  
import uuid
from datetime import datetime
import re 
from PIL import Image
import fitz # PyMuPDF

# --- IMPORTACIONES ---
from services.gemini_api import call_gemini_api, call_gemini_stream 
from services.supabase_db import log_query_event, supabase, get_daily_usage
from prompts import get_etnochat_prompt, get_media_transcription_prompt # <-- Nuevo prompt importado
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from utils import reset_etnochat_chat_workflow

# =====================================================
# MODO: ANÁLISIS DE ETNOCHAT (OPTIMIZADO)
# =====================================================

ETNOCHAT_BUCKET = "etnochat_projects"

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
    ".mp4": "video/mp4", 
    ".mov": "video/quicktime"
}
ALLOWED_EXTENSIONS = list(MIME_TYPES.keys())

# --- Funciones de Carga de Datos ---

@st.cache_data(ttl=600, show_spinner=False)
def load_etnochat_project_data(storage_folder_path: str):
    """
    Descarga archivos. 
    OPTIMIZACIÓN: Convierte Audio/Video a texto UNA VEZ y guarda el resultado (.txt) 
    para no re-procesar el archivo pesado en cada consulta.
    """
    if not storage_folder_path:
        st.error("Error: La ruta de la carpeta del proyecto está vacía.")
        return None, None
        
    text_context_parts = []
    file_parts = [] # Aquí solo irán las IMÁGENES (que siguen siendo útiles visualmente)
    
    try:
        # 1. Listar archivos
        files_list = supabase.storage.from_(ETNOCHAT_BUCKET).list(storage_folder_path)
        if not files_list:
            st.warning("El proyecto no contiene archivos.")
            return "", []

        # Mapa rápido de archivos existentes para verificar si ya existe el transcript
        existing_filenames = {f['name'] for f in files_list}

        st.write(f"Procesando {len(files_list)} archivo(s) del proyecto...")
        
        # Barra de progreso para cargas pesadas
        progress_bar = st.progress(0)
        total_files = len(files_list)

        for i, file_info in enumerate(files_list):
            file_name = file_info['name']
            
            # Ignorar los archivos de transcripción generados automáticamente para no duplicarlos
            if file_name.endswith("_transcript.txt"):
                progress_bar.progress((i + 1) / total_files)
                continue

            full_file_path = f"{storage_folder_path}/{file_name}"
            file_ext = os.path.splitext(file_name)[1].lower()
            
            try:
                # Descargar archivo
                response_bytes = supabase.storage.from_(ETNOCHAT_BUCKET).download(full_file_path)
                file_stream = io.BytesIO(response_bytes)
                
                header = f"\n\n--- INICIO DOCUMENTO: {file_name} ---\n\n"
                footer = f"\n\n--- FIN DOCUMENTO: {file_name} ---\n"
                
                # --- CASO 1: DOCUMENTOS DE TEXTO ---
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

                # --- CASO 2: IMÁGENES (Se mantienen como multimedia) ---
                elif file_ext in [".jpg", ".jpeg", ".png"]:
                    img = Image.open(file_stream)
                    file_parts.append(img)
                    text_context_parts.append(f"[Archivo de Imagen Cargado: {file_name} - La IA puede ver esta imagen]")

                # --- CASO 3: AUDIO Y VIDEO (¡OPTIMIZACIÓN!) ---
                elif file_ext in MIME_TYPES and ("audio" in MIME_TYPES[file_ext] or "video" in MIME_TYPES[file_ext]):
                    
                    transcript_filename = f"{file_name}_transcript.txt"
                    transcript_full_path = f"{storage_folder_path}/{transcript_filename}"
                    
                    transcript_text = ""

                    # A. Verificar si ya existe la transcripción en el bucket
                    if transcript_filename in existing_filenames:
                        # ¡Bingo! Ya existe. La descargamos.
                        # print(f"INFO: Usando transcripción existente para {file_name}")
                        try:
                            trans_bytes = supabase.storage.from_(ETNOCHAT_BUCKET).download(transcript_full_path)
                            transcript_text = trans_bytes.decode('utf-8')
                        except Exception as e:
                            st.warning(f"Error leyendo transcripción existente {transcript_filename}: {e}")
                    
                    # B. Si no existe, la generamos con Gemini
                    if not transcript_text:
                        # print(f"INFO: Generando nueva transcripción para {file_name}")
                        with st.spinner(f"Transcribiendo {file_name} con IA... (Una sola vez)"):
                            media_data = {"mime_type": MIME_TYPES[file_ext], "data": response_bytes}
                            prompt_transcribe = get_media_transcription_prompt()
                            
                            # Llamada NO-streaming para obtener el texto completo
                            # Usamos un limite alto de tokens para asegurar transcripción completa
                            generated_transcript = call_gemini_api([prompt_transcribe, media_data], generation_config_override={"max_output_tokens": 8192})
                            
                            if generated_transcript:
                                transcript_text = generated_transcript
                                # C. Guardar la transcripción en Supabase para el futuro
                                try:
                                    supabase.storage.from_(ETNOCHAT_BUCKET).upload(
                                        path=transcript_full_path,
                                        file=generated_transcript.encode('utf-8'),
                                        file_options={"content-type": "text/plain"}
                                    )
                                except Exception as e_upload:
                                    print(f"Error subiendo transcripción automática: {e_upload}")
                            else:
                                transcript_text = "[Error: No se pudo transcribir este archivo multimedia]"

                    # Añadir el texto resultante al contexto
                    text_context_parts.append(f"{header}[TRANSCRIPCIÓN AUTOMÁTICA DE {file_name}]\n{transcript_text}{footer}")

            except Exception as e_file:
                st.error(f"Error al procesar el archivo '{file_name}': {e_file}")
                continue
            
            progress_bar.progress((i + 1) / total_files)
        
        progress_bar.empty()
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
            accept_multiple_files=True,
            help=f"Tu plan te permite subir un máximo de {int(files_per_project_limit) if files_per_project_limit != float('inf') else 'ilimitados'} archivos."
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

    user_prompt = st.chat_input("Haz una pregunta sobre los archivos...")

    if user_prompt:
        st.session_state.mode_state["etno_chat_history"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        question_limit = st.session_state.plan_features.get('etnochat_questions_per_day', 5)
        current_queries = get_daily_usage(st.session_state.user, c.MODE_ETNOCHAT) 

        if current_queries >= question_limit and question_limit != float('inf'):
            st.error(f"Has alcanzado tu límite de {int(question_limit)} preguntas diarias para el Análisis EtnoChat.")
            st.session_state.mode_state["etno_chat_history"].pop()
            return

        with st.chat_message("assistant", avatar="✨"):
            
            history_str = "\n".join(f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["etno_chat_history"][-10:])
            
            # 1. Crear el prompt de texto
            prompt_text = get_etnochat_prompt(history_str, text_context)
            
            # 2. Crear la lista final. Nota que ahora file_parts SOLO tiene imágenes.
            # Los audios/videos ya fueron convertidos a text_context.
            final_prompt_list = [prompt_text] + file_parts
            
            # --- STREAMING ---
            stream = call_gemini_stream(final_prompt_list) 

            if stream:
                response_text = st.write_stream(stream) # Efecto visual
                
                log_query_event(user_prompt, mode=c.MODE_ETNOCHAT)
                st.session_state.mode_state["etno_chat_history"].append({
                    "role": "assistant", 
                    "content": response_text
                })
            else:
                message_placeholder = st.empty()
                message_placeholder.error("Error al obtener respuesta multimodal.")
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
                on_click=reset_etnochat_chat_workflow, 
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

    # 1. Cargar los datos del proyecto si está seleccionado pero no cargado
    if "etno_selected_project_id" in st.session_state.mode_state and "etno_file_parts" not in st.session_state.mode_state:
        
        # El mensaje se muestra dentro de load_etnochat_project_data a través de la barra de progreso
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

    # 1. VISTA DE ANÁLISIS
    if "etno_file_parts" in st.session_state.mode_state:
        show_etnochat_project_analyzer( 
            st.session_state.mode_state["etno_context_str"],
            st.session_state.mode_state["etno_file_parts"],
            st.session_state.mode_state["etno_selected_project_name"]
        )
    
    # 2. VISTA DE CARGA (Mientras se procesa)
    elif "etno_selected_project_id" in st.session_state.mode_state:
        st.info("Iniciando carga y transcripción de archivos multimedia...")
    
    # 3. VISTA DE GESTIÓN
    else:
        with st.expander("➕ Crear Nuevo Proyecto EtnoChat", expanded=True):
            show_etnochat_project_creator(user_id, project_limit, files_per_project_limit)
        
        st.divider()
        
        show_etnochat_project_list(user_id)
