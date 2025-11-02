import streamlit as st
import docx
from io import BytesIO
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_transcript_prompt

# =====================================================
# MODO: ANÁLISIS DE TRANSCRIPCIONES
# =====================================================

def transcript_analysis_mode():
    st.subheader("Análisis de Notas y Transcripciones")
    file_limit = st.session_state.plan_features.get('transcript_file_limit', 0)
    
    st.markdown(f"""
        Sube uno o varios archivos Word con notas y transcripciones...
        **Tu plan actual te permite cargar un máximo de {file_limit} archivo(s) a la vez.**
    """)
    
    # --- Lógica de feedback eliminada ---
    
    # --- Sección de Carga y Procesamiento de Archivos ---
    uploaded_files = st.file_uploader(
        "Sube tus archivos .docx aquí:",
        type=["docx"],
        accept_multiple_files=True,
        key="transcript_uploader"
    )

    if uploaded_files:
        if len(uploaded_files) > file_limit:
            st.error(f"¡Límite de archivos excedido! Tu plan permite {file_limit}..."); return
            
    if 'uploaded_transcripts_text' not in st.session_state: st.session_state.uploaded_transcripts_text = {} 
    if 'transcript_chat_history' not in st.session_state: st.session_state.transcript_chat_history = []

    if uploaded_files:
        # ... (Lógica de procesamiento de archivos sin cambios) ...
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
        st.write("**Archivos cargados para análisis:**"); [st.caption(f"- {filename}") for filename in st.session_state.uploaded_transcripts_text.keys()]; st.markdown("---")
    else:
        st.info("Sube uno o más archivos .docx para comenzar a chatear.")

    st.write("**Chat con Transcripciones:**")

    # --- Bucle de visualización REVERTIDO ---
    for msg in st.session_state.transcript_chat_history:
        with st.chat_message(msg["role"], avatar="✨" if msg['role'] == "assistant" else "👤"):
            st.markdown(msg["content"])
            # Se eliminó la llamada a st.feedback()

    user_prompt = st.chat_input("Haz una pregunta sobre las transcripciones...")

    if user_prompt:
        st.session_state.transcript_chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_prompt)

        if not st.session_state.uploaded_transcripts_text:
            st.error("No hay transcripciones cargadas..."); st.session_state.transcript_chat_history.pop(); return

        with st.chat_message("assistant", avatar="✨"):
            message_placeholder = st.empty(); message_placeholder.markdown("Analizando...")
            combined_context = "\n\n".join(f"**Archivo: {name}**\n\n{text}" for name, text in st.session_state.uploaded_transcripts_text.items())
            
            MAX_CONTEXT_LENGTH = 800000 
            if len(combined_context) > MAX_CONTEXT_LENGTH:
                combined_context = combined_context[:MAX_CONTEXT_LENGTH] + "\n\n...(contexto truncado)..."
                st.warning("Contexto truncado.", icon="⚠️")
                
            chat_prompt = get_transcript_prompt(combined_context, user_prompt)
            response = call_gemini_api(chat_prompt) 

            if response:
                message_placeholder.markdown(response)
                # --- Lógica de guardado REVERTIDA ---
                log_query_event(user_prompt, mode="Análisis de Transcripciones")
                st.session_state.transcript_chat_history.append({
                    "role": "assistant", 
                    "content": response
                    # Ya no se guarda el query_id
                })
                st.rerun() # Se mantiene el rerun
            else:
                message_placeholder.error("Error al obtener respuesta."); st.session_state.transcript_chat_history.pop()

    if st.session_state.uploaded_transcripts_text or st.session_state.transcript_chat_history:
        if st.button("Limpiar Archivos y Chat", use_container_width=True, type="secondary"):
            st.session_state.uploaded_transcripts_text = {}; st.session_state.transcript_chat_history = []; st.rerun()