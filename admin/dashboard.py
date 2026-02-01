import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, timezone

# Importación segura
try:
    from services.supabase_db import supabase, supabase_admin_client
except ImportError:
    st.error("Error crítico: No se pudieron cargar los servicios de base de datos.")
    st.stop()

# =====================================================
# PANEL DE ADMINISTRACIÓN 2.0 (BUSINESS INTELLIGENCE)
# =====================================================
def show_admin_dashboard(db_full): 
    if not supabase_admin_client:
        st.error("⚠️ Error: Falta la 'SUPABASE_SERVICE_KEY'. No tienes permisos de administrador.")
        return

    st.title("Admin Dashboard")
    
    # --- FILTROS GLOBALES (Optimización de Carga) ---
    st.markdown("### Filtros de Periodo")
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    
    today = datetime.now()
    default_start = today - timedelta(days=30)
    
    start_date = col_f1.date_input("Fecha Inicio", default_start)
    end_date = col_f2.date_input("Fecha Fin", today)
    
    # Convertir a formato ISO para Supabase
    start_iso = start_date.strftime("%Y-%m-%dT00:00:00")
    end_iso = (end_date + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")

    # --- CARGA DE DATOS OPTIMIZADA ---
    with st.spinner("Analizando métricas de consumo..."):
        try:
            # 1. Queries (Filtradas por fecha para no explotar la RAM)
            q_res = supabase.table("queries").select("*").gte("timestamp", start_iso).lt("timestamp", end_iso).execute()
            queries_data = q_res.data
            
            # 2. Usuarios y Clientes (Tablas maestras pequeñas)
            users_data = supabase_admin_client.table("users").select("email, client_id, rol").execute().data
            clients_data = supabase_admin_client.table("clients").select("id, client_name").execute().data
            
        except Exception as e:
            st.error(f"Error conectando a Supabase: {e}")
            return

    # --- PROCESAMIENTO DE DATOS ---
    if queries_data:
        df_q = pd.DataFrame(queries_data)
        df_u = pd.DataFrame(users_data) if users_data else pd.DataFrame()
        df_c = pd.DataFrame(clients_data) if clients_data else pd.DataFrame()

        # Limpieza y Casteo
        df_q['total_tokens'] = pd.to_numeric(df_q['total_tokens'], errors='coerce').fillna(0)
        df_q['timestamp'] = pd.to_datetime(df_q['timestamp'])
        df_q['Fecha'] = df_q['timestamp'].dt.date
        
        # Cruce de tablas (Queries + Users + Clients)
        # 1. Unir Queries con Users (por email)
        df_m = pd.merge(df_q, df_u, left_on='user_name', right_on='email', how='left')
        
        # 2. Unir con Clients (por client_id)
        if not df_c.empty and 'client_id' in df_m.columns:
            # Asegurar tipos string para el merge
            df_m['client_id'] = df_m['client_id'].astype(str)
            df_c['id'] = df_c['id'].astype(str)
            df_final = pd.merge(df_m, df_c, left_on='client_id', right_on='id', how='left')
            df_final['client_name'] = df_final['client_name'].fillna('Externo / Sin Asignar')
        else:
            df_final = df_m
            df_final['client_name'] = 'N/A'
            
        # Costo estimado (Ajustable)
        COST_PER_1M_TOKENS = 0.50 # Ajusta esto según tu proveedor real
        df_final['Costo_USD'] = (df_final['total_tokens'] / 1_000_000) * COST_PER_1M_TOKENS
        
    else:
        df_final = pd.DataFrame()
        st.info("No hay datos en este rango de fechas.")

    # =================================================
    # INTERFAZ DE PESTAÑAS
    # =================================================
    tab_bi, tab_users, tab_audit = st.tabs(["Business Intelligence", "Gestión de Accesos", "Logs de Auditoría"])

    # --- TAB 1: DASHBOARD BI ---
    with tab_bi:
        if not df_final.empty:
            # 1. KPIS
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Consultas Totales", len(df_final))
            k2.metric("Tokens Procesados", f"{df_final['total_tokens'].sum()/1000:.1f}k")
            k3.metric("Costo Estimado", f"${df_final['Costo_USD'].sum():.4f}")
            k4.metric("Usuarios Activos", df_final['user_name'].nunique())
            
            st.divider()
            
            # 2. GRÁFICOS (Fila 1)
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("Evolución de Uso")
                # Agrupar por día
                daily_usage = df_final.groupby('Fecha').size().reset_index(name='Consultas')
                fig_line = px.line(daily_usage, x='Fecha', y='Consultas', markers=True, template="plotly_white")
                st.plotly_chart(fig_line, width="stretch")
                
            with c2:
                st.subheader("Costo por Empresa")
                cost_client = df_final.groupby('client_name')['Costo_USD'].sum().reset_index().sort_values('Costo_USD', ascending=False)
                fig_bar = px.bar(cost_client, x='client_name', y='Costo_USD', color='client_name', text_auto='.3f', template="plotly_white")
                st.plotly_chart(fig_bar, width="stretch")

            # 3. GRÁFICOS (Fila 2)
            c3, c4 = st.columns(2)
            
            with c3:
                st.subheader("Herramientas Más Usadas")
                mode_dist = df_final['mode'].value_counts().reset_index()
                mode_dist.columns = ['Modo', 'Consultas']
                fig_pie = px.pie(mode_dist, names='Modo', values='Consultas', hole=0.4, template="plotly_white")
                st.plotly_chart(fig_pie, width="stretch")

            with c4:
                st.subheader("Top 5 Usuarios (Gasto)")
                top_users = df_final.groupby('user_name')['Costo_USD'].sum().reset_index().sort_values('Costo_USD', ascending=False).head(5)
                fig_user = px.bar(top_users, x='Costo_USD', y='user_name', orientation='h', text_auto='.3f', template="plotly_white")
                st.plotly_chart(fig_user, width="stretch")
        else:
            st.warning("Selecciona un rango de fechas con actividad para ver los gráficos.")

    # --- TAB 2: USUARIOS (Mantenemos la lógica pero más limpia) ---
    with tab_users:
        st.subheader("Invitar Nuevo Usuario")
        
        # Mapa de empresas para el selectbox
        empresa_map = {c['client_name']: c['id'] for c in clients_data} if clients_data else {}
        
        with st.form("invitacion_rapida"):
            c_u1, c_u2 = st.columns(2)
            new_email = c_u1.text_input("Correo Electrónico")
            target_client = c_u2.selectbox("Asignar a Empresa", list(empresa_map.keys()) if empresa_map else ["Sin Empresas"])
            
            if st.form_submit_button("Enviar Invitación", type="primary"):
                if new_email and empresa_map:
                    try:
                        cid = empresa_map[target_client]
                        # Enviar invitación via Supabase Auth
                        supabase_admin_client.auth.admin.invite_user_by_email(
                            new_email, 
                            options={"data": { "client_id": cid }, "redirect_to": "https://atelier-ai.streamlit.app"}
                        )
                        st.success(f"✅ Invitación enviada a {new_email}")
                    except Exception as e:
                        st.error(f"Error al invitar: {e}")
                else:
                    st.warning("Faltan datos.")

        st.divider()
        st.subheader("Directorio de Usuarios")
        
        # Tabla de usuarios enriquecida
        if users_data:
            clean_users = []
            # Crear mapa rápido de ID -> Nombre Cliente
            id_to_name = {c['id']: c['client_name'] for c in clients_data} if clients_data else {}
            
            for u in users_data:
                # Recuperar nombre de cliente
                c_name = id_to_name.get(u.get('client_id'), "Sin Asignar")
                clean_users.append({
                    "Email": u['email'],
                    "Empresa": c_name,
                    "Rol": u.get('rol', 'user')
                })
            
            st.dataframe(pd.DataFrame(clean_users), width="stretch")

    # --- TAB 3: AUDITORÍA (Logs Crudos) ---
    with tab_audit:
        st.subheader("Registro Detallado de Consultas")
        if not df_final.empty:
            # Selector de columnas
            cols_to_show = ['timestamp', 'user_name', 'client_name', 'mode', 'query', 'total_tokens', 'Costo_USD']
            st.dataframe(
                df_final[cols_to_show].sort_values('timestamp', ascending=False),
                width="stretch",
                height=600,
                column_config={
                    "timestamp": st.column_config.DatetimeColumn("Hora", format="D MMM, HH:mm"),
                    "Costo_USD": st.column_config.NumberColumn("Costo", format="$%.4f")
                }
            )
            
            # Botón de descarga
            csv = df_final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descargar Logs (CSV)", data=csv, file_name="logs_atelier.csv", mime="text/csv")
        else:
            st.info("No hay datos para mostrar.")
