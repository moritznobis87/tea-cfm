"""
Seite "Neues Projekt": Projektmaske ausfuellen, speichern und direkt das
Ergebnis-Dashboard des neuen Projekts anzeigen.
"""

from __future__ import annotations

import streamlit as st

from app import services
from app.components.project_form import render_project_form
from app.config import STATE_SELECTED_PROJECT
from app.views.project_detail import render_project_dashboard
from texte import txt


def render_new_project() -> None:
    st.subheader(txt("oberflaeche.neues_projekt_anlegen_titel"))
    st.caption(txt("oberflaeche.neues_projekt_hilfe"))

    project = render_project_form(existing=None, form_key="neues_projekt")
    if project is None:
        return

    save_path = services.save_project(project)
    st.session_state[STATE_SELECTED_PROJECT] = project.id

    st.success(txt("oberflaeche.projekt_angelegt_erfolg", name=project.name))
    st.divider()
    render_project_dashboard(
        project, services.get_global_assumptions(), save_path
    )
