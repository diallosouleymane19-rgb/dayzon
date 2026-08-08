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

import commun

from commun import (MOIS_FR, construire_tresorerie, formater,
                    solde_de_depart)


def afficher_calendrier(cle: str = "part", mots: dict | None = None) -> None:
    """
    Affiche les reglages, les indicateurs, la courbe et la grille mensuelle.

    `cle` distingue les widgets entre les deux profils : deux boutons de meme
    identifiant dans une meme session provoquent une erreur Streamlit.
    """
    mots = mots or {}
    titre_bas = mots.get("point_bas", commun.t("cal.point_bas"))

    col_a, col_b, col_c = st.columns([2, 2, 3])
    with col_a:
        debut = st.date_input(commun.t("cal.a_partir_du"), value=date.today(),
                              key=f"deb_{cle}")
    with col_b:
        horizon = st.select_slider(commun.t("cal.horizon"),
                                   options=[30, 60, 90, 180, 365], value=90,
                                   format_func=lambda j: commun.t("cal.jours", n=j),
                                   key=f"hor_{cle}")
    with col_c:
        inclure = st.toggle(mots.get("incertain", commun.t("cal.incertain")),
                            value=True, key=f"inc_{cle}",
                            help=mots.get("aide_incertain",
                                          commun.t("cal.aide_incertain")))

    t = construire_tresorerie()
    jours = t.projeter(debut, horizon, inclure_incertain=inclure)
    synth = t.synthese(debut, horizon)

    # --- Indicateurs ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(mots.get("solde_actuel", commun.t("cal.solde_aujourdhui")),
              formater(solde_de_depart()))
    k2.metric(commun.t("cal.dans_x_jours", n=horizon), formater(synth["solde_final"]),
              delta=formater(synth["variation_nette"]))
    k3.metric(titre_bas, formater(synth["solde_minimum"]),
              delta=synth["date_solde_min"].strftime("le %d/%m"), delta_color="off")

    if synth["alerte"]:
        k4.metric("⚠️ " + commun.t("cal.decouvert_le"),
                  commun.date_courte(synth["premier_jour_negatif"]),
                  delta=commun.t("cal.jours", n=synth["jours_avant_negatif"]),
                  delta_color="inverse")
        st.error(commun.t("cal.sous_zero",
                          date=commun.date_longue(synth["premier_jour_negatif"]),
                          n=synth["jours_avant_negatif"], bas=titre_bas,
                          montant=formater(synth["solde_minimum"])))
    else:
        k4.metric(commun.t("cal.situation"), commun.t("cal.aucun_decouvert"),
                  delta=commun.t("cal.sur_periode"),
                  delta_color="off")
        st.success(commun.t("cal.pas_decouvert", n=horizon, bas=titre_bas,
                            montant=formater(synth["solde_minimum"]),
                            date=commun.date_longue(synth["date_solde_min"])))

    # --- Courbe ---
    st.subheader(commun.t("cal.evolution"))
    st.line_chart(pd.DataFrame({
        commun.t("col.date"): [j.jour for j in jours],
        commun.t("col.solde"): [float(j.solde) for j in jours],
    }).set_index(commun.t("col.date")), height=260)

    # --- Grille mensuelle ---
    st.subheader(commun.t("cal.grille"))

    par_jour = {j.jour: j for j in jours}
    for annee, mois in sorted({(j.jour.year, j.jour.month) for j in jours})[:6]:
        st.markdown(f"**{commun.nom_mois(mois)} {annee}**")
        entete = st.columns(7)
        for i, nom in enumerate(commun.jours_semaine()):
            entete[i].caption(nom)

        for semaine in calendar.Calendar(firstweekday=commun.premier_jour()).monthdatescalendar(annee, mois):
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
    with st.expander(commun.t("cal.detail")):
        st.dataframe(pd.DataFrame([{
            commun.t("col.date"): commun.date_longue(j.jour),
            commun.t("col.operations"): " · ".join(j.operations) if j.operations else "",
            commun.t("col.entrees"): float(j.entrees) or None,
            commun.t("col.sorties"): float(j.sorties) or None,
            commun.t("col.solde"): float(j.solde),
        } for j in jours if j.operations or j.jour == debut]),
            use_container_width=True, hide_index=True)
