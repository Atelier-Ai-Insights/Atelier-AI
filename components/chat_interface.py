import streamlit as st
import re
import time
from utils import process_text_with_tooltips
from services.supabase_db import log_message_feedback
from services.memory_service import save_project_insight

def render_chat_history(history, source_mode="chat"):
    """
    Versión Optimizada: Usa st.expander para mostrar referencias y citas,
    asegurando que siempre sean visibles sin errores de renderizado.
    """
    if not history:
        return

    for idx, msg in enumerate(history):
        role = msg["role"]
        content = msg["content"]
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # 1. Identificar si existen referencias técnicas [x]...|||
                has_ref = "|||" in content
                
                # 2. Limpieza visual: Separar el cuerpo de la respuesta de la metadata
                parts = re.split(r'\n\s*(\*\*|##)?\s*Fuentes( Verificadas| Consultadas)?\s*:?', content, flags=re.IGNORECASE)
                display_text = parts[0]
                # Limpiar posibles restos del separador técnico
                display_text = re.split(r'\[\d+\].*?\|\|\|', display_text, flags=re.DOTALL)[0]
                
                # 3. Renderizar texto con tooltips
                html_content = process_text_with_tooltips(display_text)
                st.markdown(html_content, unsafe_allow_html=True)
                
                # --- BLOQUE DE ACCIONES (REFERENCIAS Y FEEDBACK) ---
                if has_ref:
                    # Usamos un expander con diseño limpio para las fuentes
                    with st.expander("📚 Ver Referencias y Citas"):
                        # Extraer patrones: [1] Archivo ||| Cita
                        pattern = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
                        matches = re.findall(pattern, content, flags=re.DOTALL)
                        
                        for cid, fname, quote in matches:
                            # Limpieza estética del nombre del archivo
                            clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
                            clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name).replace("In-ATL_", "")
                            
                            st.markdown(f"**[{cid}] {clean_name}**")
                            st.info(f"\"{quote.strip()}\"")

                # --- ICONOS DE FEEDBACK Y PIN ---
                c1, c2, c3, c_spacer = st.columns([1, 1, 1, 10])
                k = f"{source_mode}_{idx}"
                
                with c1:
                    if st.button("👍", key=f"up_{k}"):
                        log_message_feedback(content, source_mode, "up")
                        st.toast("Feedback registrado")
                with c2:
                    if st.button("👎", key=f"down_{k}"):
                        log_message_feedback(content, source_mode, "down")
                        st.toast("Feedback registrado")
                with c3:
                    if st.button("📌", key=f"pin_{k}"):
                        if save_project_insight(content, source_mode=source_mode):
                            st.toast("✅ Guardado")
                            time.sleep(0.5)
                            st.rerun()
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """
    Maneja la interacción de forma simplificada para evitar errores de redibujado.
    """
    st.session_state.mode_state[history_key].append({"role": "user", "content": prompt})
    
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="✨"):
        full_response = ""
        placeholder = st.empty()
        stream = response_generator_func()
        
        if stream:
            for chunk in stream:
                full_response += chunk
                placeholder.markdown(full_response + "▌")
            
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            if on_generation_success:
                on_generation_success(full_response)
            
            # Recarga para procesar el contenido con el expander y los iconos
            st.rerun()
            return full_response
