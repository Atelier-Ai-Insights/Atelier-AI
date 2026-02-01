import streamlit as st
import json
import constants as c

# --- NUEVO: COMPONENTE UNIFICADO ---
from components.chat_interface import render_chat_history, handle_chat_interaction

# --- IMPORTACIONES SERVICIOS ---
try:
    # Usamos stream para el chat
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
# MODO: PERFILES SINTÉTICOS (OPTIMIZADO)
# ==========================================
def synthetic_users_mode(db, selected_files):
    st.subheader("Perfil Sintético")
    st.markdown("Simula conversaciones con perfiles de consumidor generados a partir de tus datos reales.")
    
    # ---------------------------------------------------------
    # 1. CONFIGURACIÓN DEL PERFIL (Mantenemos lógica original)
    # ---------------------------------------------------------
    show_config = "synthetic_persona_data" not in st.session_state.mode_state
    
    with st.expander("Configurar Perfil Sintético", expanded=show_config):
        segment_name = st.text_input("Nombre del Segmento a simular:", placeholder="Ej: Compradores sensibles al precio, Mamás primerizas...")
        
        if st.button("Generar ADN del Perfil", type="primary", width="stretch"):
            if not selected_files:
                st.warning("⚠️ Selecciona documentos en el menú lateral.")
                return
            
            if not segment_name: 
                st.warning("⚠️ Define un nombre para el segmento.")
                return
            
            # Usamos status para feedback visual
            with render_process_status("Analizando datos y construyendo psique...", expanded=True) as status:
                if not gemini_available:
                    status.update(label="IA no disponible", state="error")
                    return

                # A. Buscar contexto
                status.write("🔍 Escaneando documentos...")
                context = get_relevant_info(db, segment_name, selected_files)
                
                if not context: 
                    status.update(label="No hay datos suficientes.", state="error")
                    return
                
                # B. Generar Perfil (JSON)
                status.write("Diseñando personalidad...")
                prompt = get_persona_generation_prompt(segment_name, context)
                
                # Llamada standard (no stream) porque necesitamos JSON completo
                resp = call_gemini_api(prompt, generation_config_override={"response_mime_type": "application/json"})
                
                if resp: 
                    try:
                        clean_resp = clean_gemini_json(resp)
                        persona_data = json.loads(clean_resp)
                        
                        # Normalización de datos
                        if isinstance(persona_data, list):
                            persona_data = persona_data[0] if persona_data else {}
                        
                        persona_data = {k.lower(): v for k, v in persona_data.items()}
                        
                        st.session_state.mode_state["synthetic_persona_data"] = persona_data
                        st.session_state.mode_state["synthetic_chat_history"] = [] 
                        
                        try:
                            log_query_event(f"Persona: {segment_name}", mode=c.MODE_SYNTHETIC)
                        except: pass
                        
                        status.update(label="¡Perfil Creado!", state="complete", expanded=False)
                        st.rerun()
                        
                    except Exception as e:
                        status.update(label="Error de formato", state="error")
                        st.error(f"Error procesando la respuesta de la IA: {e}")
                else:
                    status.update(label="Error de conexión con IA", state="error")

    # ---------------------------------------------------------
    # 2. VISUALIZACIÓN Y CHAT (Aquí aplicamos la optimización)
    # ---------------------------------------------------------
    if "synthetic_persona_data" in st.session_state.mode_state:
        p = st.session_state.mode_state["synthetic_persona_data"]
        
        # Validación de seguridad
        if not isinstance(p, dict):
            st.error("Error: Datos corruptos.")
            if st.button("Reiniciar"):
                st.session_state.mode_state.pop("synthetic_persona_data", None)
                st.rerun()
            return

        st.divider()
        
        # Tarjeta de Identidad (Visualización)
        col_img, col_info = st.columns([1, 4])
        with col_img:
            st.markdown(f"<div style='font-size: 80px; text-align: center; line-height: 1;'>👤</div>", unsafe_allow_html=True)
        with col_info:
            st.markdown(f"### {p.get('nombre', 'Usuario Simulado')}")
            st.caption(f"{p.get('edad', 'N/A')} | {p.get('ocupacion', 'N/A')}")
            st.info(f"**Bio:** {p.get('bio_breve', 'Sin biografía.')}")
            
        with st.expander("Ver detalles psicológicos (Dolores y Motivadores)"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Dolores:**")
                for d in p.get('dolores_principales', []): st.write(f"- {d}")
            with c2:
                st.markdown("**Motivadores:**")
                for m in p.get('motivadores_compra', []): st.write(f"- {m}")
            st.write("")
            st.markdown(f"**Estilo:** *{p.get('estilo_comunicacion', 'Estándar')}*")

        st.divider()
        st.markdown(f"#### 💬 Entrevista a {p.get('nombre', 'Usuario')}")
        
        # --- AQUI: REEMPLAZO POR COMPONENTE UNIFICADO ---
        
        # 1. Renderizar historial
        render_chat_history(st.session_state.mode_state["synthetic_chat_history"], source_mode="synthetic")

        # 2. Interacción
        placeholder_text = f"Hazle una pregunta a {p.get('nombre', 'Usuario')}..."
        
        if user_question := st.chat_input(placeholder_text):
            
            # Definimos el generador de actuación (Method Acting)
            def acting_generator():
                # En este caso no usamos st.status para que se sienta más como un chat fluido
                # a menos que la IA tarde mucho.
                with st.spinner(f"{p.get('nombre')} está pensando..."):
                    if not gemini_available: return iter(["(Error: IA desconectada)"])
                    
                    # Prompt de actuación
                    acting_prompt = get_persona_chat_instruction(p, user_question)
                    
                    # Llamada Stream
                    stream = call_gemini_stream(acting_prompt)
                    return stream if stream else iter(["(El usuario permanece en silencio...)"])

            # Delegamos al componente
            handle_chat_interaction(
                prompt=user_question,
                response_generator_func=acting_generator,
                history_key="synthetic_chat_history",
                source_mode="synthetic"
                # No logueamos cada interacción de chat aquí para no saturar la base de queries,
                # pero podrías descomentarlo si lo deseas.
            )

        # 3. Acciones Finales (Exportar / Reiniciar)
        if st.session_state.mode_state["synthetic_chat_history"]:
            st.divider()
            c1, c2, c3 = st.columns(3)
            
            with c1:
                # Preparamos texto para PDF
                chat_content = f"# Entrevista con Perfil Sintético: {p.get('nombre')}\n\n"
                chat_content += f"**Perfil:** {p.get('edad')}, {p.get('ocupacion')}\n\n---\n\n"
                for m in st.session_state.mode_state["synthetic_chat_history"]:
                    # Ajustamos etiquetas para el reporte
                    role_label = "Entrevistador" if m['role'] == 'user' else p.get('nombre')
                    chat_content += f"**{role_label}:** {m['content']}\n\n"
                
                pdf_bytes = generate_pdf_html(chat_content, title=f"Entrevista - {p.get('nombre')}", banner_path=banner_file)
                if pdf_bytes:
                    st.download_button("Descargar PDF", data=pdf_bytes, file_name=f"entrevista_{p.get('nombre')}.pdf", width="stretch")

            with c2:
                if st.button("Reiniciar Chat", width="stretch"):
                    st.session_state.mode_state["synthetic_chat_history"] = []
                    st.rerun()

            with c3:
                if st.button("Crear Nuevo Perfil", width="stretch", type="secondary"):
                    st.session_state.mode_state.pop("synthetic_persona_data", None)
                    st.session_state.mode_state.pop("synthetic_chat_history", None)
                    st.rerun()
