import streamlit as st
import json
from services.supabase_db import get_monthly_usage, log_query_event
from config import safety_settings
from services.gemini_api import call_gemini_api 
from reporting.ppt_generator import crear_ppt_desde_json
from utils import get_relevant_info, extract_text_from_pdfs, clean_gemini_json
from prompts import PROMPTS_ONEPAGER, get_onepager_final_prompt
import constants as c

# =====================================================
# MODO: GENERADOR DE ONE-PAGER PPT (OPTIMIZADO)
# =====================================================

def one_pager_ppt_mode(db_filtered, selected_files):
    st.subheader("Generador de Diapositivas Estratégicas")
    
    # 1. Verificación de Límites
    ppt_limit = st.session_state.plan_features.get('ppt_downloads_per_month', 0)
    is_unlimited = ppt_limit == float('inf')

    if is_unlimited:
        limit_text = "**Tu plan actual te permite generar One-Pagers ilimitados.**"
    elif ppt_limit > 0:
        limit_text = f"**Tu plan actual te permite generar {int(ppt_limit)} One-Pagers al mes.**"
    else:
        limit_text = "**Tu plan actual no incluye la generación de One-Pagers.**"

    st.markdown(f"""
        Sintetiza los hallazgos clave en una diapositiva de PowerPoint usando la plantilla seleccionada.
        {limit_text}
    """)

    # 2. Pantalla de Resultado (Descarga)
    # Si ya se generó un PPT, mostramos la opción de descargar y ocultamos el formulario para limpiar la UI
    if "generated_ppt_bytes" in st.session_state.mode_state:
        st.divider()
        template_name = st.session_state.mode_state.get('generated_ppt_template_name', 'Estratégica')
        st.success(f"✅ ¡Tu diapositiva '{template_name}' está lista!")
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 Descargar .pptx",
                data=st.session_state.mode_state["generated_ppt_bytes"],
                file_name=f"diapositiva_{template_name.lower().replace(' ','_')}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                width='stretch',
                type="primary"
            )
        with col2:
            if st.button("✨ Generar otra", width='stretch', type="secondary"):
                # Limpiamos el estado específico para volver a mostrar el formulario
                st.session_state.mode_state.pop("generated_ppt_bytes", None)
                st.session_state.mode_state.pop("generated_ppt_template_name", None)
                st.rerun()
        return

    # 3. Pantalla de Configuración (Formulario)
    st.divider()
    
    st.markdown("#### 1. Selecciona la Plantilla")
    template_options = list(PROMPTS_ONEPAGER.keys()) 
    selected_template_name = st.selectbox("Elige el tipo de diapositiva:", template_options)

    st.markdown("#### 2. Selecciona la Fuente de Datos")
    col_src1, col_src2 = st.columns(2)
    with col_src1: 
        use_repo = st.toggle("Usar Repositorio de Estudios", value=True)
    with col_src2: 
        use_uploads = st.toggle("Usar Archivos PDF Cargados", value=False)

    uploaded_files = None
    if use_uploads:
        uploaded_files = st.file_uploader(
            "Carga tus archivos PDF aquí:", 
            type=["pdf"], 
            accept_multiple_files=True, 
            key="onepager_pdf_uploader"
        )
        if uploaded_files: 
            st.caption(f"📎 {len(uploaded_files)} archivo(s) listo(s).")

    st.markdown(f"#### 3. Define el Tema Central")
    tema_central = st.text_area(
        "¿Cuál es el enfoque principal?", 
        height=100, 
        placeholder=f"Ej: {selected_template_name} para la marca X en el segmento joven..."
    )
    
    st.divider()

    # 4. Acción de Generar
    if st.button(f"Generar Diapositiva '{selected_template_name}'", width='stretch', type="primary"):
        
        # --- Validaciones Previas (Guard Clauses) ---
        current_ppt_usage = get_monthly_usage(st.session_state.user, c.MODE_ONEPAGER)
        
        if not is_unlimited and current_ppt_usage >= ppt_limit:
            st.error(f"⚠️ Has alcanzado tu límite mensual de {int(ppt_limit)} diapositivas.")
            return

        if not tema_central.strip():
            st.warning("⚠️ Por favor, describe el tema central para enfocar la generación.")
            return

        if not use_repo and not use_uploads:
            st.error("⚠️ Debes seleccionar al menos una fuente de datos (Repositorio o PDFs).")
            return

        if use_uploads and not uploaded_files:
            st.error("⚠️ Activaste 'Usar Archivos PDF' pero no has cargado ninguno.")
            return

        # --- Proceso de Generación ---
        with st.status("🎨 Diseñando tu One-Pager...", expanded=True) as status:
            
            # A. Recopilación de Contexto
            status.write("📚 Analizando fuentes de información...")
            relevant_info = ""
            
            try:
                if use_repo:
                    repo_text = get_relevant_info(db_filtered, tema_central, selected_files)
                    if repo_text: 
                        relevant_info += f"--- CONTEXTO REPOSITORIO ---\n{repo_text}\n\n"
                
                if use_uploads and uploaded_files:
                    pdf_text = extract_text_from_pdfs(uploaded_files)
                    if pdf_text: 
                        relevant_info += f"--- CONTEXTO PDFS CARGADOS ---\n{pdf_text}\n\n"
            
            except Exception as e:
                status.update(label="Error leyendo archivos", state="error")
                st.error(f"Ocurrió un error al leer los documentos: {e}")
                return

            # Validación crítica: ¿Tenemos información?
            if not relevant_info.strip(): 
                status.update(label="Falta de contexto", state="error")
                st.error("❌ No se encontró información relevante en las fuentes seleccionadas. Intenta ampliar el tema central o cambiar los archivos.")
                return

            # B. Generación de Estructura con IA
            status.write(f"🧠 Estructurando contenido para '{selected_template_name}'...")
            final_prompt_json = get_onepager_final_prompt(relevant_info, selected_template_name, tema_central)
            
            response_text = None
            data_json = None
            
            try:
                # Forzamos modo JSON en la configuración
                json_generation_config = {"response_mime_type": "application/json"}
                
                response_text = call_gemini_api(
                    final_prompt_json,
                    generation_config_override=json_generation_config
                )
                
                if not response_text: 
                    raise Exception("La API devolvió una respuesta vacía.")

                # Limpieza y Parseo
                cleaned_text = clean_gemini_json(response_text)
                data_json = json.loads(cleaned_text)

            except json.JSONDecodeError:
                status.update(label="Error de formato IA", state="error")
                st.error("La IA generó contenido pero falló el formato JSON. Intenta de nuevo.")
                # Opcional: st.code(response_text) para debug
                return
            except Exception as e:
                status.update(label="Error en IA", state="error")
                st.error(f"Error de conexión con el modelo: {e}")
                return

            # C. Ensamblaje del PPT
            if data_json:
                status.write("🛠️ Renderizando archivo PowerPoint (.pptx)...")
                
                try:
                    ppt_bytes = crear_ppt_desde_json(data_json)
                    
                    if ppt_bytes:
                        # Log de éxito y actualización de estado
                        log_query_event(f"{selected_template_name}: {tema_central}", mode=c.MODE_ONEPAGER)
                        
                        st.session_state.mode_state["generated_ppt_bytes"] = ppt_bytes
                        st.session_state.mode_state["generated_ppt_template_name"] = selected_template_name
                        
                        status.update(label="¡Diapositiva creada con éxito!", state="complete", expanded=False)
                        st.rerun()
                    else:
                        raise Exception("El generador de PPT devolvió un objeto vacío.")
                        
                except Exception as e:
                    status.update(label="Error en PowerPoint", state="error")
                    st.error(f"No se pudo construir el archivo PPTX: {e}")
