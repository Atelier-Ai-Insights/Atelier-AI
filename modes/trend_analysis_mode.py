import streamlit as st
import pandas as pd
import altair as alt
import json
import fitz  # PyMuPDF
import re
import time # IMPORTANTE: Para gestionar la velocidad de la capa gratuita
from utils import get_relevant_info, build_rag_context
# Asegúrate de que tu call_gemini soporte el parámetro 'model' o configúralo en services
from services.gemini_api import call_gemini_stream, call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_trend_analysis_prompt, SOURCE_LENSES
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: ANÁLISIS DE TENDENCIAS (VERSIÓN FREE TIER)
# =====================================================

def clean_text_optimized(text):
    """Limpieza agresiva para ahorrar tokens."""
    if not text: return ""
    # Quitar caracteres no imprimibles y espacios extra
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def safe_json_parse(json_str):
    """Intenta limpiar y parsear el JSON incluso si viene sucio."""
    try:
        # 1. Intentar carga directa
        return json.loads(json_str)
    except:
        try:
            # 2. Buscar patrón de bloque de código ```json ... ```
            match = re.search(r'```json\s*([\s\S]*?)\s*```', json_str)
            if match:
                return json.loads(match.group(1))
            # 3. Buscar solo corchetes
            match = re.search(r'\[\s*\{.*\}\s*\]', json_str, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except:
            return None
    return None

def trend_analysis_mode(db_filtered, selected_files):
    st.subheader("Análisis de Tendencias (Modo Eficiente)")
    st.markdown("#### ⚡ Motor: Gemini 1.5 Flash (Optimizado)")

    # --- RESULTADOS ---
    if "trend_result" in st.session_state.mode_state:
        st.divider()
        
        # 1. GRÁFICO (Con fallback si falla)
        if "trend_chart_data" in st.session_state.mode_state:
            st.markdown("### 📊 Matriz de Oportunidad")
            chart_data = st.session_state.mode_state["trend_chart_data"]
            
            # Colores
            domain = ["Emergente", "Crecimiento", "Mainstream", "Declive"]
            range_ = ["#FF9F1C", "#2EC4B6", "#E71D36", "#788B9C"]

            try:
                chart = alt.Chart(chart_data).mark_circle(size=200).encode(
                    x=alt.X('Madurez:Q', scale=alt.Scale(domain=[0, 11])),
                    y=alt.Y('Impacto:Q', scale=alt.Scale(domain=[0, 11])),
                    color=alt.Color('Etapa:N', scale=alt.Scale(domain=domain, range=range_)),
                    tooltip=['Tendencia', 'Etapa', 'Madurez', 'Impacto']
                ).properties(height=350).interactive()
                st.altair_chart(chart, use_container_width=True)
            except Exception as e:
                st.warning("No se pudo renderizar el gráfico detallado, mostrando datos crudos.")
                st.dataframe(chart_data)

        # 2. TEXTO
        st.markdown("### 📝 Reporte")
        st.markdown(st.session_state.mode_state["trend_result"])
        
        # Botón de reinicio
        if st.button("Nuevo Análisis", type="secondary", width='stretch'):
            keys = ["trend_result", "trend_topic", "trend_chart_data"]
            for k in keys: st.session_state.mode_state.pop(k, None)
            st.rerun()
        return

    st.divider()

    # --- INPUTS SIMPLIFICADOS ---
    trend_topic = st.text_input("Tema a analizar:", placeholder="Ej: Inteligencia Artificial en Banca")
    
    # Opciones ocultas en un expander para limpiar la interfaz
    with st.expander("Configuración Avanzada"):
        use_repo = st.toggle("Usar Base de Datos", value=True)
        uploaded_pdfs = st.file_uploader("PDFs Extra", type=["pdf"], accept_multiple_files=True)

    if st.button("🚀 Ejecutar Análisis Gratuito", type="primary", use_container_width=True):
        if not trend_topic.strip():
            st.warning("Escribe un tema."); return

        with st.status("Procesando...", expanded=True) as status:
            
            # 1. CONSTRUCCIÓN DE CONTEXTO (Optimizada)
            status.write("📄 Leyendo documentos...")
            full_text_docs = ""
            
            # Leer DB
            if use_repo and db_filtered:
                for doc in db_filtered:
                    for grupo in doc.get("grupos", []):
                        full_text_docs += clean_text_optimized(str(grupo.get('contenido_texto', ''))) + "\n"
            
            # Leer PDFs subidos
            if uploaded_pdfs:
                for pdf in uploaded_pdfs:
                    try:
                        with fitz.open(stream=pdf.getvalue(), filetype="pdf") as doc:
                            for page in doc:
                                full_text_docs += clean_text_optimized(page.get_text()) + "\n"
                    except: pass
            
            # CORTE DE SEGURIDAD PARA FREE TIER
            # Gemini Flash tiene 1M tokens, pero para ir rápido limitamos caracteres
            limit_chars = 30000 
            if len(full_text_docs) > limit_chars:
                full_text_docs = full_text_docs[:limit_chars] + "...[truncado]"
                status.write(f"⚠️ Texto truncado a {limit_chars} caracteres para velocidad.")

            # 2. GENERACIÓN DE TEXTO (Modelo Flash)
            status.write("🤖 Generando análisis (Modelo Flash)...")
            
            # Prompt simplificado
            prompt_text = f"""
            Analiza: '{trend_topic}'.
            Basado en estos documentos: 
            {full_text_docs}
            
            Genera un reporte ejecutivo breve (máximo 400 palabras) con:
            1. Hallazgos clave.
            2. Oportunidades detectadas.
            3. Recomendación estratégica.
            """
            
            try:
                # IMPORTANTE: Asegúrate de que 'call_gemini_stream' use internamente
                # un modelo como 'gemini-1.5-flash'. Si no puedes cambiarlo en services,
                # usa call_gemini_api estándar.
                
                # Simulamos stream collection
                full_response = ""
                stream = call_gemini_stream(prompt_text) 
                
                response_container = st.empty()
                if stream:
                    for chunk in stream:
                        full_response += chunk
                        response_container.markdown(full_response + "▌")
                    response_container.markdown(full_response)
                else:
                    raise Exception("Stream vacío")

                st.session_state.mode_state["trend_result"] = full_response
                
                # Pausa técnica para evitar error 429 (Too Many Requests)
                time.sleep(2) 

                # 3. GENERACIÓN DE GRÁFICO (Económica)
                status.write("📊 Creando datos visuales...")
                
                prompt_chart = f"""
                Del siguiente texto, extrae 4 tendencias para una matriz:
                TEXTO: {full_response}
                
                Responde SOLO JSON:
                [
                 {{"Tendencia": "Nombre", "Etapa": "Crecimiento", "Madurez": 8, "Impacto": 9}}
                ]
                """
                
                json_resp = call_gemini_api(prompt_chart) # Asegúrate que esto use Flash
                
                data = safe_json_parse(json_resp)
                if data:
                    st.session_state.mode_state["trend_chart_data"] = pd.DataFrame(data)
                else:
                    # FALLBACK: Datos dummy si falla el JSON para que NO se rompa
                    st.warning("No se pudo generar el gráfico automático. Usando ejemplo.")
                    st.session_state.mode_state["trend_chart_data"] = pd.DataFrame([
                        {"Tendencia": "Analizada", "Etapa": "Crecimiento", "Madurez": 5, "Impacto": 8}
                    ])

                st.session_state.mode_state["trend_topic"] = trend_topic
                st.rerun()

            except Exception as e:
                status.update(label="Error", state="error")
                st.error(f"Ocurrió un error: {str(e)}")
                st.info("💡 Consejo: Si usas la versión gratuita, espera 1 minuto e intenta de nuevo.")
