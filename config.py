import streamlit as st

# ==============================
# DEFINICIÓN DE PLANES Y PERMISOS
# ==============================
PLAN_FEATURES = {
    "Explorer": {
        "reports_per_month": 0, "chat_queries_per_day": 4, "projects_per_year": 2,
        "has_report_generation": False, "has_creative_conversation": False,
        "has_concept_generation": False, "has_idea_evaluation": False,
        "has_image_evaluation": False, "has_video_evaluation": False,
        "transcript_file_limit": 1, "ppt_downloads_per_month": 2,
        "project_upload_limit": 1, # <-- LÍNEA NUEVA
    },
    "Strategist": {
        "reports_per_month": 0, "chat_queries_per_day": float('inf'), "projects_per_year": 10,
        "has_report_generation": False, "has_creative_conversation": True,
        "has_concept_generation": True, "has_idea_evaluation": False,
        "has_image_evaluation": False, "has_video_evaluation": False,
        "transcript_file_limit": 5, "ppt_downloads_per_month": 4,
        "project_upload_limit": 5, # <-- LÍNEA NUEVA
    },
    "Enterprise": {
        "reports_per_month": float('inf'), "chat_queries_per_day": float('inf'), "projects_per_year": float('inf'),
        "has_report_generation": True, "has_creative_conversation": True,
        "has_concept_generation": True, "has_idea_evaluation": True,
        "has_image_evaluation": True, "has_video_evaluation": True,
        "transcript_file_limit": 10, "ppt_downloads_per_month": float('inf'),
        "project_upload_limit": float('inf'), # <-- LÍNEA NUEVA
    }
}

# ==============================
# CONFIGURACIÓN DE LA API DE GEMINI
# ==============================
api_keys = [st.secrets["API_KEY_1"], st.secrets["API_KEY_2"], st.secrets["API_KEY_3"]]

generation_config = {"temperature": 0.5, "top_p": 0.8, "top_k": 32, "max_output_tokens": 8192}

safety_settings = [{"category": c, "threshold": "BLOCK_ONLY_HIGH"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]

# ==============================
# CONSTANTES GLOBALES
# ==============================
banner_file = "Banner (2).jpg"