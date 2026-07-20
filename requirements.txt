# Laufzeit-Abhängigkeiten für Streamlit Cloud.
# (Entwickler nutzen stattdessen: pip install -e ".[dev]" – siehe pyproject.toml)
#
# WICHTIG zu pyarrow: Version 25.0.0 hat einen reproduzierbaren
# Segmentation-Fault-Bug beim Rendern von st.dataframe() (getestet gegen
# numpy 2.5.1 / pandas 3.0.3). Die Versionen 21, 23 und 24 sind stabil.
# Deshalb pyarrow < 25 explizit ausschliessen, alles andere aktuell halten
# (Python 3.14 auf Streamlit Cloud braucht moderne Wheels).
pydantic>=2.10
pandas>=2.2
numpy>=1.26
pyarrow>=20,<25
numpy-financial>=1.0
scipy>=1.13
pyyaml>=6.0
openpyxl>=3.1
streamlit>=1.40
plotly>=5.20
matplotlib>=3.8
reportlab>=4.0
