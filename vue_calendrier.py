"""
LE CALENDRIER DE TRESORERIE — affichage partage
Dayzon — SMD Global Consulting LLC

Le meme calendrier sert au particulier et a l'entreprise. Seul le vocabulaire
des libelles change ; la mecanique du solde jour par jour est identique.
"""

from __future__ import annotations

import calendar
from datetime import date

import pandas as pd
import streamlit as st

from commun import (MOIS_FR, construire_tresorerie, formater,
                    solde_de_depart)


def afficher_calendrier(cle: str = "part", mots: dict | None = None) -> None:
    """
    Affiche les reglages, les indicateurs, la courbe et la grille mensuelle.

    `cle` distingue les widgets entre les deux profils : deux boutons de meme
    identifiant dans une meme session provoquent une erreur Streamlit.
    """
    mots = mots or {}
    titre_bas = mots.get("point_bas", "Point bas")

    col_a, col_b, col_c = st.columns([2, 2, 3])
    with col_a:
        debut = st.date_input("À partir du", value=date.today(), key=f"deb_{cle}")
    with col_b:
        horizon = st.select_slider("Horizon", options=[30, 60, 90, 180, 365],
                                   value=90, format_func=lambda j: f"{j} jours",
                                   key=f"hor_{cle}")
    with col_c:
        inclure = st.toggle(mots.get("incertain", "Inclure les montants incertains"),
                            value=True, key=f"inc_{cle}",
                            help=mots.get("aide_incertain",
                                          "Devis, prospects, rentrées hypothétiques"))

    t = construire_tresorerie()
    jours = t.projeter(debut, horizon, inclure_incertain=inclure)
    synth = t.synthese(debut, horizon)

    # --- Indicateurs ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(mots.get("solde_actuel", "Solde aujourd'hui"),
              formater(solde_de_depart()))
    k2.metric(f"Dans {horizon} jours", formater(synth["solde_final"]),
              delta=formater(synth["variation_nette"]))
    k3.metric(titre_bas, formater(synth["solde_minimum"]),
              delta=synth["date_solde_min"].strftime("le %d/%m"), delta_color="off")

    if synth["alerte"]:
        k4.metric("⚠️ Découvert le", synth["premier_jour_negatif"].strftime("%d/%m"),
                  delta=f"dans {synth['jours_avant_negatif']} jours",
                  delta_color="inverse")
        st.error(f"**Votre solde passe sous zéro le "
                 f"{synth['premier_jour_negatif'].strftime('%d/%m/%Y')}**, soit dans "
                 f"{synth['jours_avant_negatif']} jours. "
                 f"{titre_bas} : {formater(synth['solde_minimum'])}.")
    else:
        k4.metric("Situation", "Aucun découvert", delta="sur la période",
                  delta_color="off")
        st.success(f"Aucun découvert prévu sur les {horizon} prochains jours. "
                   f"{titre_bas} : {formater(synth['solde_minimum'])} "
                   f"le {synth['date_solde_min'].strftime('%d/%m/%Y')}.")

    # --- Courbe ---
    st.subheader("Évolution du solde")
    st.line_chart(pd.DataFrame({
        "Date": [j.jour for j in jours],
        "Solde": [float(j.solde) for j in jours],
    }).set_index("Date"), height=260)

    # --- Grille mensuelle ---
    st.subheader("Calendrier — solde de fin de journée")

    par_jour = {j.jour: j for j in jours}
    for annee, mois in sorted({(j.jour.year, j.jour.month) for j in jours})[:6]:
        st.markdown(f"**{MOIS_FR[mois]} {annee}**")
        entete = st.columns(7)
        for i, nom in enumerate(["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]):
            entete[i].caption(nom)

        for semaine in calendar.Calendar(firstweekday=0).monthdatescalendar(annee, mois):
            cols = st.columns(7)
            for i, jour in enumerate(semaine):
                with cols[i]:
                    if jour.month != mois:
                        st.caption(" ")
                        continue
                    info = par_jour.get(jour)
                    if info is None:
                        st.caption(f"{jour.day}")
                        continue
                    solde = float(info.solde)
                    couleur = ("#c0392b" if solde < 0
                               else "#e67e22" if solde < 500 else "#27ae60")
                    mouvement = ""
                    if info.operations:
                        mouvement = (f"<div style='font-size:10px;color:#666'>"
                                     f"{float(info.variation):+,.0f}</div>")
                    st.markdown(
                        f"<div style='border:1px solid #e0e0e0;border-radius:6px;"
                        f"padding:4px;min-height:58px'>"
                        f"<div style='font-size:11px;color:#888'>{jour.day}</div>"
                        f"<div style='font-size:13px;font-weight:600;color:{couleur}'>"
                        f"{solde:,.0f}</div>{mouvement}</div>",
                        unsafe_allow_html=True)
        st.write("")

    # --- Detail ---
    with st.expander("Voir le détail jour par jour"):
        st.dataframe(pd.DataFrame([{
            "Date": j.jour.strftime("%d/%m/%Y"),
            "Opérations": " · ".join(j.operations) if j.operations else "",
            "Entrées": float(j.entrees) or None,
            "Sorties": float(j.sorties) or None,
            "Solde": float(j.solde),
        } for j in jours if j.operations or j.jour == debut]),
            use_container_width=True, hide_index=True)
