import streamlit as st
import docx
from io import BytesIO
from services.gemini_api import call_gemini_api
# --- ¡IMPORTACIÓN ACTUALIZADA! ---
from services.supabase_db import log_query_event, log_query_feedback
from prompts import get_transcript_prompt

# =====================================================
# MODO: ANÁLISIS DE TRANSCRIPCIONES
# =====================================================

def transcript_analysis_mode():
    st.subheader("Análisis de Notas y Transcripciones")
    file_limit = st.session_state.plan_features.get('transcript_file_limit', 0)
    
    st.markdown(f"""
        Sube uno o varios archivos Word con notas y transcripciones de entrevistas o
        focus groups. Luego, haz preguntas sobre el contenido en el chat.
        
        **Tu plan actual te permite cargar un máximo de {file_limit} archivo(s) a la vez.**
    """)
    
    # --- FUNCIÓN DE CALLBACK PARA EL FEEDBACK ---
    def transcript_feedback_callback(feedback, query_id):
        if query_id:
            # Usar .get() para seguridad y score=0 para 'thumbs_down'
            score = 1 if feedback.get('score') == 'thumbs_up' else 0
            log_query_feedback(query_id, score)
            st.toast("¡Gracias por tu feedback!")
        else:
            st.toast("Error: No se encontró el ID de la consulta.")
    # --- FIN DEL CALLBACK ---
    
    # --- Sección de Carga y Procesamiento de Archivos ---
    uploaded_files = st.file_uploader(
        "Sube tus archivos .docx aquí:",
        type=["docx"],
        accept_multiple_files=True,
        key="transcript_uploader"
    )

    if uploaded_files:
        if len(uploaded_files) > file_limit:
            st.error(f"¡Límite de archivos excedido! Tu plan permite {file_limit} archivo(s), pero has subido {len(uploaded_files)}. Por favor, deselecciona los archivos sobrantes.")
            return
            
    if 'uploaded_transcripts_text' not in st.session_state:
        st.session_state.uploaded_transcripts_text = {} 
    if 'transcript_chat_history' not in st.session_state:
        st.session_state.transcript_chat_history = []

    if uploaded_files:
        newly_processed = False
        with st.spinner("Procesando archivos .docx..."):
            current_texts = {}
            for uploaded_file in uploaded_files:
                file_stream = BytesIO(uploaded_file.getvalue())
                try:
                    document = docx.Document(file_stream)
                    full_text = "\n".join([para.text for para in document.paragraphs if para.text.strip()])
                    current_texts[uploaded_file.name] = full_text
                    if uploaded_file.name not in st.session_state.uploaded_transcripts_text or st.session_state.uploaded_transcripts_text.get(uploaded_file.name) != full_text:
                        newly_processed = True
                except Exception as e:
                    st.error(f"Error al procesar '{uploaded_file.name}': {e}")

            if newly_processed or set(current_texts.keys()) != set(st.session_state.uploaded_transcripts_text.keys()):
                st.session_state.uploaded_transcripts_text = current_texts
                st.session_state.transcript_chat_history = [] 
                st.info(f"Se procesaron {len(current_texts)} archivo(s). El chat se ha reiniciado.")

    if st.session_state.uploaded_transcripts_text:
        st.write("**Archivos cargados para análisis:**")
        for filename in st.session_state.uploaded_transcripts_text.keys():
            st.caption(f"- {filename}")
        st.markdown("---")
    else:
        st.info("Sube uno o más archivos .docx para comenzar a chatear.")

    # --- Sección de Chat ---
    st.write("**Chat con Transcripciones:**")

    # --- BUCLE DE VISUALIZACIÓN DE CHAT (MODIFICADO) ---
    for msg in st.session_state.transcript_chat_history:
        if msg['role'] == "assistant":
            with st.chat_message("assistant", avatar="✨"):
                st.markdown(msg["content"])
                # Añadir widget de feedback
                if msg.get('query_id'):
                    st.feedback(
                        key=f"feedback_transcript_{msg['query_id']}", # Key única
                        on_submit=transcript_feedback_callback,
                        args=(msg.get('query_id'),) # Pasar el query_id
                    )
        else: # role == "user"
            with st.chat_message("user", avatar="👤"):
                st.markdown(msg["content"])

    # Input del usuario
    user_prompt = st.chat_input("Haz una pregunta sobre las transcripciones...")

    if user_prompt:
        st.session_state.transcript_chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        if not st.session_state.uploaded_transcripts_text:
            st.error("No hay transcripciones cargadas para analizar. Por favor, sube archivos .docx.")
            st.session_state.transcript_chat_history.pop()
            return

        with st.chat_message("assistant", avatar="✨"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Analizando transcripciones...")

            combined_context = "\n\n--- Nueva Transcripción ---\n\n".join(
                f"**Archivo: {name}**\n\n{text}"
                for name, text in st.session_state.uploaded_transcripts_text.items()
            )

            MAX_CONTEXT_LENGTH = 800000 
            if len(combined_context) > MAX_CONTEXT_LENGTH:
                combined_context = combined_context[:MAX_CONTEXT_LENGTH] + "\n\n...(contexto truncado)..."
                st.warning("El contexto combinado de las transcripciones es muy largo y ha sido truncado.", icon="⚠️")

            chat_prompt = get_transcript_prompt(combined_context, user_prompt)

            response = call_gemini_api(chat_prompt) 

            if response:
                message_placeholder.markdown(response)
                # --- ¡CAMBIO AQUÍ! ---
                # 1. Loguear la consulta y obtener el ID
                query_id = log_query_event(user_prompt, mode="Análisis de Transcripciones")
                # 2. Guardar el ID con el mensaje
                st.session_state.transcript_chat_history.append({
                    "role": "assistant", 
                    "content": response,
                    "query_id": query_id
                })
                # --- FIN DEL CAMBIO ---
            else:
                message_placeholder.error("Error al obtener respuesta del análisis.")
                st.session_state.transcript_chat_history.pop()

    if st.session_state.uploaded_transcripts_text or st.session_state.transcript_chat_history:
        if st.button("Limpiar Archivos y Chat", use_container_width=True, type="secondary"):
            st.session_state.uploaded_transcripts_text = {}
            st.session_state.transcript_chat_history = []
            st.rerun()