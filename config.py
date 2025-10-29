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
    },
    "Strategist": {
        "reports_per_month": 0, "chat_queries_per_day": float('inf'), "projects_per_year": 10,
        "has_report_generation": False, "has_creative_conversation": True,
        "has_concept_generation": True, "has_idea_evaluation": False,
        "has_image_evaluation": False, "has_video_evaluation": False,
        "transcript_file_limit": 5, "ppt_downloads_per_month": 4,
    },
    "Enterprise": {
        "reports_per_month": float('inf'), "chat_queries_per_day": float('inf'), "projects_per_year": float('inf'),
        "has_report_generation": True, "has_creative_conversation": True,
        "has_concept_generation": True, "has_idea_evaluation": True,
        "has_image_evaluation": True, "has_video_evaluation": True,
        "transcript_file_limit": 10, "ppt_downloads_per_month": float('inf'),
    }
}
