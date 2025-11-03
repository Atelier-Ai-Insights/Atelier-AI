import streamlit as st
import docx
from io import BytesIO
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_transcript_prompt, get_autocode_prompt
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: ANÁLISIS DE TEXTOS (CUALI)
# =====================================================

@st.cache_data
def process_text_files(uploaded_files_list):
    """
    Lee una lista de archivos docx y devuelve un dict {nombre: texto}
    y una cadena de texto combinada para los prompts.
    """
    combined_context = "" # Para el prompt de autocode
    file_texts_dict = {}  # Para el chat de transcripción
    
    for uploaded_file in uploaded_files_list:
        file_stream = BytesIO(uploaded_file.getvalue())
        try:
            document = docx.Document(file_stream)
            full_text = "\n".join([para.text for para in document.paragraphs if para.text.strip()])
            
            # Para el autocode (un solo bloque de texto)
            combined_context += f"\n\n--- INICIO DOCUMENTO: {uploaded_file.name} ---\n\n{full_text}\n\n--- FIN DOCUMENTO: {uploaded_file.name} ---\n"
            
            # Para el chat (dict separado)
            file_texts_dict[uploaded_file.name] = full_text
            
        except Exception as e:
            st.error(f"Error al procesar '{uploaded_file.name}': {e}")
    
    return file_texts_dict, combined_context

# --- Función Principal del Modo ---

def text_analysis_mode():
    st.subheader(c.MODE_TEXT_ANALYSIS) # <-- Esto tomará el nuevo nombre
    file_limit = st.session_state.plan_features.get('transcript_file_limit', 0)
    
    st.markdown(f"""
        Sube uno o varios archivos Word (.docx) con entrevistas o focus groups.
        **Tu plan actual te permite cargar un máximo de {file_limit} archivo(s) a la vez.**
    """)

    uploaded_files = st.file_uploader(
        "Sube tus archivos .docx aquí:",
        type=["docx"],
        accept_multiple_files=True,
        key="text_analysis_uploader"
    )

    if uploaded_files:
        if len(uploaded_files) > file_limit:
            st.error(f"¡Límite de archivos excedido! Tu plan permite {file_limit}..."); return

        # Procesar archivos y guardar en session_state si son nuevos
        current_file_names = {f.name for f in uploaded_files}
        if "text_analysis_file_names" not in st.session_state or st.session_state.text_analysis_file_names != current_file_names:
            with st.spinner(f"Procesando {len(uploaded_files)} archivo(s)..."):
                file_texts_dict, combined_context = process_text_files(uploaded_files)
                st.session_state.text_analysis_files_dict = file_texts_dict
                st.session_state.text_analysis_combined_context = combined_context
                st.session_state.text_analysis_file_names = current_file_names
                # Reiniciar los sub-modos
                st.session_state.pop("transcript_chat_history", None)
                st.session_state.pop("autocode_result", None)
            st.success(f"Se procesaron {len(current_file_names)} archivo(s).")
    
    # Si no hay archivos, no mostrar nada más
    if "text_analysis_files_dict" not in st.session_state or not st.session_state.text_analysis_files_dict:
        st.info("Sube uno o más archivos .docx para comenzar.")
        return

    st.markdown("---")
    st.write("**Archivos cargados para análisis:**")
    for filename in st.session_state.text_analysis_files_dict.keys():
        st.caption(f"- {filename}")
    st.markdown("---")
    
    # --- INICIO DE LA MODIFICACIÓN (Nombres de Pestañas) ---
    tab_chat, tab_autocode = st.tabs(["Análisis de Notas y Transcripciones", "Auto-Codificación"])
    # --- FIN DE LA MODIFICACIÓN ---

    # --- PESTAÑA 1: CHAT DE TRANSCRIPCIONES ---
    with tab_chat:
        st.header("Análisis de Notas y Transcripciones") # <-- Título modificado
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
                
                combined_context = st.session_state.text_analysis_combined_context
                
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

    # --- PESTAÑA 2: AUTO-CODIFICACIÓN ---
    with tab_autocode:
        st.header("Auto-Codificación") # <-- Título modificado
        
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
                        
                        combined_context = st.session_state.text_analysis_combined_context
                        
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