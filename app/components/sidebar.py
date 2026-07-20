"""
Sidebar-Komponente: Sichern/Wiederherstellen von Projekten und Globalen
Annahmen ueber Excel-Dateien.

Hintergrund: Streamlit Cloud hat kein dauerhaftes Dateisystem - neu
angelegte Projekte gehen bei einem Reboot/Redeploy verloren, wenn sie
nicht im GitHub-Repo liegen. Der Excel-Down-/Upload ist der bewusst
einfache Sicherungsweg (und fuer tabellarische Daten wie Preiskurven
ohnehin das bequemere Bearbeitungsformat als YAML).
"""

from __future__ import annotations

import streamlit as st

from app import services
from app.config import PROJECTS_DIR
from engine.io_excel import (
    excel_to_global_assumptions,
    excel_to_projects,
    global_assumptions_to_excel,
    projects_to_excel,
)
from engine.io_yaml import load_project_yaml
from texte import txt

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render_import_export() -> None:
    with st.sidebar.expander(txt("oberflaeche.sidebar_projekte_titel")):
        st.caption(txt("oberflaeche.sidebar_projekte_beschreibung"))

        st.markdown(txt("oberflaeche.sidebar_herunterladen_titel"))
        projects_dict = services.list_project_files()
        if projects_dict:
            alle_projekte = [load_project_yaml(p) for p in projects_dict.values()]
            st.download_button(
                txt("oberflaeche.sidebar_alle_projekte_excel"),
                data=projects_to_excel(alle_projekte),
                file_name="projekte.xlsx",
                mime=_XLSX_MIME,
                width="stretch",
            )
        else:
            st.caption(txt("oberflaeche.sidebar_keine_projekte"))

        st.markdown(txt("oberflaeche.sidebar_hochladen_titel"))
        uploaded_projekte = st.file_uploader(
            txt("oberflaeche.sidebar_projekte_upload_label"),
            type=["xlsx"], key="project_upload",
        )
        if uploaded_projekte and st.button(
            txt("oberflaeche.sidebar_hochgeladene_projekte_speichern"),
            type="primary", width="stretch",
        ):
            try:
                importierte = excel_to_projects(uploaded_projekte.getvalue())
                for project in importierte:
                    services.save_project(project, PROJECTS_DIR / f"{project.id}.yaml")
                st.success(txt("oberflaeche.sidebar_projekte_gespeichert", namen=", ".join(p.name for p in importierte)))
                st.rerun()
            except Exception as exc:
                st.error(txt("oberflaeche.sidebar_excel_fehler", fehler=exc))

    with st.sidebar.expander(txt("oberflaeche.sidebar_annahmen_titel")):
        st.caption(txt("oberflaeche.sidebar_annahmen_beschreibung"))

        st.markdown(txt("oberflaeche.sidebar_herunterladen_titel"))
        st.download_button(
            txt("oberflaeche.sidebar_annahmen_excel"),
            data=global_assumptions_to_excel(services.get_global_assumptions()),
            file_name="globale_annahmen.xlsx",
            mime=_XLSX_MIME,
            width="stretch",
        )

        st.markdown(txt("oberflaeche.sidebar_hochladen_titel"))
        uploaded_ga = st.file_uploader(
            txt("oberflaeche.sidebar_annahmen_upload_label"), type=["xlsx"],
            key="global_assumptions_upload",
        )
        if uploaded_ga and st.button(
            txt("oberflaeche.sidebar_annahmen_uebernehmen"),
            type="primary", width="stretch",
        ):
            try:
                neue_ga = excel_to_global_assumptions(uploaded_ga.getvalue())
                services.save_global_assumptions(neue_ga)
                st.success(txt("oberflaeche.sidebar_annahmen_uebernommen"))
                st.rerun()
            except Exception as exc:
                st.error(txt("oberflaeche.sidebar_excel_fehler", fehler=exc))
