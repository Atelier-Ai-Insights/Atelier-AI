import streamlit as st
import pandas as pd

# Importación segura
try:
    from services.supabase_db import supabase, supabase_admin_client
except ImportError:
    st.error("Error crítico: No se pudieron cargar los servicios de base de datos.")
    st.stop()

# =====================================================
# PANEL DE ADMINISTRACIÓN (VERSIÓN ESTABLE)
# =====================================================
def show_admin_dashboard(db_full): 
    if not supabase_admin_client:
        st.error("⚠️ Error: Falta la 'SUPABASE_SERVICE_KEY'.")
        return

    st.title("Panel de Control")
    tab_stats, tab_users = st.tabs(["Registro de Consultas", "Gestión de Usuarios"])

    # --- PESTAÑA 1: TABLA MAESTRA DE CONSULTAS ---
    with tab_stats:
        st.subheader("Auditoría de Consumo")
        
        try:
            # 1. Cargar datos crudos
            queries = supabase.table("queries").select("*").execute().data
            users = supabase_admin_client.table("users").select("email, client_id").execute().data
            clients = supabase_admin_client.table("clients").select("id, client_name").execute().data

            if queries:
                # 2. Convertir a DataFrames
                df_q = pd.DataFrame(queries)
                df_u = pd.DataFrame(users) if users else pd.DataFrame(columns=['email', 'client_id'])
                df_c = pd.DataFrame(clients) if clients else pd.DataFrame(columns=['id', 'client_name'])

                # 3. Limpieza de datos (CRÍTICO PARA EVITAR PANTALLA BLANCA)
                # Aseguramos que los tokens sean números, si falla pone 0
                df_q['total_tokens'] = pd.to_numeric(df_q['total_tokens'], errors='coerce').fillna(0)
                
                # 4. Cruces (Merges)
                # Unimos Query con Usuario
                df_m = pd.merge(df_q, df_u, left_on='user_name', right_on='email', how='left')
                
                # Unimos con Cliente
                # Convertimos IDs a string para evitar conflictos de tipos int/object
                if not df_c.empty:
                    df_m['client_id'] = df_m['client_id'].astype(str)
                    df_c['id'] = df_c['id'].astype(str)
                    df_final = pd.merge(df_m, df_c, left_on='client_id', right_on='id', how='left')
                else:
                    df_final = df_m
                    df_final['client_name'] = 'N/A'

                # 5. Rellenar nulos
                df_final['client_name'] = df_final['client_name'].fillna('⚠️ Sin Asignar')

                # 6. Costos
                df_final['Costo'] = (df_final['total_tokens'] / 1_000_000) * 0.30

                # 7. Selección de Columnas para mostrar
                # Creamos un DF limpio solo con lo que necesitamos ver
                cols = ['timestamp', 'client_name', 'user_name', 'mode', 'query', 'total_tokens', 'Costo']
                # Validamos que existan las columnas
                valid_cols = [c for c in cols if c in df_final.columns]
                df_show = df_final[valid_cols].sort_values('timestamp', ascending=False)

                # --- MÉTRICAS ---
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Consultas", len(df_show))
                c2.metric("Tokens Totales", f"{df_show['total_tokens'].sum():,.0f}")
                c3.metric("Costo Total", f"${df_show['Costo'].sum():.4f}")

                st.divider()

                # --- RENDERIZADO SEGURO (SIN STYLE.FORMAT) ---
                st.dataframe(
                    df_show,
                    column_config={
                        "timestamp": st.column_config.DatetimeColumn("Fecha", format="D MMM YYYY, HH:mm"),
                        "client_name": "Empresa",
                        "user_name": "Usuario",
                        "mode": "Herramienta",
                        "query": st.column_config.TextColumn("Prompt", width="large"),
                        "total_tokens": st.column_config.NumberColumn("Tokens", format="%d"),
                        "Costo": st.column_config.NumberColumn("Costo USD", format="$%.5f"),
                    },
                    use_container_width=True,
                    height=500,
                    hide_index=True
                )
            else:
                st.info("No hay datos de consultas.")

        except Exception as e:
            st.error(f"Error cargando tabla: {e}")

    # --- PESTAÑA 2: USUARIOS ---
    with tab_users:
        st.subheader("Gestión de Accesos")
        
        # Obtener lista de empresas para el selectbox
        empresa_map = {}
        try:
            c_data = supabase_admin_client.table("clients").select("id, client_name").execute().data
            if c_data:
                empresa_map = {c['client_name']: c['id'] for c in c_data}
        except: pass

        # FORMULARIO
        with st.form("invitacion_segura"):
            c1, c2 = st.columns(2)
            email = c1.text_input("Correo")
            empresa = c2.selectbox("Empresa", list(empresa_map.keys()) if empresa_map else ["Sin Empresas"])
            
            if st.form_submit_button("Invitar", type="primary"):
                if email and empresa_map:
                    try:
                        cid = empresa_map[empresa]
                        supabase_admin_client.auth.admin.invite_user_by_email(
                            email, 
                            options={"data": { "client_id": cid }, "redirect_to": "https://atelier-ai.streamlit.app"}
                        )
                        st.success(f"Invitado: {email} -> {empresa}")
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Verifica los datos.")

        st.divider()

        # LISTA USUARIOS
        try:
            users_raw = supabase_admin_client.table("users").select("email, created_at, rol, clients(client_name)").order("created_at", desc=True).execute()
            if users_raw.data:
                clean_users = []
                for u in users_raw.data:
                    c = u.get('clients')
                    clean_users.append({
                        "Fecha": u['created_at'],
                        "Email": u['email'],
                        "Rol": u['rol'],
                        "Empresa": c['client_name'] if c else "Sin Asignar"
                    })
                
                st.dataframe(
                    pd.DataFrame(clean_users),
                    column_config={
                        "Fecha": st.column_config.DatetimeColumn("Registro", format="YYYY-MM-DD")
                    },
                    use_container_width=True
                )
        except Exception as e:
            st.warning(f"No se pudo cargar la lista de usuarios: {e}")
