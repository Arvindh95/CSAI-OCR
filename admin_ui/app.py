import streamlit as st

home = st.Page("Home.py", title="Home", default=True)
client_detail = st.Page("pages/1_Client_Detail.py", title="Client Detail")
actions = st.Page("pages/2_Actions.py", title="Actions")
client_tmpls = st.Page("pages/4_Client_Templates.py", title="Client Templates")

templates = st.Page("pages/3_Templates.py", title="Templates")
annotate = st.Page("pages/5_Annotate.py", title="Annotate")

field_guide = st.Page("pages/6_Field_Strategies_Guide.py", title="Field Strategies Guide")
api_ref = st.Page("pages/7_API_Reference.py", title="API Reference")
user_manual = st.Page("pages/8_User_Manual.py", title="User Manual")

pg = st.navigation({
    "Clients": [home, client_detail, actions, client_tmpls],
    "Templates": [templates, annotate],
    "Docs": [field_guide, api_ref, user_manual],
})
pg.run()
