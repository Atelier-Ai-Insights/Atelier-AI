import streamlit as st
import pandas as pd
import altair as alt
from pytrends.request import TrendReq # Requiere pip install pytrends
from services.gemini_api import call_gemini_stream
import time

# =====================================================
# MODO: TREND PULSE (GOOGLE TRENDS DIRECTO)
# =====================================================

def google_trends_mode():
    st.subheader("⚡ Market Pulse (Google Trends Live)")
    st.info("Este modo conecta directamente con Google Trends. Cero consumo de tokens en lectura de documentos.")

    # Input simple
    keyword = st.text_input("Término de búsqueda:", placeholder="Ej: Ayuno Intermitente")
    
    if st.button("Analizar Tendencia", type="primary"):
        if not keyword:
            st.warning("Ingresa un término."); return

        with st.status("📡 Conectando con Google Trends...", expanded=True) as status:
            
            # 1. OBTENCIÓN DE DATOS (GRATIS - SIN IA)
            try:
                pytrends = TrendReq(hl='es-ES', tz=360)
                # Construir payload (últimos 12 meses)
                pytrends.build_payload([keyword], cat=0, timeframe='today 12-m')
                
                # Obtener interés en el tiempo
                data = pytrends.interest_over_time()
                
                if data.empty:
                    status.update(label="Sin datos", state="error")
                    st.error(f"No hay suficientes datos de búsqueda para '{keyword}'.")
                    return
                
                # Limpieza básica para el gráfico
                data = data.reset_index()
                data = data.rename(columns={keyword: 'Interés', 'date': 'Fecha'})
                
                status.write("✅ Datos obtenidos. Generando gráfico nativo...")

            except Exception as e:
                status.update(label="Error de conexión", state="error")
                st.error("Google Trends rechazó la conexión (posible límite de tasa). Intenta en 1 minuto.")
                # Fallback: Datos simulados para que veas la UI funcionar
                data = pd.DataFrame({
                    'Fecha': pd.date_range(start='1/1/2023', periods=12, freq='M'),
                    'Interés': [20, 35, 40, 60, 55, 70, 85, 90, 80, 75, 95, 100]
                })
            
            # 2. VISUALIZACIÓN (GRATIS - SIN IA)
            # Usamos Altair directo sobre los datos. Costo de tokens = 0.
            
            chart = alt.Chart(data).mark_area(
                line={'color':'#FF4B4B'},
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='#FF4B4B', offset=0),
                           alt.GradientStop(color='white', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x=alt.X('Fecha:T', title="Tiempo"),
                y=alt.Y('Interés:Q', title="Interés de Búsqueda (0-100)"),
                tooltip=['Fecha', 'Interés']
            ).properties(
                title=f"Interés en el tiempo: {keyword}",
                height=300
            ).interactive()
            
            st.altair_chart(chart, use_container_width=True)

            # 3. INTERPRETACIÓN (MÍNIMO COSTO DE IA)
            # Solo enviamos un resumen estadístico, no documentos enteros.
            status.write("🧠 Interpretando datos con Gemini...")
            
            # Calculamos métricas simples para darle masticado a la IA
            mean_interest = data['Interés'].mean()
            last_interest = data['Interés'].iloc[-1]
            trend_direction = "Al alza" if last_interest > mean_interest else "A la baja"
            
            prompt = f"""
            Actúa como analista de datos.
            El término "{keyword}" tiene estos datos en Google Trends (últimos 12 meses):
            - Interés Promedio: {mean_interest:.1f}/100
            - Interés Actual: {last_interest}/100
            - Tendencia general: {trend_direction}
            
            Dame 3 bullet points muy breves explicando qué podría significar esto para un negocio.
            No inventes datos, solo interpreta la tendencia.
            """
            
            stream = call_gemini_stream(prompt)
            
            status.update(label="¡Listo!", state="complete", expanded=False)
            
            st.markdown("### 🔍 Interpretación Rápida")
            response_container = st.empty()
            full_text = ""
            for chunk in stream:
                full_text += chunk
                response_container.markdown(full_text + "▌")
            response_container.markdown(full_text)
