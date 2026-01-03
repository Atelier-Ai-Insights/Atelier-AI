import streamlit as st
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_ideation_prompt
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
import constants as c

def ideacion_mode(db, selected_files):
    st.subheader("Ideación Estratégica")
    st.caption("Brainstorming creativo fundamentado en datos del repositorio.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # Inicializar historial si no existe
    if "ideation_history" not in st.session_state.mode_state:
        st.session_state.mode_state["ideation_history"] = []

    # 1. MOSTRAR HISTORIAL
    # Recorremos el historial para mostrar mensajes anteriores
    for msg in st.session_state.mode_state["ideation_history"]:
        with st.chat_message(msg["role"], avatar="✨" if msg["role"]=="assistant" else "👤"):
            if msg["role"] == "assistant":
                # Renderizamos con tooltips lo que ya está en memoria
                st.markdown(process_text_with_tooltips(msg["content"]), unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])

    # 2. INPUT DEL USUARIO
    user_input = st.chat_input("Escribe un desafío creativo...")
    
    if user_input:
        # A. Mostrar mensaje usuario
        st.session_state.mode_state["ideation_history"].append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # B. Generar respuesta
        with st.chat_message("assistant", avatar="✨"):
            response = None
            
            # Usamos el status context manager, pero guardamos la referencia 'status'
            with render_process_status("Conectando puntos...", expanded=True) as status:
                relevant_info = get_relevant_info(db, user_input, selected_files)
                
                # Construimos un historial breve para contexto (últimos 3 mensajes)
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["ideation_history"][-3:]])
                
                prompt = get_ideation_prompt(hist_str, relevant_info)
                response = call_gemini_api(prompt)
                
                # --- CORRECCIÓN CLAVE: ACTUALIZAR ESTADO AL TERMINAR ---
                if response:
                    status.update(label="¡Ideas generadas!", state="complete", expanded=False)
                else:
                    status.update(label="Error al generar", state="error")

            # C. Mostrar respuesta final
            if response:
                # Procesamos Tooltips
                enriched_html = process_text_with_tooltips(response)
                st.markdown(enriched_html, unsafe_allow_html=True)
                
                # Guardar en historial
                st.session_state.mode_state["ideation_history"].append({"role": "assistant", "content": response})
                
                # Log
                try:
                    log_query_event(f"Ideación: {user_input[:50]}", mode=c.MODE_IDEATION)
                except: pass

    # 3. BOTÓN DE DESCARGA (NUEVO)
    # Si hay historial, mostramos opción de descargar
    if st.session_state.mode_state["ideation_history"]:
        st.divider()
        
        # Convertimos el historial a texto plano para el PDF
        full_chat_text = ""
        for m in st.session_state.mode_state["ideation_history"]:
            role_title = "Usuario" if m["role"] == "user" else "Atelier AI"
            full_chat_text += f"**{role_title}:**\n{m['content']}\n\n"
        
        pdf_bytes = generate_pdf_html(full_chat_text, title="Sesión de Ideación", banner_path=banner_file)
        
        if pdf_bytes:
            col1, col2 = st.columns([1, 4])
            with col1:
                st.download_button(
                    label="Descargar Sesión",
                    data=pdf_bytes,
                    file_name="Ideacion_Creativa.pdf",
                    mime="application/pdf",
                    type="secondary",
                    use_container_width=True
                )
            with col2:
                if st.button("Nueva Sesión", type="secondary"):
                    st.session_state.mode_state["ideation_history"] = []
                    st.rerun()
