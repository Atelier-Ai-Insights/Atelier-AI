import streamlit as st
import json
from utils import get_relevant_info, clean_gemini_json, render_process_status
from services.gemini_api import call_gemini_api, call_gemini_stream
from services.supabase_db import log_query_event
from prompts import get_persona_generation_prompt, get_persona_chat_instruction
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

def synthetic_users_mode(db, selected_files):
    st.subheader("Perfil Sintético")
    st.markdown("Simula conversaciones con perfiles de consumidor generados a partir de tus datos reales.")
    
    # 1. CONFIGURACIÓN DEL PERFIL
    show_config = "synthetic_persona_data" not in st.session_state.mode_state
    
    with st.expander("Configurar Perfil Sintético", expanded=show_config):
        segment_name = st.text_input("Nombre del Segmento a simular:", placeholder="Ej: Compradores sensibles al precio, Mamás primerizas...")
        
        if st.button("Generar ADN del Perfil", type="primary", use_container_width=True):
            if not selected_files:
                st.warning("⚠️ Selecciona documentos en el menú lateral.")
                return
            
            if not segment_name: 
                st.warning("⚠️ Define un nombre para el segmento.")
                return
            
            with render_process_status("Analizando datos y construyendo psique...", expanded=True) as status:
                
                # A. Buscar contexto
                status.write("Escaneando documentos...")
                context = get_relevant_info(db, segment_name, selected_files)
                
                if not context: 
                    status.update(label="No hay datos suficientes.", state="error")
                    return
                
                # B. Generar Perfil
                status.write("Diseñando personalidad...")
                prompt = get_persona_generation_prompt(segment_name, context)
                
                resp = call_gemini_api(prompt, generation_config_override={"response_mime_type": "application/json"})
                
                if resp: 
                    try:
                        clean_resp = clean_gemini_json(resp)
                        persona_data = json.loads(clean_resp)
                        
                        if isinstance(persona_data, list):
                            if len(persona_data) > 0:
                                persona_data = persona_data[0]
                            else:
                                raise ValueError("La IA devolvió una lista vacía.")
                        
                        st.session_state.mode_state["synthetic_persona_data"] = persona_data
                        st.session_state.mode_state["synthetic_chat_history"] = [] 
                        
                        # --- CORRECCIÓN AQUÍ: Usamos MODE_SYNTHETIC ---
                        try:
                            log_query_event(f"Persona: {segment_name}", mode=c.MODE_SYNTHETIC)
                        except Exception as e:
                            print(f"Log warning: {e}")
                        
                        status.update(label="¡Perfil Creado!", state="complete", expanded=False)
                        st.rerun()
                        
                    except Exception as e:
                        status.update(label="Error de formato", state="error")
                        st.error(f"Error procesando la respuesta de la IA: {e}")
                else:
                    status.update(label="Error de conexión con IA", state="error")

    # 2. VISUALIZACIÓN DEL PERFIL Y CHAT
    if "synthetic_persona_data" in st.session_state.mode_state:
        p = st.session_state.mode_state["synthetic_persona_data"]
        
        if not isinstance(p, dict):
            st.error("Error: El perfil generado no tiene el formato correcto.")
            if st.button("Reiniciar"):
                st.session_state.mode_state.pop("synthetic_persona_data")
                st.rerun()
            return

        st.divider()
        
        col_img, col_info = st.columns([1, 4])
        with col_img:
            st.markdown(f"<div style='font-size: 80px; text-align: center; line-height: 1;'>👤</div>", unsafe_allow_html=True)
        with col_info:
            st.markdown(f"### {p.get('nombre', 'Sin Nombre')}")
            st.caption(f"{p.get('edad', 'N/A')} | {p.get('ocupacion', 'N/A')}")
            st.info(f"**Bio:** {p.get('bio_breve', 'Sin biografía')}")
            
        with st.expander("Ver detalles psicológicos (Dolores y Motivadores)"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Dolores:**")
                st.write(p.get('dolores_principales', []))
            with c2:
                st.markdown("**Motivadores:**")
                st.write(p.get('motivadores_compra', []))
            
            st.markdown(f"**Estilo:** *{p.get('estilo_comunicacion', 'Estándar')}*")

        # 3. CHAT
        st.divider()
        st.markdown(f"#### Entrevista a {p.get('nombre', 'Usuario')}")
        
        if "synthetic_chat_history" not in st.session_state.mode_state:
            st.session_state.mode_state["synthetic_chat_history"] = []
            
        for msg in st.session_state.mode_state["synthetic_chat_history"]:
            role = msg['role']
            name = "Entrevistador" if role == "user" else p.get('nombre', 'Usuario')
            avatar = "🎤" if role == "user" else "👤"
            
            with st.chat_message(name, avatar=avatar):
                st.markdown(msg['content'])

        user_question = st.chat_input(f"Hazle una pregunta a {p.get('nombre', 'Usuario')}...")
        
        if user_question:
            st.session_state.mode_state["synthetic_chat_history"].append({"role": "user", "content": user_question})
            with st.chat_message("Entrevistador", avatar="🎤"):
                st.markdown(user_question)
            
            with st.chat_message(p.get('nombre', 'Usuario'), avatar="👤"):
                with st.spinner(f"{p.get('nombre')} está pensando..."):
                    acting_prompt = get_persona_chat_instruction(p, user_question)
                    stream = call_gemini_stream(acting_prompt)
                    if stream:
                        response = st.write_stream(stream)
                        st.session_state.mode_state["synthetic_chat_history"].append({"role": "assistant", "content": response})

        # --- ACCIONES ---
        if st.session_state.mode_state["synthetic_chat_history"]:
            st.divider()
            c1, c2, c3 = st.columns(3)
            
            with c1:
                chat_content = f"# Entrevista con Perfil Sintético: {p.get('nombre')}\n\n"
                chat_content += f"**Perfil:** {p.get('edad')}, {p.get('ocupacion')}\n\n---\n\n"
                for m in st.session_state.mode_state["synthetic_chat_history"]:
                    role_label = "Entrevistador" if m['role'] == 'user' else p.get('nombre')
                    chat_content += f"**{role_label}:** {m['content']}\n\n"
                
                pdf_bytes = generate_pdf_html(chat_content, title=f"Entrevista - {p.get('nombre')}", banner_path=banner_file)
                if pdf_bytes:
                    st.download_button("Descargar PDF", data=pdf_bytes, file_name=f"entrevista_{p.get('nombre')}.pdf", use_container_width=True)

            with c2:
                if st.button("Reiniciar Chat", use_container_width=True):
                    st.session_state.mode_state["synthetic_chat_history"] = []
                    st.rerun()

            with c3:
                if st.button("Crear Nuevo Perfil", use_container_width=True, type="secondary"):
                    st.session_state.mode_state.pop("synthetic_persona_data", None)
                    st.session_state.mode_state.pop("synthetic_chat_history", None)
                    st.rerun()
