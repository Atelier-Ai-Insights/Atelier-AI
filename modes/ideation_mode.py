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
    for msg in st.session_state.mode_state["ideation_history"]:
        with st.chat_message(msg["role"], avatar="✨" if msg["role"]=="assistant" else "👤"):
            if msg["role"] == "assistant":
                st.markdown(process_text_with_tooltips(msg["content"]), unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])

    # 2. INPUT FIJO ABAJO (AJUSTE 1)
    user_input = st.chat_input("Escribe un desafío creativo...")
    
    if user_input:
        # A. Mostrar mensaje usuario
        st.session_state.mode_state["ideation_history"].append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # B. Generar respuesta
        with st.chat_message("assistant", avatar="✨"):
            response = None
            
            with render_process_status("Conectando puntos...", expanded=True) as status:
                relevant_info = get_relevant_info(db, user_input, selected_files)
                
                # Contexto breve de últimos mensajes
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["ideation_history"][-3:]])
                
                prompt = get_ideation_prompt(hist_str, relevant_info)
                response = call_gemini_api(prompt)
                
                if response:
                    status.update(label="¡Ideas generadas!", state="complete", expanded=False)
                else:
                    status.update(label="Error al generar", state="error")

            # C. Mostrar respuesta final
            if response:
                enriched_html = process_text_with_tooltips(response)
                st.markdown(enriched_html, unsafe_allow_html=True)
                
                st.session_state.mode_state["ideation_history"].append({"role": "assistant", "content": response})
                
                try:
                    log_query_event(f"Ideación: {user_input[:50]}", mode=c.MODE_IDEATION)
                except: pass

    # 3. BOTONES DE ACCIÓN (AJUSTES 2 y 3)
    if st.session_state.mode_state["ideation_history"]:
        # AJUSTE 2: Quitamos st.divider() para evitar la "doble línea" visual
        st.write("") 
        
        # Generar PDF
        full_chat_text = ""
        for m in st.session_state.mode_state["ideation_history"]:
            role_title = "Usuario" if m["role"] == "user" else "Atelier AI"
            full_chat_text += f"**{role_title}:**\n{m['content']}\n\n"
        
        pdf_bytes = generate_pdf_html(full_chat_text, title="Sesión de Ideación", banner_path=banner_file)
        
        # AJUSTE 3: Columnas iguales y botones full-width
        col1, col2 = st.columns(2)
        
        with col1:
            if pdf_bytes:
                st.download_button(
                    label="Descargar PDF",
                    data=pdf_bytes,
                    file_name="Ideacion_Creativa.pdf",
                    mime="application/pdf",
                    type="secondary",
                    use_container_width=True # Ancho completo
                )
        with col2:
            if st.button("Nueva Búsqueda", type="secondary", use_container_width=True): # Ancho completo
                st.session_state.mode_state["ideation_history"] = []
                st.rerun()
