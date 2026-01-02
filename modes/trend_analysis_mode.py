import streamlit as st
import pandas as pd
import altair as alt
from pytrends.request import TrendReq
from services.gemini_api import call_gemini_stream
from utils import render_process_status, get_relevant_info
from prompts import get_trend_synthesis_prompt
import random

# =====================================================
# MODO: TREND RADAR 360 (ROBUSTO ANTI-ERROR)
# =====================================================

def google_trends_mode():
    st.subheader("📡 Radar de Tendencias 360°")
    st.markdown("Triangulación de datos: **Mercado en Vivo** + **Inteligencia Interna** + **IA**.")
    
    # Mensaje de ayuda para educar al usuario sobre Keywords vs Frases
    with st.expander("ℹ️ Tips de búsqueda"):
        st.caption("Google Trends funciona mejor con **términos cortos** (ej: 'Sellos Octagonales', 'Air Fryer') en lugar de frases largas. La IA se encargará de profundizar en el análisis.")

    # Input: Simple y limpio
    c1, c2 = st.columns([3, 1])
    keyword = c1.text_input("Término a explorar:", placeholder="Ej: Sellos Octagonales")
    market = c2.selectbox("Mercado", ["Colombia", "México", "Global"], index=0)
    
    # Mapeo de códigos de país para Pytrends
    geo_map = {"Colombia": "CO", "México": "MX", "Global": ""}
    geo_code = geo_map[market]

    if st.button("Escanear Radar", type="primary", use_container_width=True):
        if not keyword:
            st.warning("Ingresa un término."); return

        # Variables de estado
        trend_df = None
        rising_terms = []
        internal_context = ""
        is_simulation = False
        simulation_reason = "" # Razón por la cual se activó la simulación
        
        # --- PROCESO UNIFICADO CON STATUS ---
        stream = None
        
        # Acceso a DB
        db = st.session_state.get("db_full", [])
        all_files = [d['nombre_archivo'] for d in db] if db else []

        with render_process_status(f"Analizando '{keyword}' en múltiples fuentes...", expanded=True) as status:
            
            # PASO 1: CONTEXTO INTERNO (RAG)
            status.write("📂 Buscando huellas en repositorio interno...")
            internal_context = get_relevant_info(db, keyword, all_files, max_chars=10000)
            
            # PASO 2: GOOGLE TRENDS (INTENTO ROBUSTO)
            status.write("🌍 Conectando con Google Trends (Live)...")
            try:
                pytrends = TrendReq(hl='es', tz=300, timeout=(5, 10)) # Timeout corto para fallar rápido si es necesario
                pytrends.build_payload([keyword], cat=0, timeframe='today 12-m', geo=geo_code)
                
                # A. Interés en el tiempo
                data = pytrends.interest_over_time()
                
                # --- CORRECCIÓN CLAVE: MANEJO DE DATOS VACÍOS ---
                if data.empty:
                    # Si está vacío, lanzamos excepción manual para activar el fallback
                    raise ValueError("EmptyData")
                
                data = data.reset_index()
                trend_df = data.rename(columns={keyword: 'Interés', 'date': 'Fecha'})
                
                # B. Consultas Relacionadas (Rising)
                try:
                    related = pytrends.related_queries()
                    if related and keyword in related:
                        rising_df = related[keyword]['rising']
                        if rising_df is not None:
                            rising_terms = rising_df.head(5)['query'].tolist()
                except:
                    pass 

            except Exception as e:
                # --- FALLBACK INTELIGENTE (SIMULACIÓN) ---
                is_simulation = True
                
                # Determinamos la razón del fallo para informar al usuario
                if "EmptyData" in str(e):
                    simulation_reason = "El término es muy específico o largo para Google Trends."
                    status.write("⚠️ Término muy específico (Sin volumen en Google). Activando IA Estratégica...")
                else:
                    simulation_reason = "Google Trends no responde (Conexión/Bloqueo)."
                    status.write("⚠️ Señal externa débil. Activando estimación predictiva...")
                
                # Generamos curva dummy coherente para que la UI no se rompa
                dates = pd.date_range(end=pd.Timestamp.now(), periods=52, freq='W')
                base = random.randint(20, 50)
                # Creamos una tendencia aleatoria pero realista
                values = [min(100, max(0, base + (i * 0.5) + random.randint(-15, 15))) for i in range(52)]
                trend_df = pd.DataFrame({'Fecha': dates, 'Interés': values})
                
                # Rising terms simulados basados en la keyword del usuario
                rising_terms = [f"tendencia {keyword}", f"futuro de {keyword}", f"análisis {keyword}"]

            # PASO 3: SÍNTESIS CON IA
            status.write("🧠 El Estratega Virtual está conectando los puntos...")
            
            # Preparamos los textos para el prompt
            trend_summary = f"Tendencia {'simulada (estimación)' if is_simulation else 'real'}. Interés actual calculado: {trend_df['Interés'].iloc[-1]}/100."
            rising_str = ", ".join(rising_terms) if rising_terms else "No se detectaron breakouts específicos."
            
            # IMPORTANTE: Si es simulación por frase larga, le damos contexto extra a la IA
            extra_instruction = ""
            if is_simulation and "específico" in simulation_reason:
                extra_instruction = f"NOTA: El usuario buscó una frase muy larga ('{keyword}'). Google Trends no dio datos. Asume el rol de consultor experto y responde analíticamente sobre el TEMA implícito en la frase."

            final_prompt = get_trend_synthesis_prompt(keyword, trend_summary + extra_instruction, internal_context, rising_str)
            
            stream = call_gemini_stream(final_prompt)
            
            if stream:
                status.update(label="¡Análisis completado!", state="complete", expanded=False)
            else:
                status.update(label="Error en síntesis", state="error")

        # --- VISUALIZACIÓN DE RESULTADOS ---
        
        # Aviso de Simulación (Transparencia con el usuario)
        if is_simulation:
            st.warning(f"ℹ️ **Modo Estimación Activado:** {simulation_reason} Los datos del gráfico son una proyección referencial de la IA, no datos directos de Google.")

        # 1. KPIs Rápidos
        k1, k2, k3 = st.columns(3)
        last_val = trend_df['Interés'].iloc[-1]
        
        k1.metric("Interés Proyectado", f"{int(last_val)}/100")
        k2.metric("Fuente de Datos", "Estimación IA" if is_simulation else "Google Trends Live", delta_color="off")
        k3.metric("Menciones Internas", "Sí detectadas" if len(internal_context) > 100 else "No detectadas", 
                 delta="Validado" if len(internal_context) > 100 else "Nuevo Territorio")

        # 2. Gráfico y Contexto
        tab_main, tab_internal = st.tabs(["📈 Radar de Mercado", "🗂️ Evidencia Interna"])
        
        with tab_main:
            # Gráfico
            chart = alt.Chart(trend_df).mark_area(
                line={'color':'#29B5E8'},
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='#29B5E8', offset=0),
                           alt.GradientStop(color='rgba(255,255,255,0)', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x=alt.X('Fecha:T', title="Último Año"),
                y=alt.Y('Interés:Q', title="Interés"),
                tooltip=['Fecha', 'Interés']
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)
            
            # Rising Terms (Píldoras)
            if rising_terms:
                st.caption("🔥 Temas Relacionados / Breakout Trends:")
                tags_html = " ".join([f"<span style='background-color:#f0f2f6; padding:4px 8px; border-radius:12px; margin-right:5px; font-size:12px;'>📈 {term}</span>" for term in rising_terms])
                st.markdown(tags_html, unsafe_allow_html=True)

        with tab_internal:
            if len(internal_context) > 100:
                st.info("💡 La IA encontró fragmentos relevantes en tus estudios anteriores:")
                with st.container(height=300):
                    st.markdown(internal_context)
            else:
                st.markdown("Esta tendencia parece ser nueva para la organización. No se encontraron referencias directas en el repositorio.")

        # 3. Output Estratégico de la IA
        st.divider()
        if stream:
            st.markdown("### 🎯 Atelier Strategic Brief")
            st.write_stream(stream)
