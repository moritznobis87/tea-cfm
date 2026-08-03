"""
Seite "Neues Projekt": Projektmaske in voller Breite, danach direkt auf
die Projektseite.

Warum hier weiterhin ein Formular mit Absenden-Knopf und nicht die
Parameterspalte: Das Anlegen ist ein abgeschlossener Vorgang mit einem
Ergebnis ("das Projekt existiert jetzt"), kein Ausprobieren an einem
vorhandenen Projekt. Die Arbeit am Ergebnis beginnt danach - und die
findet auf der Projektseite statt, wo Eingabe und Ergebnis nebeneinander
stehen.
"""

from __future__ import annotations

import streamlit as st

from app import router, services
from app.components.project_form import render_project_form
from app.config import STATE_SELECTED_PROJECT
from texte import txt


def render_new_project() -> None:
    st.subheader(txt("oberflaeche.neues_projekt_anlegen_titel"))
    st.caption(txt("oberflaeche.neues_projekt_hilfe"))

    project = render_project_form(existing=None, form_key="neues_projekt")
    if project is None:
        return

    services.save_project(project)
    st.session_state[STATE_SELECTED_PROJECT] = project.id
    router.gehe_zu("projekt", projekt_id=project.id)
