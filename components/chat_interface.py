import streamlit as st
import re
import html
from utils import process_text_with_tooltips

# --- VENTANA EMERGENTE DE FUENTES ---
@st.dialog("Fuentes y Evidencia")
def show_sources_dialog(content):
    """
    Extrae la metadata oculta y la muestra de forma estructurada en un modal.
    """
    # Buscamos el patrón: [1] Nombre.pdf ||| Cita: "..."
    pattern = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
    matches = re.findall(pattern, content, flags=re.DOTALL)
    
    if not matches:
        st.write("No hay citas detalladas para esta respuesta.")
        return

    for cid, fname, quote in matches:
        with st.container(border=True):
            # Limpiamos el nombre como en utils.py
            clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
            clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name).replace("In-ATL_", "")
            
            st.markdown(f"**[{cid}] {clean_name}**")
            st.caption(f"Evidencia detectada:")
            st.info(quote.strip().strip('"'))

def render_chat_history(history, source_mode="chat"):
    if not history:
        return

    for idx, msg in enumerate(history):
        role = msg["role"]
        content = msg["content"]
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # 1. Limpieza visual total: cortamos TODO lo que venga después del cuerpo del mensaje
                # Buscamos donde empiezan las fuentes verificadas o los metadatos técnicos
                display_text = re.split(r'\n\s*(\*\*|##)?\s*Fuentes( Verificadas| Consultadas)?\s*:?', content, flags=re.IGNORECASE)[0]
                # También cortamos si detectamos el separador técnico directamente
                display_text = re.split(r'\[\d+\].*?\|\|\|', display_text, flags=re.DOTALL)[0]
                
                html_content = process_text_with_tooltips(display_text)
                st.markdown(html_content, unsafe_allow_html=True)
                
                # 2. Botón para abrir el modal de fuentes
                # Solo lo mostramos si el contenido original tiene el separador técnico |||
                if "|||" in content:
                    if st.button("Ver Fuentes y Citas", key=f"src_btn_{source_mode}_{idx}", icon="📖"):
                        show_sources_dialog(content)
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
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
            
            # Al finalizar, renderizamos limpio
            display_text = re.split(r'\n\s*(\*\*|##)?\s*Fuentes( Verificadas| Consultadas)?\s*:?', full_response, flags=re.IGNORECASE)[0]
            display_text = re.split(r'\[\d+\].*?\|\|\|', display_text, flags=re.DOTALL)[0]
            
            final_html = process_text_with_tooltips(display_text)
            placeholder.markdown(final_html, unsafe_allow_html=True)
            
            # IMPORTANTE: El botón no aparecerá en el "streaming" inmediato por limitación de Streamlit,
            # pero aparecerá en cuanto el componente se refresque o se haga scroll.
            if "|||" in full_response:
                st.button("Ver Fuentes y Citas", key=f"src_btn_live", on_click=show_sources_dialog, args=(full_response,))
            
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            if on_generation_success:
                on_generation_success(full_response)
            return full_response
        else:
            st.error("Error: No se recibió respuesta de la IA.")
            return None
