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
import theme

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

    # --- Le chiffre de tete ---
    # Un seul montant domine l'ecran : celui que l'utilisateur est venu
    # chercher. Le reste devient secondaire, y compris le solde du jour.
    theme.hero(commun.t("cal.dans_x_jours", n=horizon),
               formater(synth["solde_final"]),
               commun.t("cal.le_date",
                        date=commun.date_longue(synth["date_solde_min"]))
               + " · " + titre_bas + " " + formater(synth["solde_minimum"]))

    k1, k2, k3, k4 = st.columns(4)
    theme.kpi(k1, mots.get("solde_actuel", commun.t("cal.solde_aujourdhui")),
              formater(solde_de_depart()))
    theme.kpi(k2, commun.t("cal.variation"), formater(synth["variation_nette"]),
              couleur=theme.couleur_montant(synth["variation_nette"]))
    theme.kpi(k3, titre_bas, formater(synth["solde_minimum"]),
              commun.t("cal.le_date",
                       date=commun.date_courte(synth["date_solde_min"])),
              couleur=theme.couleur_montant(synth["solde_minimum"]))

    if synth["alerte"]:
        theme.kpi(k4, commun.t("cal.decouvert_le"),
                  commun.date_courte(synth["premier_jour_negatif"]),
                  commun.t("cal.jours", n=synth["jours_avant_negatif"]),
                  couleur=theme.ROUGE)
        st.write("")
        theme.message("alerte", commun.t("cal.decouvert_le") + " "
                      + commun.date_longue(synth["premier_jour_negatif"]),
                      commun.t("cal.sous_zero",
                               date=commun.date_longue(synth["premier_jour_negatif"]),
                               n=synth["jours_avant_negatif"], bas=titre_bas,
                               montant=formater(synth["solde_minimum"])))
    else:
        theme.kpi(k4, commun.t("cal.situation"),
                  commun.t("cal.aucun_decouvert"),
                  commun.t("cal.sur_periode"), couleur=theme.VERT)
        st.write("")
        theme.message("bon", commun.t("cal.aucun_decouvert"),
                      commun.t("cal.pas_decouvert", n=horizon, bas=titre_bas,
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
            entete[i].markdown(f"<div class='dz-dow'>{nom}</div>",
                               unsafe_allow_html=True)

        for semaine in calendar.Calendar(firstweekday=commun.premier_jour()).monthdatescalendar(annee, mois):
            cols = st.columns(7)
            for i, jour in enumerate(semaine):
                with cols[i]:
                    if jour.month != mois:
                        st.markdown("<div class='dz-jour vide'></div>",
                                    unsafe_allow_html=True)
                        continue
                    info = par_jour.get(jour)
                    if info is None:
                        # Avant la date de depart : pas de solde, mais la
                        # case reste dessinee pour que la grille tienne.
                        st.markdown(
                            f"<div class='dz-jour hors'>"
                            f"<div class='d'>{jour.day}</div></div>",
                            unsafe_allow_html=True)
                        continue
                    solde = float(info.solde)
                    couleur = (theme.ROUGE if solde < 0
                               else theme.AMBRE if solde < 500 else theme.VERT)
                    mouvement = ""
                    if info.operations:
                        signe = "+" if info.variation > 0 else "−"
                        mouvement = (f"<div class='m'>{signe}"
                                     f"{commun.nombre(abs(info.variation))}"
                                     f"</div>")
                    st.markdown(
                        f"<div class='dz-jour'>"
                        f"<div class='d'>{jour.day}</div>"
                        f"<div class='s' style='color:{couleur}'>"
                        f"{commun.nombre(solde)}</div>{mouvement}</div>",
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
