import streamlit as st
import time
import constants as c

# --- BLOQUE DE SEGURIDAD MÁXIMA ---
def safe_process_text(text):
    return text  # Versión simple sin HTML

# Intentamos importar Gemini
try:
    from services.gemini_api import call_gemini_stream
    gemini_available = True
except Exception as e:
    print(f"Error Gemini: {e}")
    gemini_available = False
    def call_gemini_stream(prompt): return None

# Intentamos importar Utilidades básicas
try:
    from utils import get_relevant_info, render_process_status
    # Importamos la función de tooltips que arreglamos
    try:
        from utils import process_text_with_tooltips
    except ImportError:
        process_text_with_tooltips = safe_process_text
except Exception:
    def get_relevant_info(db, q, f): return "Info simulada"
    def render_process_status(text, expanded=False): return st.status(text, expanded=expanded)
    process_text_with_tooltips = safe_process_text

# Intentamos importar Prompts y Logs
try:
    from prompts import get_grounded_chat_prompt
    from services.supabase_db import log_query_event
    from services.memory_service import save_project_insight 
except Exception:
    def get_grounded_chat_prompt(h, r): return "Prompt simulado"
    def log_query_event(q, mode): pass
    def save_project_insight(c, source_mode): return True

# DESACTIVAMOS PDF TEMPORALMENTE PARA DESCARTAR EL ERROR
generate_pdf_html = None 
from config import banner_file

# ==========================================
# FUNCIÓN PRINCIPAL DEL CHAT
# ==========================================
def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    st.caption("Consulta tus documentos con referencias verificadas.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "chat_history" not in st.session_state.mode_state:
        st.session_state.mode_state["chat_history"] = []

    # 2. MOSTRAR HISTORIAL
    for idx, msg in enumerate(st.session_state.mode_state["chat_history"]):
        role_avatar = "✨" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=role_avatar):
            if msg["role"] == "assistant":
                # AQUÍ ESTÁ LA MAGIA: Procesamos el texto histórico con tooltips
                formatted_html = process_text_with_tooltips(msg["content"])
                st.markdown(formatted_html, unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])
            
            # Botón PIN simplificado
            if msg["role"] == "assistant":
                col_spacer, col_pin = st.columns([15, 1])
                with col_pin:
                    if st.button("📌", key=f"pin_hist_{idx}", help="Guardar"):
                        try:
                            save_project_insight(msg["content"], source_mode="chat")
                            st.toast("✅ Guardado")
                        except: pass

    # 3. INPUT DEL USUARIO
    if user_input := st.chat_input("Haz una pregunta sobre tus documentos..."):
        
        # A. Guardar pregunta
        st.session_state.mode_state["chat_history"].append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # B. Generar Respuesta
        with st.chat_message("assistant", avatar="✨"):
            full_response = ""
            placeholder = st.empty()
            
            try:
                with st.status("Consultando documentos...", expanded=True) as status:
                    
                    if not gemini_available:
                        status.update(label="Error: IA no disponible", state="error")
                        full_response = "⚠️ El servicio de IA no se pudo cargar correctamente."
                    
                    else:
                        relevant_info = get_relevant_info(db, user_input, selected_files)
                        
                        if not relevant_info:
                            status.update(label="Sin hallazgos", state="error")
                            full_response = "No encontré información en los documentos."
                        else:
                            # Construir prompt
                            hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["chat_history"][-3:]])
                            prompt = get_grounded_chat_prompt(hist_str, relevant_info)
                            
                            # Llamada a IA
                            stream = call_gemini_stream(prompt)
                            
                            if stream:
                                status.update(label="Escribiendo...", state="running")
                                for chunk in stream:
                                    full_response += chunk
                                    # Mientras escribe, mostramos texto plano para velocidad
                                    placeholder.markdown(full_response + "▌")
                                status.update(label="Listo", state="complete", expanded=False)
                            else:
                                full_response = "Error de conexión con la IA."
                                status.update(label="Error", state="error")
            
            except Exception as e:
                full_response = f"Error inesperado: {str(e)}"
                print(f"Error Chat Loop: {e}")
            
            # C. Render Final (AQUÍ APLICAMOS LA MAGIA)
            # Procesamos el texto final con la función de tooltips de utils.py
            final_html = process_text_with_tooltips(full_response)
            placeholder.markdown(final_html, unsafe_allow_html=True)
            
            # Guardar en historial (Guardamos el texto CRUDO para que la IA tenga contexto limpio, pero mostramos HTML)
            st.session_state.mode_state["chat_history"].append({"role": "assistant", "content": full_response})
            
            # Botón PIN para respuesta nueva
            col_s, col_p = st.columns([15, 1])
            with col_p:
                if st.button("📌", key="pin_new", help="Guardar"):
                    save_project_insight(full_response, source_mode="chat")
                    st.toast("✅ Guardado")

    # 4. BOTÓN LIMPIAR
    if st.session_state.mode_state["chat_history"]:
        st.write("")
        if st.button("Limpiar Conversación", use_container_width=True):
            st.session_state.mode_state["chat_history"] = []
            st.rerun()
