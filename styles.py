import streamlit as st

TABS_CSS = """
<style>
     /* Contenedor principal de las pestañas */
     div[data-testid="stTabs"] > div[role="tablist"] {
         border-bottom: 1px solid #e0e0e0;
         gap: 5px;
         padding-bottom: 0px;
     }

     /* Botones individuales de las pestañas (inactivas) */
     button[data-baseweb="tab"] {
         border: 1px solid #e0e0e0;
         border-bottom: none;
         border-radius: 8px 8px 0 0;
         padding: 10px 18px !important;
         margin: 0px;
         background-color: #f0f0f0;
         color: #555;
         transition: background-color 0.2s ease, color 0.2s ease;
         position: relative;
         bottom: -1px;
     }

     /* Efecto hover en pestañas inactivas */
     button[data-baseweb="tab"]:not([aria-selected="true"]):hover {
         background-color: #e5e5e5;
         color: #333;
     }

     /* Pestaña activa */
     button[data-baseweb="tab"][aria-selected="true"] {
         background-color: white;
         border-color: #e0e0e0;
         color: #0068c9;
         font-weight: 600;
         border-bottom-color: white !important;
         z-index: 1;
     }

     /* Ocultar la línea azul indicadora por defecto */
      div[data-baseweb="tab-highlight"] {
         display: none;
     }

     /* Contenido debajo de las pestañas */
     div[data-testid="stTabContent"] {
         padding-top: 20px;
         border-top: none;
     }
</style>
"""

# --- CSS PARA EL MENÚ ESTILO GEMINI ---
HIDE_ST_STYLE = """
     <style>
     /* 1. Ocultar el menú de hamburguesa de la DERECHA (los 3 puntos de configuración) */
     #MainMenu {visibility: hidden;}

     /* 2. Ocultar el "Made with Streamlit" del pie de página */
     footer {visibility: hidden;}

     /* 3. Ocultar la barra de estado inferior */
     [data-testid="stStatusWidget"] {visibility: hidden;}
     
     /* 4. AJUSTE DEL HEADER (BARRA SUPERIOR) */
     /* No lo ocultamos (hidden), sino que lo hacemos transparente para ver el botón de la izquierda */
     header {
        background: transparent !important;
     }
     
     /* Opcional: Si quieres que la barra de colores de arriba desaparezca visualmente */
     [data-testid="stHeader"] {
        background-color: rgba(0,0,0,0);
     }
     
     /* 5. Asegurar que el botón de colapsar (la flecha/hamburguesa de la izquierda) sea visible y accesible */
     [data-testid="collapsedControl"] {
        display: block;
        color: #333; /* Color del icono */
     }
     </style>
"""

LOGIN_PAGE_CSS = """
    <style>
        [data-testid="stAppViewContainer"] > .main { padding-top: 2rem; }
        div[data-testid="stBlock"] { padding-top: 0rem; }
        div[data-testid="stVerticalBlock"] > div { gap: 0.5rem !important; }
        div[data-testid="stButton"] button {
            padding-top: 0.4rem !important;
            padding-bottom: 0.4rem !important;
            min-height: 0px !important;
            height: auto !important;
        }
        div[data-baseweb="input"] {
            padding-top: 0.2rem !important;
            padding-bottom: 0.2rem !important;
        }
    </style>
"""

def apply_styles():
    st.markdown(TABS_CSS, unsafe_allow_html=True)
    st.markdown(HIDE_ST_STYLE, unsafe_allow_html=True)

def apply_login_styles():
    st.markdown(LOGIN_PAGE_CSS, unsafe_allow_html=True)
