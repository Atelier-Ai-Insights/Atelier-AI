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
# PANEL DE ADMINISTRACIÓN (OPTIMIZADO)
# =====================================================
def show_admin_dashboard(db_full): 
    if not supabase_admin_client:
        st.error("⚠️ Error: Falta la 'SUPABASE_SERVICE_KEY' en la configuración.")
        return

    st.title("Panel de Control")
    
    # 1. AJUSTE: Solo 2 pestañas (Quitamos Repositorio)
    tab_stats, tab_users = st.tabs(["Reporte de Consumo", "Gestión de Usuarios"])

    # --- PESTAÑA 1: ESTADÍSTICAS (La tabla importante) ---
    with tab_stats:
        st.subheader("Auditoría de Búsquedas y Costos")
        
        try:
            with st.spinner("Cargando registro de consultas..."):
                # 1. Cargar Datos Crudos
                # Traemos 'queries' (la tabla más importante)
                queries_res = supabase.table("queries").select("user_name, mode, query, timestamp, total_tokens").execute()
                # Traemos 'users' para saber el client_id
                users_res = supabase_admin_client.table("users").select("email, client_id").execute()
                # Traemos 'clients' para saber el nombre de la empresa
                clients_res = supabase_admin_client.table("clients").select("id, client_name").execute()

                if queries_res.data:
                    # Crear DataFrames
                    df_q = pd.DataFrame(queries_res.data)
                    df_u = pd.DataFrame(users_res.data) if users_res.data else pd.DataFrame()
                    df_c = pd.DataFrame(clients_res.data) if clients_res.data else pd.DataFrame()

                    # Limpieza básica
                    df_q['total_tokens'] = df_q['total_tokens'].fillna(0).astype(int)
                    df_q['timestamp'] = pd.to_datetime(df_q['timestamp']).dt.tz_localize(None)

                    # 2. Cruce de Datos (Joins para tener todo en una tabla maestra)
                    # Unimos Consultas con Usuarios (por email)
                    df_merged = pd.merge(df_q, df_u, left_on='user_name', right_on='email', how='left')
                    # Unimos con Clientes (por client_id)
                    df_final = pd.merge(df_merged, df_c, left_on='client_id', right_on='id', how='left')
                    
                    # Rellenar nulos visuales
                    df_final['client_name'] = df_final['client_name'].fillna('⚠️ Sin Asignar')

                    # 3. Cálculo de Costos
                    COST_PER_1M = 0.30
                    df_final['Costo ($)'] = (df_final['total_tokens'] / 1_000_000) * COST_PER_1M

                    # --- MÉTRICAS ---
                    total_tokens = df_final['total_tokens'].sum()
                    total_cost = df_final['Costo ($)'].sum()
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total Consultas", len(df_final))
                    c2.metric("Tokens Consumidos", f"{total_tokens:,.0f}")
                    c3.metric("Costo Estimado ($)", f"${total_cost:.4f}")

                    st.divider()

                    # --- TABLA PRINCIPAL (LO MÁS IMPORTANTE) ---
                    st.markdown("### 📋 Detalle de Consultas")
                    # Ordenamos por fecha descendente
                    df_display = df_final[['timestamp', 'client_name', 'user_name', 'mode', 'query', 'total_tokens', 'Costo ($)']].sort_values('timestamp', ascending=False)
                    
                    st.dataframe(
                        df_display.style.format({
                            "Costo ($)": "${:.5f}", 
                            "total_tokens": "{:,.0f}"
                        }),
                        column_config={
                            "timestamp": st.column_config.DatetimeColumn("Fecha", format="D MMM, HH:mm"),
                            "client_name": "Empresa",
                            "user_name": "Usuario",
                            "mode": "Herramienta",
                            "query": st.column_config.TextColumn("Prompt / Consulta", width="large"),
                            "total_tokens": "Tokens",
                        },
                        use_container_width=True,
                        height=600 # Altura generosa para ver bien los datos
                    )
                else:
                    st.info("No hay registros de búsquedas todavía.")

        except Exception as e:
            st.error(f"Error procesando la tabla de búsquedas: {e}")


    # --- PESTAÑA 2: USUARIOS (Invitación con Cliente) ---
    with tab_users:
        st.subheader("Gestión de Accesos")

        # 1. Obtener lista de clientes para el dropdown
        client_options = {}
        try:
            c_data = supabase_admin_client.table("clients").select("id, client_name").execute().data
            if c_data:
                # Diccionario: Nombre -> ID
                client_options = {c['client_name']: c['id'] for c in c_data}
        except: pass

        # 2. Formulario de Invitación (AJUSTE CLAVE: SELECCIÓN DE CLIENTE)
        with st.container(border=True):
            st.markdown("##### ✉️ Invitar Nuevo Usuario")
            with st.form("invite_form"):
                col1, col2 = st.columns(2)
                email = col1.text_input("Correo electrónico")
                
                # Dropdown fundamental para asociar el client_id
                empresa_selec = col2.selectbox(
                    "Asignar a Empresa", 
                    options=list(client_options.keys()) if client_options else ["Sin Empresas disponibles"]
                )

                if st.form_submit_button("Enviar Invitación", type="primary"):
                    if not email or not client_options:
                        st.warning("Faltan datos (correo o empresas configuradas).")
                    else:
                        target_id = client_options[empresa_selec]
                        try:
                            # Aquí es donde ocurre la magia: Se envía el client_id en los metadatos
                            supabase_admin_client.auth.admin.invite_user_by_email(
                                email, 
                                options={
                                    "data": { "client_id": target_id },
                                    "redirect_to": "https://atelier-ai.streamlit.app"
                                }
                            )
                            st.success(f"✅ Invitación enviada a {email} (Empresa: {empresa_selec})")
                        except Exception as e:
                            if "already created" in str(e): st.warning("Este usuario ya está registrado.")
                            else: st.error(f"Error al invitar: {e}")

        st.divider()

        # 3. Lista de Usuarios (Solo Lectura para estabilidad)
        st.markdown("##### Directorio Actual")
        try:
            users = supabase_admin_client.table("users").select("email, created_at, rol, client_id, clients(client_name)").order("created_at", desc=True).execute()
            if users.data:
                # Aplanamos el JSON para mostrar el nombre de la empresa bonito
                flat_users = []
                for u in users.data:
                    c_info = u.get('clients')
                    flat_users.append({
                        "Registrado": pd.to_datetime(u['created_at']).strftime('%Y-%m-%d'),
                        "Email": u['email'],
                        "Rol": u['rol'],
                        "Empresa": c_info['client_name'] if c_info else "⛔ Sin Asignar"
                    })
                
                st.dataframe(pd.DataFrame(flat_users), use_container_width=True)
            else:
                st.info("No hay usuarios registrados.")
        except Exception as e:
            st.warning("No se pudo cargar la lista de usuarios.")
