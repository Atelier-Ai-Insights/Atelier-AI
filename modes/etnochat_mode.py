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
from prompts import get_etnochat_prompt, get_media_transcription_prompt 
import constants as c
from reporting.pdf_generator import generate_pdf_html
# --- NUEVA IMPORTACIÓN ---
from reporting.docx_generator import generate_docx
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
    file_parts = [] # Aquí solo irán las IMÁGENES
    
    try:
        # 1. Listar archivos
        files_list = supabase.storage.from_(ETNOCHAT_BUCKET).list(storage_folder_path)
        if not files_list:
            st.warning("El proyecto no contiene archivos.")
            return "", []

        existing_filenames = {f['name'] for f in files_list}

        st.write(f"Procesando {len(files_list)} archivo(s) del proyecto...")
        
        progress_bar = st.progress(0)
        total_files = len(files_list)

        for i, file_info in enumerate(files_list):
            file_name = file_info['name']
            
            if file_name.endswith("_transcript.txt"):
                progress_bar.progress((i + 1) / total_files)
                continue

            full_file_path = f"{storage_folder_path}/{file_name}"
            file_ext = os.path.splitext(file_name)[1].lower()
            
            try:
                response_bytes = supabase.storage.from_(ETNOCHAT_BUCKET).download(full_file_path)
                file_stream = io.BytesIO(response_bytes)
                
                header = f"\n\n--- INICIO DOCUMENTO: {file_name} ---\n\n"
                footer = f"\n\n--- FIN DOCUMENTO: {file_name} ---\n"
                
                # --- TEXTO ---
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

                # --- IMÁGENES ---
                elif file_ext in [".jpg", ".jpeg", ".png"]:
                    img = Image.open(file_stream)
                    file_parts.append(img)
                    text_context_parts.append(f"[Archivo de Imagen Cargado: {file_name} - La IA puede ver esta imagen]")

                # --- AUDIO Y VIDEO ---
                elif file_ext in MIME_TYPES and ("audio" in MIME_TYPES[file_ext] or "video" in MIME_TYPES[file_ext]):
                    
                    transcript_filename = f"{file_name}_transcript.txt"
                    transcript_full_path = f"{storage_folder_path}/{transcript_filename}"
                    transcript_text = ""

                    if transcript_filename in existing_filenames:
                        try:
                            trans_bytes = supabase.storage.from_(ETNOCHAT_BUCKET).download(transcript_full_path)
                            transcript_text = trans_bytes.decode('utf-8')
                        except Exception as e:
                            st.warning(f"Error leyendo transcripción existente {transcript_filename}: {e}")
                    
                    if not transcript_text:
                        with st.spinner(f"Transcribiendo {file_name} con IA... (Una sola vez)"):
                            media_data = {"mime_type": MIME_TYPES[file_ext], "data": response_bytes}
                            prompt_transcribe = get_media_transcription_prompt()
                            
                            generated_transcript = call_gemini_api([prompt_transcribe, media_data], generation_config_override={"max_output_tokens": 8192})
                            
                            if generated_transcript:
                                transcript_text = generated_transcript
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
        st.warning(f"Has alcanzado el límite de {int(project_limit)} proyectos EtnoChat.")
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
        
        submitted = st.form_submit_button("Crear Proyecto")

    if submitted:
        if not all([project_name, project_brand, project_year, uploaded_files]):
            st.warning("Por favor, completa todos los campos obligatorios (*).")
            return

        if len(uploaded_files) > files_per_project_limit and files_per_project_limit != float('inf'):
            st.error(f"Límite de archivos excedido. Máximo: {int(files_per_project_limit)}.")
            return

        project_storage_folder = f"{user_id}/{uuid.uuid4()}" 
        
        with st.spinner(f"Creando proyecto y subiendo {len(uploaded_files)} archivo(s)..."):
            try:
                uploaded_file_paths = [] 
                for uploaded_file in uploaded_files: 
                    base_name = uploaded_file.name.replace(' ', '_')
                    safe_name = re.sub(r'[^\w._-]', '', base_name)
                    file_ext = os.path.splitext(safe_name)[1].lower()
                    
                    if not safe_name or safe_name.startswith('.'):
                        safe_name = f"archivo_{uuid.uuid4()}{file_ext}"
                    
                    storage_file_path = f"{project_storage_folder}/{safe_name}"
                    uploaded_file_paths.append(storage_file_path) 

                    supabase.storage.from_(ETNOCHAT_BUCKET).upload(
                        path=storage_file_path,
                        file=uploaded_file.getvalue(),
                        file_options={"content-type": MIME_TYPES.get(file_ext, "application/octet-stream")}
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

def show_etnochat_project_list(user_id):
    st.subheader("Mis Proyectos EtnoChat")
    try:
        response = supabase.table("etnochat_projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        projects = response.data
    except Exception as e: st.error(f"Error al cargar lista: {e}"); return

    if not projects: st.info("No hay proyectos."); return

    for proj in projects:
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown(f"**{proj['project_name']}**")
                st.caption(f"Marca: {proj.get('project_brand')} | Año: {proj.get('project_year')}")
            with col2:
                if st.button("Analizar", key=f"analizar_etno_{proj['id']}", width='stretch', type="primary"):
                    st.session_state.mode_state["etno_selected_project_id"] = proj['id']
                    st.session_state.mode_state["etno_selected_project_name"] = proj['project_name']
                    st.session_state.mode_state["etno_storage_path"] = proj['storage_path']
                    st.rerun()
            with col3:
                if st.button("Eliminar", key=f"eliminar_etno_{proj['id']}", width='stretch'):
                    try:
                        if proj['storage_path']:
                            files_in_project = supabase.storage.from_(ETNOCHAT_BUCKET).list(proj['storage_path'])
                            if files_in_project:
                                paths = [f"{proj['storage_path']}/{f['name']}" for f in files_in_project]
                                supabase.storage.from_(ETNOCHAT_BUCKET).remove(paths)
                        supabase.table("etnochat_projects").delete().eq("id", proj['id']).execute()
                        st.success("Eliminado."); st.rerun()
                    except Exception as e: st.error(f"Error al eliminar: {e}")

def show_etnochat_project_analyzer(text_context, file_parts, project_name):
    """
    Muestra la UI de chat multimodal con exportación a Word y PDF.
    """
    st.markdown(f"### Analizando: **{project_name}**")
    
    if st.button("← Volver a la lista de proyectos"):
        st.session_state.mode_state = {}
        st.rerun()
        
    st.divider()
    st.header("Chat Etnográfico Multimodal")
    
    if "etno_chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["etno_chat_history"] = []

    for msg in st.session_state.mode_state["etno_chat_history"]:
        with st.chat_message(msg["role"], avatar="✨" if msg['role'] == "assistant" else "👤"):
            st.markdown(msg["content"])

    user_prompt = st.chat_input("Haz una pregunta sobre los archivos...")

    if user_prompt:
        st.session_state.mode_state["etno_chat_history"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"): st.markdown(user_prompt)

        question_limit = st.session_state.plan_features.get('etnochat_questions_per_day', 5)
        current_queries = get_daily_usage(st.session_state.user, c.MODE_ETNOCHAT) 

        if current_queries >= question_limit and question_limit != float('inf'):
            st.error(f"Has alcanzado tu límite de preguntas diarias.")
            st.session_state.mode_state["etno_chat_history"].pop()
            return

        with st.chat_message("assistant", avatar="✨"):
            history_str = "\n".join(f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["etno_chat_history"][-10:])
            prompt_text = get_etnochat_prompt(history_str, text_context)
            final_prompt_list = [prompt_text] + file_parts
            
            stream = call_gemini_stream(final_prompt_list) 

            if stream:
                response_text = st.write_stream(stream) 
                log_query_event(user_prompt, mode=c.MODE_ETNOCHAT)
                st.session_state.mode_state["etno_chat_history"].append({"role": "assistant", "content": response_text})
            else:
                st.error("Error al obtener respuesta multimodal.")
                st.session_state.mode_state["etno_chat_history"].pop()

    # --- BOTONES DE EXPORTACIÓN Y REINICIO ---
    if st.session_state.mode_state["etno_chat_history"]:
        st.divider() 
        
        # Preparar contenido crudo para las exportaciones
        chat_content_raw = f"# Reporte Etnográfico: {project_name}\n\n"
        chat_content_raw += "\n\n".join(f"**{m['role'].upper()}:** {m['content']}" for m in st.session_state.mode_state["etno_chat_history"])
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # PDF
            pdf_bytes = generate_pdf_html(chat_content_raw.replace("](#)", "]"), title=f"EtnoChat - {project_name}", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button("📄 Chat en PDF", data=pdf_bytes, file_name="etno_chat.pdf", mime="application/pdf", width='stretch')
        
        with col2:
            # WORD (Nuevo)
            docx_bytes = generate_docx(chat_content_raw, title=f"EtnoChat - {project_name}")
            if docx_bytes:
                st.download_button("📝 Chat en Word", data=docx_bytes, file_name="etno_chat.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width='stretch', type="primary")

        with col3: 
            st.button("🔄 Reiniciar Chat", on_click=reset_etnochat_chat_workflow, key="new_etno_chat_btn", width='stretch')

# --- FUNCIÓN PRINCIPAL DEL MODO ---

def etnochat_mode():
    st.subheader(c.MODE_ETNOCHAT)
    st.markdown("Carga y analiza conversaciones de WhatsApp, incluyendo textos, audios, imágenes y videos.")
    st.divider()

    user_id = st.session_state.user_id
    project_limit = st.session_state.plan_features.get('etnochat_project_limit', 0)
    files_per_project_limit = st.session_state.plan_features.get('etnochat_max_files_per_project', 0)

    # 1. Cargar datos si hay proyecto seleccionado
    if "etno_selected_project_id" in st.session_state.mode_state and "etno_file_parts" not in st.session_state.mode_state:
        text_ctx, file_parts = load_etnochat_project_data(st.session_state.mode_state["etno_storage_path"]) 
        if text_ctx is not None:
            st.session_state.mode_state["etno_context_str"] = text_ctx
            st.session_state.mode_state["etno_file_parts"] = file_parts
        else:
            st.error("No se pudieron cargar los datos.")
            st.session_state.mode_state.pop("etno_selected_project_id", None)

    # 2. Router de Vistas
    if "etno_file_parts" in st.session_state.mode_state:
        show_etnochat_project_analyzer( 
            st.session_state.mode_state["etno_context_str"],
            st.session_state.mode_state["etno_file_parts"],
            st.session_state.mode_state["etno_selected_project_name"]
        )
    elif "etno_selected_project_id" in st.session_state.mode_state:
        st.info("Iniciando carga...")
    else:
        with st.expander("➕ Crear Nuevo Proyecto EtnoChat", expanded=True):
            show_etnochat_project_creator(user_id, project_limit, files_per_project_limit)
        st.divider()
        show_etnochat_project_list(user_id)
