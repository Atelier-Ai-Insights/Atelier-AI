import streamlit as st
import docx
import io
import os  
import uuid
from datetime import datetime
import re 
from PIL import Image
import fitz # PyMuPDF
import gc # <--- NUEVO: Garbage Collector para gestión de memoria

# --- IMPORTACIONES SERVICIOS ---
try:
    from services.gemini_api import call_gemini_api, call_gemini_stream 
    gemini_available = True
except ImportError:
    gemini_available = False
    def call_gemini_stream(p): return None
    def call_gemini_api(p, generation_config_override=None): return None

from services.supabase_db import log_query_event, supabase, get_daily_usage
from prompts import get_etnochat_prompt, get_media_transcription_prompt 
import constants as c
from config import banner_file
from utils import reset_etnochat_chat_workflow, render_process_status

# --- IMPORTACIONES UI UNIFICADA ---
from components.chat_interface import render_chat_history, handle_chat_interaction

# --- GENERADORES ---
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx

# =====================================================
# MODO: ANÁLISIS DE ETNOCHAT (OPTIMIZADO V2)
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

# --- Funciones de Carga de Datos (Optimized Memory Usage) ---

@st.cache_data(ttl=600, show_spinner=False)
def load_etnochat_project_data(storage_folder_path: str):
    """
    Descarga archivos con gestión estricta de memoria.
    Prioriza transcripciones existentes para evitar descargas pesadas.
    """
    if not storage_folder_path:
        st.error("Error: Ruta de proyecto vacía.")
        return None, None
        
    text_context_parts = []
    file_parts = [] # Solo imágenes
    
    try:
        # 1. Listar archivos
        files_list = supabase.storage.from_(ETNOCHAT_BUCKET).list(storage_folder_path)
        if not files_list:
            st.warning("El proyecto está vacío.")
            return "", []

        # Mapa de archivos existentes para búsqueda rápida O(1)
        existing_filenames = {f['name'] for f in files_list}

        st.write(f"Procesando {len(files_list)} archivo(s)...")
        progress_bar = st.progress(0)
        total_files = len(files_list)

        for i, file_info in enumerate(files_list):
            file_name = file_info['name']
            
            # Si es un archivo de transcripción, lo saltamos aquí (se carga asociado a su media o solo)
            # Pero si es un txt suelto que NO es transcripción automática, lo procesamos.
            if file_name.endswith("_transcript.txt"):
                # Verificamos si es huérfano (si no existe el audio original)
                original_media = file_name.replace("_transcript.txt", "")
                has_original = any(original_media in f for f in existing_filenames)
                if has_original:
                    progress_bar.progress((i + 1) / total_files)
                    continue 

            full_file_path = f"{storage_folder_path}/{file_name}"
            file_ext = os.path.splitext(file_name)[1].lower()
            
            try:
                # --- LÓGICA DE AUDIO/VIDEO (OPTIMIZACIÓN MAYOR) ---
                if file_ext in MIME_TYPES and ("audio" in MIME_TYPES[file_ext] or "video" in MIME_TYPES[file_ext]):
                    transcript_filename = f"{file_name}_transcript.txt"
                    transcript_full_path = f"{storage_folder_path}/{transcript_filename}"
                    
                    # 1. ¿Existe ya la transcripción?
                    if transcript_filename in existing_filenames:
                        # ¡OPTIMIZACIÓN! Descargamos SOLO el TXT (Kb), no el Video (Mb/Gb)
                        trans_bytes = supabase.storage.from_(ETNOCHAT_BUCKET).download(transcript_full_path)
                        transcript_text = trans_bytes.decode('utf-8')
                        text_context_parts.append(f"\n\n--- TRANSCRIPCIÓN DE {file_name} ---\n{transcript_text}\n")
                        
                        # Liberar memoria explícitamente
                        del trans_bytes
                        gc.collect()
                        
                    else:
                        # 2. No existe, toca descargar y transcribir (Costoso pero necesario una vez)
                        with st.spinner(f"Transcribiendo {file_name}... (Esto tomará unos segundos)"):
                            response_bytes = supabase.storage.from_(ETNOCHAT_BUCKET).download(full_file_path)
                            media_data = {"mime_type": MIME_TYPES[file_ext], "data": response_bytes}
                            prompt_transcribe = get_media_transcription_prompt()
                            
                            generated_transcript = call_gemini_api([prompt_transcribe, media_data], generation_config_override={"max_output_tokens": 8192})
                            
                            if generated_transcript:
                                text_context_parts.append(f"\n\n--- TRANSCRIPCIÓN AUTOMÁTICA DE {file_name} ---\n{generated_transcript}\n")
                                # Guardar para el futuro
                                try:
                                    supabase.storage.from_(ETNOCHAT_BUCKET).upload(
                                        path=transcript_full_path,
                                        file=generated_transcript.encode('utf-8'),
                                        file_options={"content-type": "text/plain"}
                                    )
                                except: pass
                            
                            # LIMPIEZA CRÍTICA DE MEMORIA
                            del response_bytes
                            del media_data
                            gc.collect()

                # --- LÓGICA DE IMÁGENES ---
                elif file_ext in [".jpg", ".jpeg", ".png"]:
                    # Descargamos
                    response_bytes = supabase.storage.from_(ETNOCHAT_BUCKET).download(full_file_path)
                    file_stream = io.BytesIO(response_bytes)
                    img = Image.open(file_stream)
                    file_parts.append(img)
                    text_context_parts.append(f"[Imagen cargada: {file_name}]")
                    # No borramos img porque se necesita para el prompt, pero borramos el buffer binario
                    del response_bytes
                    gc.collect()

                # --- DOCUMENTOS DE TEXTO ---
                else:
                    response_bytes = supabase.storage.from_(ETNOCHAT_BUCKET).download(full_file_path)
                    file_stream = io.BytesIO(response_bytes)
                    
                    header = f"\n\n--- DOC: {file_name} ---\n"
                    footer = "\n----------------------\n"
                    
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
                    
                    del response_bytes
                    del file_stream
                    gc.collect()

            except Exception as e_file:
                st.warning(f"Saltando archivo '{file_name}': {e_file}")
                continue
            
            progress_bar.progress((i + 1) / total_files)
        
        progress_bar.empty()
        combined_text_context = "\n".join(text_context_parts)
        return combined_text_context, file_parts
        
    except Exception as e:
        st.error(f"Error crítico cargando proyecto: {e}")
        return None, None

# --- Funciones de UI ---

def show_etnochat_project_creator(user_id, project_limit, files_per_project_limit):
    st.subheader("Crear Nuevo Proyecto")
    
    # Validar Límites
    try:
        response = supabase.table("etnochat_projects").select("id", count='exact').eq("user_id", user_id).execute()
        if response.count >= project_limit and project_limit != float('inf'):
            st.warning(f"Límite de proyectos alcanzado ({int(project_limit)}).")
            return
    except: pass

    with st.form("new_etnochat_project_form"):
        project_name = st.text_input("Nombre del Proyecto*", placeholder="Ej: Etnografía Cocinas Cali")
        project_brand = st.text_input("Marca*", placeholder="Ej: Marca Y")
        project_year = st.number_input("Año*", min_value=2020, max_value=2030, value=datetime.now().year)
        
        uploaded_files = st.file_uploader(
            "Cargar Archivos Multimedia*",
            type=[ext.lstrip('.') for ext in ALLOWED_EXTENSIONS],
            accept_multiple_files=True
        )
        
        if st.form_submit_button("Crear Proyecto"):
            if not all([project_name, project_brand, uploaded_files]):
                st.warning("Completa los campos obligatorios.")
                return

            if len(uploaded_files) > files_per_project_limit and files_per_project_limit != float('inf'):
                st.error(f"Demasiados archivos. Máximo: {int(files_per_project_limit)}.")
                return

            project_storage_folder = f"{user_id}/{uuid.uuid4()}" 
            
            with render_process_status("Subiendo archivos...", expanded=True) as status:
                try:
                    for idx, uploaded_file in enumerate(uploaded_files): 
                        status.write(f"Subiendo {idx+1}/{len(uploaded_files)}: {uploaded_file.name}")
                        
                        base_name = uploaded_file.name.replace(' ', '_')
                        safe_name = re.sub(r'[^\w._-]', '', base_name)
                        file_ext = os.path.splitext(safe_name)[1].lower()
                        
                        if not safe_name: safe_name = f"file_{uuid.uuid4()}{file_ext}"
                        
                        path = f"{project_storage_folder}/{safe_name}"
                        
                        # Subida optimizada
                        file_bytes = uploaded_file.getvalue()
                        supabase.storage.from_(ETNOCHAT_BUCKET).upload(
                            path=path,
                            file=file_bytes,
                            file_options={"content-type": MIME_TYPES.get(file_ext, "application/octet-stream")}
                        )
                        
                        # Liberar memoria local
                        del file_bytes
                        gc.collect()

                    supabase.table("etnochat_projects").insert({
                        "project_name": project_name,
                        "project_brand": project_brand,
                        "project_year": int(project_year),
                        "storage_path": project_storage_folder, 
                        "user_id": user_id
                    }).execute()
                    
                    status.update(label="¡Proyecto Creado!", state="complete", expanded=False)
                    st.success("Proyecto creado exitosamente.")
                    st.rerun()

                except Exception as e:
                    status.update(label="Error", state="error")
                    st.error(f"Error: {e}")

def show_etnochat_project_list(user_id):
    st.subheader("Mis Proyectos EtnoChat")
    try:
        response = supabase.table("etnochat_projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        if not response.data: st.info("No hay proyectos."); return

        for proj in response.data:
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.markdown(f"**{proj['project_name']}**\n<span style='color:grey; font-size:0.8em'>{proj.get('project_brand')} | {proj.get('project_year')}</span>", unsafe_allow_html=True)
                
                if c2.button("Analizar", key=f"btn_analizar_{proj['id']}", width='stretch', type="primary"):
                    st.session_state.mode_state.update({
                        "etno_selected_project_id": proj['id'],
                        "etno_selected_project_name": proj['project_name'],
                        "etno_storage_path": proj['storage_path']
                    })
                    st.rerun()
                    
                if c3.button("Borrar", key=f"btn_borrar_{proj['id']}", width='stretch'):
                    try:
                        # Limpieza profunda en Storage
                        if proj['storage_path']:
                            files = supabase.storage.from_(ETNOCHAT_BUCKET).list(proj['storage_path'])
                            if files:
                                paths = [f"{proj['storage_path']}/{f['name']}" for f in files]
                                supabase.storage.from_(ETNOCHAT_BUCKET).remove(paths)
                        
                        supabase.table("etnochat_projects").delete().eq("id", proj['id']).execute()
                        st.success("Eliminado.")
                        st.rerun()
                    except Exception as e: st.error(f"Error eliminando: {e}")
    except: st.error("Error cargando lista.")

# --- ANALIZADOR PRINCIPAL (UI UNIFICADA) ---

def show_etnochat_project_analyzer(text_context, file_parts, project_name):
    st.markdown(f"### Analizando: **{project_name}**")
    if st.button("← Volver"): 
        st.session_state.mode_state = {}
        st.rerun()
        
    st.divider()
    
    # 1. INICIALIZAR HISTORIAL
    if "etno_chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["etno_chat_history"] = []

    # 2. RENDERIZAR HISTORIAL (Componente Unificado)
    render_chat_history(st.session_state.mode_state["etno_chat_history"], source_mode="etnochat")

    # 3. INTERACCIÓN USUARIO
    if user_prompt := st.chat_input("Haz una pregunta sobre los archivos multimedia..."):
        
        # Validación de Cuota Diaria
        limit = st.session_state.plan_features.get('etnochat_questions_per_day', 5)
        usage = get_daily_usage(st.session_state.user, c.MODE_ETNOCHAT)
        if usage >= limit and limit != float('inf'):
            st.error("Límite diario de preguntas alcanzado.")
            return

        # Generador Específico Multimodal
        def etnochat_generator():
            with st.status("Analizando multimodal...", expanded=True) as status:
                status.write("Procesando contexto visual y textual...")
                
                # Contexto Histórico
                history_str = "\n".join(f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["etno_chat_history"][-6:])
                
                # Prompt Compuesto
                prompt_text = get_etnochat_prompt(history_str, text_context)
                
                # Payload: Texto Prompt + Imágenes (file_parts)
                # Nota: Gemini procesa texto e imágenes en la misma lista
                final_payload = [prompt_text] + file_parts + [f"\nUsuario: {user_prompt}"]
                
                status.write("Consultando motor Gemini...")
                stream = call_gemini_stream(final_payload)
                
                if stream:
                    status.update(label="Respuesta generada", state="complete", expanded=False)
                    return stream
                else:
                    status.update(label="Error", state="error")
                    return iter(["Error al procesar la solicitud multimodal."])

        # Delegar al componente visual
        handle_chat_interaction(
            prompt=user_prompt,
            response_generator_func=etnochat_generator,
            history_key="etno_chat_history",
            source_mode="etnochat",
            on_generation_success=lambda r: log_query_event(user_prompt, mode=c.MODE_ETNOCHAT)
        )

    # 4. EXPORTACIÓN
    if st.session_state.mode_state["etno_chat_history"]:
        st.divider()
        c1, c2, c3 = st.columns(3)
        
        # Preparamos el texto plano para los reportes
        raw_text = f"# Reporte EtnoChat: {project_name}\n\n"
        raw_text += "\n\n".join(f"**{m['role'].upper()}:** {m['content']}" for m in st.session_state.mode_state["etno_chat_history"])
        
        with c1:
            pdf = generate_pdf_html(raw_text.replace("](#)", "]"), title=f"EtnoChat - {project_name}", banner_path=banner_file)
            if pdf: st.download_button("Descargar PDF", data=pdf, file_name="etno_reporte.pdf", mime="application/pdf", width='stretch')
        
        with c2:
            docx = generate_docx(raw_text, title=f"EtnoChat - {project_name}")
            if docx: st.download_button("Descargar Word", data=docx, file_name="etno_reporte.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width='stretch', type="primary")

        with c3: 
            st.button("Reiniciar", on_click=reset_etnochat_chat_workflow, key="rst_etno", width='stretch')

# --- FUNCIÓN PRINCIPAL DEL MODO ---

def etnochat_mode():
    st.subheader(c.MODE_ETNOCHAT)
    st.markdown("Carga y analiza conversaciones de WhatsApp, audios, imágenes y videos.")
    st.divider()

    user_id = st.session_state.user_id
    project_limit = st.session_state.plan_features.get('etnochat_project_limit', 0)
    files_limit = st.session_state.plan_features.get('etnochat_max_files_per_project', 0)

    # 1. Cargar datos (si aplica)
    if "etno_selected_project_id" in st.session_state.mode_state and "etno_file_parts" not in st.session_state.mode_state:
        with render_process_status("Cargando proyecto (optimizando memoria)...", expanded=True) as status:
            text_ctx, file_parts = load_etnochat_project_data(st.session_state.mode_state["etno_storage_path"]) 
            status.update(label="Carga completa", state="complete", expanded=False)

        if text_ctx is not None:
            st.session_state.mode_state["etno_context_str"] = text_ctx
            st.session_state.mode_state["etno_file_parts"] = file_parts
        else:
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
        with st.expander("➕ Crear Nuevo Proyecto", expanded=True):
            show_etnochat_project_creator(user_id, project_limit, files_limit)
        st.divider()
        show_etnochat_project_list(user_id)
