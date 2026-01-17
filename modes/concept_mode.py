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
    from prompts import get_concept_gen_prompt 
except ImportError:
    def log_query_event(q, m): pass
    def save_project_insight(c, source_mode): pass
    def get_concept_gen_prompt(h, r): return ""

# 4. PDF Config
try:
    from reporting.pdf_generator import generate_pdf_html
    from config import banner_file
except ImportError:
    generate_pdf_html = None
    banner_file = None

# ==========================================
# CALLBACKS (LA SOLUCIÓN AL DOBLE CLIC)
# ==========================================
def handle_save_concept(content):
    """
    Esta función se ejecuta ANTES de que la app se recargue.
    Garantiza que el dato ya esté en la DB cuando se pinte el sidebar.
    """
    try:
        save_project_insight(content, source_mode="concept")
        st.toast("✅ Concepto guardado exitosamente")
    except Exception as e:
        st.toast(f"❌ Error al guardar: {e}")

# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================
def concept_generation_mode(db, selected_files):
    st.subheader("Generador de Conceptos")
    st.caption("Estructura ideas de innovación en conceptos de marketing sólidos (Insight + Beneficio + RTB).")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "concept_history" not in st.session_state.mode_state:
        st.session_state.mode_state["concept_history"] = []

    # 2. MOSTRAR HISTORIAL
    for idx, msg in enumerate(st.session_state.mode_state["concept_history"]):
        role_avatar = "✨" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=role_avatar):
            if msg["role"] == "assistant":
                # Renderizar con tooltips limpios
                html_content = process_text_with_tooltips(msg["content"])
                st.markdown(html_content, unsafe_allow_html=True)
                
                # BOTÓN PIN CON CALLBACK (Solución Definitiva)
                col_s, col_p = st.columns([15, 1])
                with col_p:
                    st.button(
                        "📌", 
                        key=f"pin_con_{idx}", 
                        help="Guardar Concepto",
                        on_click=handle_save_concept,  # <--- MAGIA AQUÍ
                        args=(msg["content"],)         # Pasamos el contenido como argumento
                    )
            else:
                st.markdown(msg["content"])

    # 3. INPUT DE USUARIO
    concept_input = st.chat_input("Describe la idea base para el concepto...")

    if concept_input:
        # A. Mostrar mensaje usuario
        st.session_state.mode_state["concept_history"].append({"role": "user", "content": concept_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(concept_input)

        # B. Generar Respuesta
        with st.chat_message("assistant", avatar="✨"):
            response = None
            placeholder = st.empty()
            
            with render_process_status("Diseñando concepto ganador...", expanded=True) as status:
                if gemini_available:
                    status.write("Buscando evidencia de soporte...")
                    relevant_info = get_relevant_info(db, concept_input, selected_files)
                    
                    status.write("Estructurando Insight, Beneficio y RTB...")
                    prompt = get_concept_gen_prompt(concept_input, relevant_info)
                    response = call_gemini_api(prompt)
                    
                    if response:
                        status.update(label="Concepto Generado", state="complete", expanded=False)
                    else:
                        status.update(label="Error al generar", state="error")
                else:
                    status.update(label="Servicio IA no disponible", state="error")
            
            # C. Mostrar respuesta final
            if response:
                enriched_html = process_text_with_tooltips(response)
                placeholder.markdown(enriched_html, unsafe_allow_html=True)
                
                st.session_state.mode_state["concept_history"].append({"role": "assistant", "content": response})
                
                # Botón PIN para la nueva respuesta (CON CALLBACK)
                col_s, col_p = st.columns([15, 1])
                with col_p:
                    st.button(
                        "📌", 
                        key="pin_con_new", 
                        help="Guardar Concepto",
                        on_click=handle_save_concept, # <--- MAGIA AQUÍ TAMBIÉN
                        args=(response,)
                    )
                
                try:
                    log_query_event(f"Concepto: {concept_input[:30]}", mode=c.MODE_CONCEPT)
                except: pass

    # 4. BOTONES DE ACCIÓN
    if st.session_state.mode_state["concept_history"]:
        st.write("") 
        
        col1, col2 = st.columns(2)
        
        with col1:
            if generate_pdf_html:
                full_text = ""
                for m in st.session_state.mode_state["concept_history"]:
                    role = "Idea Base" if m["role"] == "user" else "Concepto Desarrollado"
                    full_text += f"**{role}:**\n{m['content']}\n\n---\n\n"

                try:
                    pdf_bytes = generate_pdf_html(full_text, title="Conceptos de Producto", banner_path=banner_file)
                    if pdf_bytes:
                        st.download_button(
                            label="Descargar PDF", 
                            data=pdf_bytes, 
                            file_name="Conceptos_Generados.pdf", 
                            mime="application/pdf", 
                            type="secondary",
                            use_container_width=True
                        )
                except Exception: pass
        
        with col2:
            if st.button("Nueva Sesión", type="secondary", use_container_width=True):
                st.session_state.mode_state["concept_history"] = []
                st.rerun()
