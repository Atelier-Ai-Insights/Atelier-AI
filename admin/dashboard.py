import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt

# Importación segura
try:
    from services.supabase_db import supabase, supabase_admin_client
except ImportError:
    st.error("Error crítico: No se pudieron cargar los servicios de base de datos.")
    st.stop()

# =====================================================
# DASHBOARD REPOSITORIO
# =====================================================
def show_repository_dashboard(db_full):
    st.subheader("Dashboard de Tendencias del Repositorio")
    if not db_full:
        st.warning("No hay datos en el repositorio.")
        return

    try:
        df = pd.DataFrame(db_full)
        df['marca'] = df['marca'].fillna('Sin Año').astype(str)
        df['filtro'] = df['filtro'].fillna('Sin Marca').astype(str)
        df['cliente'] = df['cliente'].fillna('Sin Cliente').astype(str)
    except Exception as e:
        st.error(f"Error procesando datos: {e}"); return
            
    # Gráficos simples y nativos
    st.markdown("#### Distribución por Año")
    st.bar_chart(df['marca'].value_counts().sort_index())

    st.divider()
    st.markdown("**Estudios por Cliente**")
    try:
        counts = df['cliente'].value_counts()
        if not counts.empty:
            st.bar_chart(counts) # Usamos nativo para evitar error de matplotlib
        else:
            st.info("Sin datos de clientes.")
    except: pass

    st.divider()
    st.markdown("**Estudios por Marca**")
    st.dataframe(df['filtro'].value_counts(), use_container_width=True)

# =====================================================
# PANEL DE ADMINISTRACIÓN (VERSIÓN DESBLOQUEADA)
# =====================================================
def show_admin_dashboard(db_full): 
    if not supabase_admin_client:
        st.error("⚠️ Falta configuración de SUPABASE_SERVICE_KEY.")
        return

    st.title("Panel de Control")
    
    # Pestañas
    tab_stats, tab_users, tab_repo = st.tabs(["Estadísticas", "Usuarios", "Repositorio"])

    # --- PESTAÑA 1: ESTADÍSTICAS ---
    with tab_stats:
        try:
            # Indicador de carga simple
            with st.spinner("Cargando métricas..."):
                stats_res = supabase.table("queries").select("user_name, total_tokens, timestamp").execute()
                
                if stats_res.data:
                    df = pd.DataFrame(stats_res.data)
                    total_qs = len(df)
                    total_tok = df['total_tokens'].fillna(0).sum()
                    cost = (total_tok / 1_000_000) * 0.30
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Consultas", total_qs)
                    c2.metric("Tokens", f"{total_tok:,.0f}")
                    c3.metric("Costo Aprox.", f"${cost:.4f}")
                    
                    st.divider()
                    st.caption("Últimas 10 consultas:")
                    st.dataframe(df.sort_values("timestamp", ascending=False).head(10), use_container_width=True)
                else:
                    st.info("No hay datos de uso aún.")
        except Exception as e:
            st.error(f"Error en estadísticas: {e}")

    # --- PESTAÑA 2: USUARIOS (AQUÍ ESTABA EL ERROR) ---
    with tab_users:
        st.subheader("Directorio de Usuarios")
        
        # 1. Formulario de Invitación (Simplificado)
        with st.expander("✉️ Enviar Invitación", expanded=False):
            with st.form("simple_invite"):
                email = st.text_input("Email")
                if st.form_submit_button("Invitar"):
                    try:
                        supabase_admin_client.auth.admin.invite_user_by_email(
                            email, options={"redirect_to": "https://atelier-ai.streamlit.app"}
                        )
                        st.success(f"Invitado: {email}")
                    except Exception as e:
                        st.error(f"Error: {e}")

        # 2. Lista de Usuarios (VERSIÓN SEGURA: Solo lectura)
        # Quitamos st.data_editor porque estaba colgando la app
        try:
            users = supabase_admin_client.table("users").select("email, created_at, rol, client_id").execute()
            if users.data:
                df_u = pd.DataFrame(users.data)
                st.write("Lista de usuarios registrados:")
                st.dataframe(df_u, use_container_width=True)
            else:
                st.info("No hay usuarios.")
        except Exception as e:
            st.warning(f"No se pudo cargar la lista de usuarios: {e}")

    # --- PESTAÑA 3: REPOSITORIO ---
    with tab_repo:
        show_repository_dashboard(db_full)
