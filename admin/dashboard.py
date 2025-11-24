import streamlit as st
import pandas as pd
from services.supabase_db import supabase, supabase_admin_client
import altair as alt 

# =====================================================
# FUNCIÓN DEL DASHBOARD DEL REPOSITORIO
# =====================================================
def show_repository_dashboard(db_full):
    st.subheader("Dashboard de Tendencias del Repositorio")
    st.markdown("Una vista de helicóptero de todo el conocimiento en la base de datos.")

    if not db_full:
        st.warning("No hay datos en el repositorio para analizar.")
        return

    # --- 1. Preparar Datos ---
    try:
        df = pd.DataFrame(db_full)
        df['marca'] = df['marca'].fillna('Sin Año').astype(str)
        df['filtro'] = df['filtro'].fillna('Sin Marca').astype(str)
        df['cliente'] = df['cliente'].fillna('Sin Cliente').astype(str)
        
    except Exception as e:
        st.error(f"Error al procesar los datos del repositorio: {e}")
        return
            
    # --- 2. Mostrar Gráficos ---
    st.markdown("#### Distribución de Estudios")
    
    st.markdown("**Estudios por Año**")
    year_counts = df['marca'].value_counts().sort_index()
    st.bar_chart(year_counts)

    st.divider()
    
    st.markdown("**Estudios por Cliente**")
    try:
        cliente_counts_series = df['cliente'].value_counts()
        cliente_counts_df = cliente_counts_series.reset_index()
        cliente_counts_df.columns = ['Cliente', 'Conteo']
        
        if not cliente_counts_df.empty:
            base = alt.Chart(cliente_counts_df).encode(theta=alt.Theta("Conteo:Q", stack=True))
            pie = base.mark_arc(outerRadius=120).encode(
                color=alt.Color("Cliente:N"),
                order=alt.Order("Conteo:Q", sort="descending"),
                tooltip=["Cliente", "Conteo"]
            )
            text = base.mark_text(radius=140).encode(
                text=alt.Text("Conteo:Q", format=".1%"),
                order=alt.Order("Conteo:Q", sort="descending"),
                color=alt.value("black") 
            )
            st.altair_chart(pie + text, width='stretch')
        else:
            st.info("No hay datos de clientes.")
    except Exception as e: st.error(f"Error gráfico pastel: {e}")

    st.divider()

    st.markdown("**Estudios por Marca**")
    filtro_counts = df['filtro'].value_counts().reset_index()
    filtro_counts.columns = ['Marca', 'Conteo']
    st.dataframe(filtro_counts.set_index('Marca'), width='stretch')


# =====================================================
# PANEL DE ADMINISTRACIÓN (CON INVITADOR AUTOMÁTICO)
# =====================================================
def show_admin_dashboard(db_full): 
    if not supabase_admin_client:
        st.error("⚠️ Error de Configuración: No se encontró 'SUPABASE_SERVICE_KEY'. No puedes gestionar usuarios sin ella.")
        return

    tab_stats, tab_users, tab_repo = st.tabs(["Estadísticas", "Gestión Usuarios", "Repositorio"])

    # --- PESTAÑA 1: ESTADÍSTICAS ---
    with tab_stats:
        st.subheader("Estadísticas de Uso y Consumo", divider="grey")
        with st.spinner("Cargando estadísticas..."):
            try:
                stats_response = supabase.table("queries").select("user_name, mode, timestamp, total_tokens").execute()
                
                if stats_response.data:
                    df_stats = pd.DataFrame(stats_response.data)
                    df_stats['timestamp'] = pd.to_datetime(df_stats['timestamp']).dt.tz_localize(None)
                    
                    if 'total_tokens' in df_stats.columns:
                        df_stats['total_tokens'] = df_stats['total_tokens'].fillna(0).astype(int)
                    else: df_stats['total_tokens'] = 0 

                    total_queries = len(df_stats)
                    total_tokens = df_stats['total_tokens'].sum()
                    est_cost = (total_tokens / 1_000_000) * 0.30 

                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total Consultas", total_queries)
                    m2.metric("Tokens Procesados", f"{total_tokens:,.0f}")
                    m3.metric("Costo Aprox ($USD)", f"${est_cost:.4f}")
                    st.divider()

                    st.write("**Top Usuarios (Consumo)**")
                    user_tokens = df_stats.groupby('user_name')['total_tokens'].sum().reset_index().sort_values(by="total_tokens", ascending=False)
                    st.dataframe(user_tokens, width='stretch', hide_index=True)

                    st.divider()
                    st.write("**Consumo por Modo**")
                    mode_tokens = df_stats.groupby('mode')['total_tokens'].sum().reset_index()
                    
                    base = alt.Chart(mode_tokens).encode(theta=alt.Theta("total_tokens:Q", stack=True))
                    pie = base.mark_arc(outerRadius=120).encode(
                        color=alt.Color("mode:N"), tooltip=["mode", "total_tokens"]
                    )
                    st.altair_chart(pie, width='stretch')
                else: st.info("Sin datos de uso.")
            except Exception as e: st.error(f"Error stats: {e}")

    # --- PESTAÑA 2: GESTIÓN DE USUARIOS E INVITACIONES (MEJORADO) ---
    with tab_users:
        
        # SECCIÓN A: INVITAR USUARIO (NUEVO - SOLUCIÓN AL PROBLEMA DE NULL)
        st.subheader("📩 Invitar Usuario Nuevo", divider="blue")
        st.info("Usa esto para enviar un correo de invitación oficial. El usuario quedará vinculado automáticamente a la empresa seleccionada.")
        
        # 1. Cargar lista de clientes para el dropdown
        try:
            clients_data = supabase_admin_client.table("clients").select("id, client_name").execute().data
            client_options = {c['client_name']: c['id'] for c in clients_data} if clients_data else {}
        except: client_options = {}

        with st.form("invite_user_form"):
            col_inv_1, col_inv_2 = st.columns(2)
            new_email = col_inv_1.text_input("Correo electrónico del usuario")
            target_client_name = col_inv_2.selectbox("Asignar a Empresa (Cliente)", list(client_options.keys()))
            
            btn_invite = st.form_submit_button("Enviar Invitación", type="primary")
            
            if btn_invite:
                if new_email and target_client_name:
                    target_client_id = client_options[target_client_name]
                    try:
                        # AQUÍ ESTÁ LA MAGIA: Enviamos el client_id dentro de la metadata
                        invite_res = supabase_admin_client.auth.admin.invite_user_by_email(
                            new_email,
                            options={
                                "data": { "client_id": target_client_id }, # Esto arregla el NULL
                                "redirect_to": "https://atelier-ai.streamlit.app"
                            }
                        )
                        st.success(f"✅ Invitación enviada a **{new_email}** para la empresa **{target_client_name}**.")
                        st.caption("El usuario aparecerá en la tabla de abajo una vez acepte el correo.")
                    except Exception as e:
                        if "already created" in str(e):
                            st.warning("El usuario ya existe. Intenta editar su rol abajo.")
                        else:
                            st.error(f"Error al invitar: {e}")
                else:
                    st.warning("Faltan datos.")

        # SECCIÓN B: GESTIÓN DE CLIENTES (CÓDIGOS)
        st.divider()
        with st.expander("🏢 Gestión de Empresas y Códigos", expanded=False):
            try:
                clients_resp = supabase_admin_client.table("clients").select("*").order("created_at", desc=True).execute()
                if clients_resp.data: 
                    st.dataframe(pd.DataFrame(clients_resp.data)[['client_name', 'invite_code', 'plan']], width='stretch')
                
                st.write("**Crear Nueva Empresa**")
                c1, c2, c3, c4 = st.columns([2,2,2,1])
                n_name = c1.text_input("Nombre Empresa")
                n_plan = c2.selectbox("Plan", ["Explorer", "Strategist", "Enterprise"])
                n_code = c3.text_input("Código Invitación")
                if c4.button("Crear"):
                    supabase_admin_client.table("clients").insert({"client_name": n_name, "plan": n_plan, "invite_code": n_code}).execute()
                    st.rerun()
            except Exception as e: st.error(f"Error clientes: {e}")

        # SECCIÓN C: TABLA DE USUARIOS (EDICIÓN)
        st.divider()
        st.subheader("👥 Usuarios Registrados")
        try:
            users_resp = supabase_admin_client.table("users").select("id, email, created_at, rol, client_id, clients(client_name)").order("created_at", desc=True).execute()

            if users_resp.data:
                user_list = []
                for user in users_resp.data:
                    client_info = user.get('clients')
                    client_name = client_info.get('client_name', "⛔ SIN ASIGNAR") if client_info else "⛔ SIN ASIGNAR"
                        
                    user_list.append({
                        'id': user.get('id'), 
                        'email': user.get('email'), 
                        'rol': user.get('rol', 'user'), 
                        'empresa': client_name,
                        'client_id': user.get('client_id'), # Oculto para lógica
                        'creado': pd.to_datetime(user.get('created_at')).strftime('%Y-%m-%d')
                    })
                    
                df_users = pd.DataFrame(user_list)
                
                # Editor de datos
                edited_df = st.data_editor(
                    df_users,
                    column_config={
                        "id": None, "client_id": None,
                        "rol": st.column_config.SelectboxColumn("Rol", options=["user", "admin"], required=True),
                        "email": st.column_config.TextColumn("Email", disabled=True),
                        "empresa": st.column_config.TextColumn("Empresa (Solo lectura)", disabled=True)
                    },
                    hide_index=True,
                    key="user_editor",
                    width='stretch'
                )
                
                # Guardar cambios de Rol
                if st.button("Guardar Cambios de Rol"):
                    # Lógica simplificada de actualización (comparar con original no incluido por brevedad, actualiza todo)
                    # En producción idealmente comparamos cambios.
                    for index, row in edited_df.iterrows():
                        try:
                            supabase_admin_client.table("users").update({"rol": row['rol']}).eq("id", row['id']).execute()
                        except: pass
                    st.success("Roles actualizados.")
                    st.rerun()
            else:
                st.info("No hay usuarios.")
        except Exception as e:
            st.error(f"Error cargando usuarios: {e}")

    # --- PESTAÑA 3: REPOSITORIO ---
    with tab_repo:
        show_repository_dashboard(db_full)
