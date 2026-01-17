import streamlit as st
import constants as c

# --- BLOQUE DE SEGURIDAD (SAFE IMPORTS) ---
def safe_process_text(text): return text

# 1. Servicios IA
try:
    from services.gemini_api import call_gemini_api
    gemini_available = True
except ImportError:
    gemini_available = False
    def call_gemini_api(prompt): return "Error: Servicio de IA no disponible."

# 2. Utilidades y Citas
try:
    from utils import get_relevant_info, render_process_status
    try:
        from utils import process_text_with_tooltips
    except ImportError:
        process_text_with_tooltips = safe_process_text
except ImportError:
    def get_relevant_info(db, q, f): return ""
    def render_process_status(l, expanded=True): return st.status(l, expanded=expanded)
    process_text_with_tooltips = safe_process_text

# 3. Base de Datos y Memoria
try:
    from services.supabase_db import log_query_event
    from services.memory_service import save_project_insight
    from prompts import get_ideation_prompt
except ImportError:
    def log_query_event(q, m): pass
    def save_project_insight(c, source_mode): pass
    def get_ideation_prompt(h, r): return ""

# 4. PDF Config
try:
    from reporting.pdf_generator import generate_pdf_html
    from config import banner_file
except ImportError:
    generate_pdf_html = None
    banner_file = None


# ==========================================
# FUNCIÓN PRINCIPAL: IDEACIÓN
# ==========================================
def ideacion_mode(db, selected_files):
    st.subheader("Ideación Estratégica")
    st.caption("Brainstorming creativo fundamentado en datos del repositorio.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # Inicializar historial
    if "ideation_history" not in st.session_state.mode_state:
        st.session_state.mode_state["ideation_history"] = []

    # 1. MOSTRAR HISTORIAL
    for idx, msg in enumerate(st.session_state.mode_state["ideation_history"]):
        role_avatar = "✨" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=role_avatar):
            if msg["role"] == "assistant":
                # Renderizar con tooltips
                html_content = process_text_with_tooltips(msg["content"])
                st.markdown(html_content, unsafe_allow_html=True)
                
                # Botón PIN para guardar idea en historial
                col_s, col_p = st.columns([15, 1])
                with col_p:
                    if st.button("📌", key=f"pin_idea_{idx}", help="Guardar en Memoria del Proyecto"):
                        save_project_insight(msg["content"], source_mode="ideation")
                        st.toast("✅ Idea guardada")
            else:
                st.markdown(msg["content"])

    # 2. INPUT DE USUARIO
    user_input = st.chat_input("Escribe un desafío creativo...")
    
    if user_input:
        # A. Mostrar mensaje usuario
        st.session_state.mode_state["ideation_history"].append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # B. Generar respuesta
        with st.chat_message("assistant", avatar="✨"):
            response = None
            placeholder = st.empty()
            
            with render_process_status("Conectando puntos...", expanded=True) as status:
                if gemini_available:
                    relevant_info = get_relevant_info(db, user_input, selected_files)
                    
                    # Contexto breve de últimos mensajes
                    hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["ideation_history"][-3:]])
                    
                    prompt = get_ideation_prompt(hist_str, relevant_info)
                    response = call_gemini_api(prompt) # Ideación usa llamada normal (no stream) usualmente
                    
                    if response:
                        status.update(label="¡Ideas generadas!", state="complete", expanded=False)
                    else:
                        status.update(label="Error al generar", state="error")
                else:
                     status.update(label="Servicio IA no disponible", state="error")

            # C. Mostrar respuesta final
            if response:
                # Procesar Citas y Tooltips
                enriched_html = process_text_with_tooltips(response)
                placeholder.markdown(enriched_html, unsafe_allow_html=True)
                
                st.session_state.mode_state["ideation_history"].append({"role": "assistant", "content": response})
                
                # Botón PIN para la nueva respuesta
                col_s, col_p = st.columns([15, 1])
                with col_p:
                    if st.button("📌", key="pin_idea_new", help="Guardar en Memoria del Proyecto"):
                        save_project_insight(response, source_mode="ideation")
                        st.toast("✅ Idea guardada")
                
                try:
                    log_query_event(f"Ideación: {user_input[:50]}", mode=c.MODE_IDEATION)
                except: pass

    # 3. BOTONES DE ACCIÓN
    if st.session_state.mode_state["ideation_history"]:
        st.write("") 
        
        col1, col2 = st.columns(2)
        
        with col1:
            if generate_pdf_html:
                # Generar texto plano para el PDF
                full_chat_text = ""
                for m in st.session_state.mode_state["ideation_history"]:
                    role_title = "Usuario" if m["role"] == "user" else "Atelier AI"
                    full_chat_text += f"**{role_title}:**\n{m['content']}\n\n"
                
                try:
                    pdf_bytes = generate_pdf_html(full_chat_text, title="Sesión de Ideación", banner_path=banner_file)
                    if pdf_bytes:
                        st.download_button(
                            label="Descargar PDF",
                            data=pdf_bytes,
                            file_name="Ideacion_Creativa.pdf",
                            mime="application/pdf",
                            type="secondary",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"No se pudo generar PDF: {e}")

        with col2:
            if st.button("Nueva Búsqueda", type="secondary", use_container_width=True):
                st.session_state.mode_state["ideation_history"] = []
                st.rerun()
