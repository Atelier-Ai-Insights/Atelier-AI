import streamlit as st
from utils import get_relevant_info, render_process_status, process_text_with_tooltips # <--- IMPORTANTE
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_ideation_prompt
import constants as c

def ideacion_mode(db, selected_files):
    st.subheader("💡 Ideación Estratégica")
    st.caption("Brainstorming creativo fundamentado en datos del repositorio.")

    if not selected_files:
        st.info("Selecciona documentos para comenzar.")
        return

    # Inicializar historial si no existe
    if "ideation_history" not in st.session_state.mode_state:
        st.session_state.mode_state["ideation_history"] = []

    # Mostrar Historial
    for msg in st.session_state.mode_state["ideation_history"]:
        with st.chat_message(msg["role"], avatar="✨" if msg["role"]=="assistant" else "👤"):
            if msg["role"] == "assistant":
                # Aplicamos Tooltips al historial
                st.markdown(process_text_with_tooltips(msg["content"]), unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])

    # Input
    user_input = st.chat_input("Escribe un desafío creativo...")
    
    if user_input:
        # Guardar User Msg
        st.session_state.mode_state["ideation_history"].append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar="✨"):
            with render_process_status("Conectando puntos...", expanded=False):
                relevant_info = get_relevant_info(db, user_input, selected_files)
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["ideation_history"][-5:]])
                prompt = get_ideation_prompt(hist_str, relevant_info)
                response = call_gemini_api(prompt)
            
            if response:
                # Renderizar con Tooltips
                enriched_html = process_text_with_tooltips(response)
                st.markdown(enriched_html, unsafe_allow_html=True)
                
                st.session_state.mode_state["ideation_history"].append({"role": "assistant", "content": response})
                log_query_event(f"Ideación: {user_input}", mode=c.MODE_IDEATION)
