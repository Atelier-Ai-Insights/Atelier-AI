import streamlit as st
import json
import constants as c

# --- COMPONENTES UNIFICADOS ---
from components.chat_interface import render_chat_history, handle_chat_interaction

# --- IMPORTACIONES SERVICIOS ---
try:
    from services.gemini_api import call_gemini_api, call_gemini_stream
    gemini_available = True
except ImportError:
    gemini_available = False
    def call_gemini_api(p, generation_config_override=None): return None
    def call_gemini_stream(p): return None

from utils import get_relevant_info, clean_gemini_json, render_process_status
from services.supabase_db import log_query_event
from prompts import get_persona_generation_prompt, get_persona_chat_instruction
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# ==========================================
# MODO: PERFILES SINTÉTICOS (RELEVANCIA OPTIMIZADA)
# ==========================================
def synthetic_users_mode(db, selected_files):
    st.subheader("Perfil Sintético")
    st.markdown("Simula conversaciones con perfiles de consumidor generados a partir de tus datos reales.")
    
    # ---------------------------------------------------------
    # 1. CONFIGURACIÓN DEL PERFIL
    # ---------------------------------------------------------
    show_config = "synthetic_persona_data" not in st.session_state.mode_state
    
    with st.expander("Configurar Perfil Sintético", expanded=show_config):
        segment_name = st.text_input("Nombre del Segmento a simular:", placeholder="Ej: Compradores sensibles al precio...")
        
        if st.button("Generar ADN del Perfil", type="primary", width="stretch"):
            if not selected_files:
                st.warning("⚠️ Selecciona documentos en el menú lateral.")
                return
            
            if not segment_name: 
                st.warning("⚠️ Define un nombre para el segmento.")
                return
            
            with render_process_status("Analizando datos y construyendo psique...", expanded=True) as status:
                if not gemini_available:
                    status.update(label="IA no disponible", state="error")
                    return

                # Contexto inicial para crear la identidad
                status.write("🔍 Escaneando documentos para el ADN del perfil...")
                context = get_relevant_info(db, segment_name, selected_files)
                
                if not context: 
                    status.update(label="No hay datos suficientes.", state="error")
                    return
                
                status.write("Diseñando personalidad y visión de futuro...")
                prompt = get_persona_generation_prompt(segment_name, context)
                
                resp = call_gemini_api(prompt, generation_config_override={"response_mime_type": "application/json"})
                
                if resp: 
                    try:
                        clean_resp = clean_gemini_json(resp)
                        persona_data = json.loads(clean_resp)
                        
                        if isinstance(persona_data, list):
                            persona_data = persona_data[0] if persona_data else {}
                        
                        persona_data = {k.lower(): v for k, v in persona_data.items()}
                        
                        st.session_state.mode_state["synthetic_persona_data"] = persona_data
                        st.session_state.mode_state["synthetic_chat_history"] = [] 
                        
                        try:
                            log_query_event(f"Persona: {segment_name}", c.MODE_SYNTHETIC)
                        except: pass
                        
                        status.update(label="¡Perfil Creado!", state="complete", expanded=False)
                        st.rerun()
                        
                    except Exception as e:
                        status.update(label="Error de formato", state="error")
                        st.error(f"Error procesando la respuesta de la IA: {e}")
                else:
                    status.update(label="Error de conexión con IA", state="error")

    # ---------------------------------------------------------
    # 2. VISUALIZACIÓN Y ENTREVISTA DINÁMICA
    # ---------------------------------------------------------
    if "synthetic_persona_data" in st.session_state.mode_state:
        p = st.session_state.mode_state["synthetic_persona_data"]
        
        if not isinstance(p, dict):
            st.error("Error: Datos corruptos.")
            if st.button("Reiniciar"):
                st.session_state.mode_state.pop("synthetic_persona_data", None)
                st.rerun()
            return

        st.divider()
        
        # Tarjeta de Identidad
        col_img, col_info = st.columns([1, 4])
        with col_img:
            st.markdown(f"<div style='font-size: 80px; text-align: center;'>👤</div>", unsafe_allow_html=True)
        with col_info:
            st.markdown(f"### {p.get('nombre', 'Usuario Simulado')}")
            st.caption(f"{p.get('edad', 'N/A')} | {p.get('ocupacion', 'N/A')}")
            st.info(f"**Bio:** {p.get('bio_breve', 'Sin biografía.')}")
            
        with st.expander("Ver ADN Psicológico y Prospectiva"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Dolores y Miedos:**")
                for d in p.get('dolores_principales', []): st.write(f"- {d}")
                st.markdown(f"**Visión Futuro:** {p.get('vision_prospectiva', 'No definida.')}")
            with c2:
                st.markdown("**Motivadores:**")
                for m in p.get('motivadores_compra', []): st.write(f"- {m}")
                st.write("")
                st.markdown(f"**Estilo:** *{p.get('estilo_comunicacion', 'Estándar')}*")

        st.divider()
        st.markdown(f"#### 💬 Entrevista con {p.get('nombre', 'Usuario')}")
        
        # 1. Renderizar historial
        render_chat_history(st.session_state.mode_state["synthetic_chat_history"], source_mode="synthetic")

        # 2. Interacción con RAG Dinámico por Pregunta
        placeholder_text = f"Pregunta a {p.get('nombre')} sobre temas específicos..."
        
        if user_question := st.chat_input(placeholder_text):
            
            def acting_generator():
                with st.spinner(f"{p.get('nombre')} está redactando una respuesta detallada..."):
                    if not gemini_available: return iter(["(Error: IA desconectada)"])
                    
                    # MEJORA: Buscamos información relevante ESPECÍFICA para la pregunta del usuario
                    # Esto garantiza que la respuesta extensa esté anclada a la pregunta.
                    current_context = get_relevant_info(db, user_question, selected_files)
                    
                    # Memoria de la conversación
                    history_slice = st.session_state.mode_state["synthetic_chat_history"][-5:]
                    history_str = "\n".join([f"{m['role']}: {m['content']}" for m in history_slice])

                    # Prompt con jerarquía de relevancia
                    acting_prompt = get_persona_chat_instruction(
                        p, 
                        user_question, 
                        history_str, 
                        current_context
                    )
                    
                    stream = call_gemini_stream(acting_prompt)
                    return stream if stream else iter(["(El usuario guarda silencio...)"])

            handle_chat_interaction(
                prompt=user_question,
                response_generator_func=acting_generator,
                history_key="synthetic_chat_history",
                source_mode="synthetic"
            )

        # 3. Acciones Finales
        if st.session_state.mode_state["synthetic_chat_history"]:
            st.divider()
            c1, c2, c3 = st.columns(3)
            
            with c1:
                chat_content = f"# Entrevista: {p.get('nombre')}\n\n"
                chat_content += f"**Bio:** {p.get('bio_breve')}\n\n---\n\n"
                for m in st.session_state.mode_state["synthetic_chat_history"]:
                    role_label = "Entrevistador" if m['role'] == 'user' else p.get('nombre')
                    chat_content += f"**{role_label}:** {m['content']}\n\n"
                
                pdf_bytes = generate_pdf_html(chat_content, title=f"Entrevista - {p.get('nombre')}", banner_path=banner_file)
                if pdf_bytes:
                    st.download_button("Descargar PDF", data=pdf_bytes, file_name=f"entrevista_{p.get('nombre')}.pdf", width="stretch")

            with c2:
                if st.button("Limpiar Chat", width="stretch"):
                    st.session_state.mode_state["synthetic_chat_history"] = []
                    st.rerun()

            with c3:
                if st.button("Cambiar Perfil", width="stretch", type="secondary"):
                    st.session_state.mode_state.pop("synthetic_persona_data", None)
                    st.session_state.mode_state.pop("synthetic_chat_history", None)
                    st.rerun()
