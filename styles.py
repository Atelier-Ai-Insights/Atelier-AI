import streamlit as st

# ==============================================================================
# ESTILOS DE PESTAÑAS (TABS)
# ==============================================================================
TABS_CSS = """
<style>
     div[data-testid="stTabs"] > div[role="tablist"] {
         border-bottom: 1px solid #e0e0e0;
         gap: 5px;
         padding-bottom: 0px;
     }

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

     button[data-baseweb="tab"]:not([aria-selected="true"]):hover {
         background-color: #e5e5e5;
         color: #333;
     }

     button[data-baseweb="tab"][aria-selected="true"] {
         background-color: white;
         border-color: #e0e0e0;
         color: #0068c9;
         font-weight: 600;
         border-bottom-color: white !important;
         z-index: 1;
     }

     div[data-baseweb="tab-highlight"] {
         display: none;
     }

     div[data-testid="stTabContent"] {
         padding-top: 20px;
         border-top: none;
     }
</style>
"""

# ==============================================================================
# ESTILOS DE UI GENERAL (MENÚ GEMINI)
# ==============================================================================
HIDE_ST_STYLE = """
     <style>
     #MainMenu {visibility: hidden;}
     footer {visibility: hidden;}
     [data-testid="stStatusWidget"] {visibility: hidden;}
     
     header {
        background: transparent !important;
     }
     
     [data-testid="stHeader"] {
        background-color: rgba(0,0,0,0);
     }
     
     [data-testid="collapsedControl"] {
        display: block;
        color: #333;
     }
     </style>
"""

# ==============================================================================
# ESTILOS DE LOGIN
# ==============================================================================
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

# ==============================================================================
# ESTILOS DE CITAS (TOOLTIPS) - ESTILO ACADÉMICO / WIKIPEDIA
# ==============================================================================
TOOLTIP_CSS = """
    <style>
        /* El contenedor invisible que agrupa el [1] y la caja flotante */
        .tooltip-container {
            position: relative;
            display: inline-block;
            margin: 0 1px;
            line-height: 1;
        }

        /* El número visible [1] - Estilo Superíndice Académico */
        .citation-number {
            cursor: help;
            color: #0056b3; /* Azul Oscuro Profesional */
            font-weight: bold;
            font-size: 0.75em; /* Fuente pequeña */
            vertical-align: super; /* Arriba del renglón */
            border-bottom: 1px dotted #0056b3; /* Subrayado sutil */
            padding: 0 1px;
            border-radius: 2px;
            transition: all 0.2s ease;
        }
        
        .citation-number:hover {
            background-color: rgba(0, 86, 179, 0.1);
            color: #003d80;
            border-bottom: 1px solid #003d80;
        }

        /* El cuadro de texto flotante (Tooltip Oculto) */
        .tooltip-container .tooltip-text {
            visibility: hidden;
            width: 320px;
            background-color: #262730; /* Fondo oscuro */
            color: #e0e0e0; /* Texto claro */
            text-align: left;
            border-radius: 8px;
            padding: 12px;
            font-size: 0.85rem; /* Tamaño de letra normal para leer */
            line-height: 1.4;
            font-weight: normal;
            vertical-align: baseline; /* Reseteamos la alineación para el contenido */
            
            /* Posicionamiento */
            box-shadow: 0px 8px 16px rgba(0,0,0,0.25);
            border: 1px solid #444;
            position: absolute;
            z-index: 1000;
            bottom: 180%; /* Más arriba para no tapar el texto */
            left: 50%;
            margin-left: -160px; /* Centrado */
            
            /* Animación suave */
            opacity: 0;
            transform: translateY(10px);
            transition: opacity 0.2s ease, transform 0.2s ease;
            pointer-events: none; /* Evita clicks accidentales */
        }

        /* Flechita decorativa abajo de la caja */
        .tooltip-container .tooltip-text::after {
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            margin-left: -6px;
            border-width: 6px;
            border-style: solid;
            border-color: #262730 transparent transparent transparent;
        }

        /* Mostrar al pasar el mouse sobre el contenedor */
        .tooltip-container:hover .tooltip-text {
            visibility: visible;
            opacity: 1;
            transform: translateY(0);
        }
        
        /* Título del archivo dentro del tooltip */
        .tooltip-text strong {
            display: block;
            color: #4da6ff; /* Azul clarito para el título en fondo oscuro */
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid #555;
            padding-bottom: 4px;
            margin-bottom: 6px;
        }
    </style>
"""

# ==============================================================================
# FUNCIONES DE APLICACIÓN
# ==============================================================================

def apply_styles():
    st.markdown(TABS_CSS, unsafe_allow_html=True)
    st.markdown(HIDE_ST_STYLE, unsafe_allow_html=True)
    st.markdown(TOOLTIP_CSS, unsafe_allow_html=True)

def apply_login_styles():
    st.markdown(LOGIN_PAGE_CSS, unsafe_allow_html=True)
