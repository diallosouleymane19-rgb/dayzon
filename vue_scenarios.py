"""
ONGLET SCÉNARIOS — affichage partagé
Dayzon — SMD Global Consulting LLC

Le même écran sert au particulier et à l'entreprise ; seul le catalogue
d'hypothèses proposées change.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

import commun

from commun import DEVISES, formater_court, solde_de_depart
from moteur_tresorerie import Recurrence
from scenarios import (GENRES, PORTEES, Hypothese, Scenario, comparer, modeles)

VERT, ROUGE, ORANGE, GRIS = "#1F7244", "#C0392B", "#E67E22", "#8A8A8A"


def _taux() -> dict:
    return {d: t for d, (_, t) in DEVISES.items()}


# ---------------------------------------------------------------------------
# Construction d'un scénario sur mesure
# ---------------------------------------------------------------------------

def _formulaire_sur_mesure(operations: list[dict]) -> None:
    with st.expander(commun.t("sc.construire")):
        nom = st.text_input(commun.t("sc.nom"), key="sc_nom",
                            placeholder=commun.t("sc.placeholder_nom"))

        genre = st.selectbox(commun.t("sc.supposer"), GENRES,
                             format_func=lambda g: commun.t("gen." + g),
                             key="sc_genre")

        libelles = sorted({o["libelle"] for o in operations})
        h = None

        if genre in ("varier", "supprimer", "decaler"):
            c1, c2 = st.columns(2)
            with c1:
                portee = st.selectbox(commun.t("sc.sur_quoi"), PORTEES,
                                      format_func=lambda p: commun.t("por." + p),
                                      key="sc_portee")
            with c2:
                toutes = commun.t("sc.toutes")
                cible = st.selectbox(commun.t("sc.op_particuliere"),
                                     [toutes] + libelles, key="sc_cible")
            cible = "" if cible == toutes else cible

            if genre == "varier":
                valeur = st.slider(commun.t("sc.variation"), -100, 100, -20, 5,
                                   format="%d %%", key="sc_var")
                h = Hypothese("varier", valeur, cible, portee)
            elif genre == "decaler":
                valeur = st.slider(commun.t("sc.decalage"), 0, 120, 30, 5,
                                   key="sc_dec")
                h = Hypothese("decaler", valeur, cible, portee)
            else:
                h = Hypothese("supprimer", cible=cible, portee=portee)

        elif genre == "ajouter":
            c1, c2 = st.columns(2)
            with c1:
                intitule = st.text_input(commun.t("sc.intitule"), key="sc_lib",
                                         placeholder=commun.t("sc.placeholder_lib"))
                sens = st.radio(commun.t("sc.type"), ["sortie", "entree"],
                                horizontal=True, key="sc_sens",
                                format_func=lambda s: commun.t("sc." + s))
            with c2:
                montant = st.number_input(commun.t("sc.montant"), min_value=0.0, value=1000.0,
                                          step=100.0, key="sc_mt")
                quand = st.date_input(commun.t("sc.a_partir_du"), value=date.today(),
                                      key="sc_date")
            freq = st.selectbox(
                commun.t("sc.frequence"),
                ["chaque_mois", "une_fois", "chaque_semaine", "chaque_annee"],
                format_func=lambda f: commun.t("sc." + f), key="sc_freq")
            h = Hypothese("ajouter",
                          montant if sens == "entree" else -montant,
                          libelle_ajout=intitule or commun.t("sc.nouvelle_op"),
                          date_ajout=quand,
                          recurrence_ajout={
                              "chaque_mois": Recurrence.MENSUELLE,
                              "une_fois": Recurrence.PONCTUELLE,
                              "chaque_semaine": Recurrence.HEBDOMADAIRE,
                              "chaque_annee": Recurrence.ANNUELLE}[freq])

        else:  # solde
            valeur = st.number_input(commun.t("sc.tresorerie_dep"), value=0.0, step=500.0,
                                     key="sc_solde")
            h = Hypothese("solde", valeur)

        if h is not None:
            st.caption(commun.t("sc.hypothese", phrase=h.phrase(commun.t)))
            if st.button(commun.t("sc.ajouter"), type="primary", key="sc_ok"):
                st.session_state.setdefault("scenarios_perso", [])
                st.session_state.scenarios_perso.append(
                    Scenario(nom or h.phrase(commun.t), [h],
                             commun.t("sc.defini_par_vous")))
                st.rerun()


# ---------------------------------------------------------------------------
# Affichage principal
# ---------------------------------------------------------------------------

def afficher_scenarios(profil: str = "Particulier") -> None:
    operations = st.session_state.operations
    if not operations:
        st.info(commun.t("sc.aucune_op"))
        return

    st.subheader(commun.t("sc.et_si"))
    st.caption(commun.t("sc.explication"))

    catalogue = modeles(profil, operations, t=commun.t)
    perso = st.session_state.get("scenarios_perso", [])
    tous = {**catalogue, **{s.nom: s for s in perso}}

    defaut = list(catalogue)[:2]
    choisis = st.multiselect(
        commun.t("sc.que_tester"), list(tous),
        default=[n for n in defaut if n in tous],
        help=commun.t("sc.aide_choix"))

    c1, c2 = st.columns([2, 3])
    with c1:
        horizon = st.select_slider(commun.t("sc.combien_temps"),
                                   options=[90, 180, 365, 730], value=180,
                                   format_func=lambda j: commun.t("sc.mois",
                                                                  n=j // 30),
                                   key="sc_hor")
    with c2:
        debut = st.date_input(commun.t("sc.a_partir_du"), value=date.today(),
                              key="sc_deb")

    _formulaire_sur_mesure(operations)

    if perso and st.button(commun.t("sc.effacer_perso")):
        del st.session_state.scenarios_perso
        st.rerun()

    if not choisis:
        st.info(commun.t("sc.selectionnez"))
        return

    retenus = [tous[n] for n in choisis]
    for s in retenus:
        if s.explication:
            st.caption(f"**{s.nom}** — {s.explication}")

    resultats = comparer(retenus, operations,
                         float(solde_de_depart()),
                         st.session_state.devise, _taux(), debut, horizon,
                         t=commun.t)

    base = resultats[0]

    # --- Courbes superposées ---
    st.divider()
    st.subheader(commun.t("sc.solde_selon"))
    courbes = pd.DataFrame({r.nom: dict(r.courbe) for r in resultats})
    courbes.index.name = commun.t("col.date")
    st.line_chart(courbes, height=340)
    st.caption(commun.t("sc.ligne_actuelle"))

    # --- Verdict par scénario ---
    st.divider()
    st.subheader(commun.t("sc.ce_que_ca_coute"))

    for r in resultats:
        reference = r.nom == base.nom
        niveau, phrase = r.verdict(commun.t, commun.date_longue)
        couleur = {"bon": VERT, "attention": ORANGE, "alerte": ROUGE}[niveau]

        c1, c2, c3 = st.columns([3.2, 2, 2])
        with c1:
            st.markdown(f"**{r.nom}**")
            if not reference:
                st.caption(r.resume)
            else:
                st.caption(commun.t("sc.sans_modif"))
        with c2:
            st.markdown(
                f"<div style='text-align:right'>"
                f"<span style='font-size:19px;font-weight:700;color:{couleur}'>"
                f"{formater_court(r.solde_minimum)}</span><br>"
                f"<span style='font-size:11px;color:#888'>"
                f"{commun.t('sc.point_bas_le', date=commun.date_courte(r.date_solde_min))}"
                f"</span></div>",
                unsafe_allow_html=True)
        with c3:
            if reference:
                st.markdown("<div style='text-align:right;color:#888;"
                            "font-size:12px;padding-top:6px'>"
                            + commun.t("sc.reference") + "</div>",
                            unsafe_allow_html=True)
            else:
                signe = "" if float(r.ecart_final) < 0 else "+"
                st.markdown(
                    f"<div style='text-align:right'>"
                    f"<span style='font-size:17px;font-weight:600;color:"
                    f"{ROUGE if float(r.ecart_final) < 0 else VERT}'>"
                    f"{signe}{formater_court(r.ecart_final)}</span><br>"
                    f"<span style='font-size:11px;color:#888'>"
                    f"{commun.t('sc.ecart_a', n=horizon // 30)}</span></div>",
                    unsafe_allow_html=True)

        {"alerte": st.error, "attention": st.warning,
         "bon": st.success}[niveau](phrase)

    # --- Ce qu'il faut retenir ---
    casses = [r for r in resultats[1:] if not r.tient]
    st.divider()
    st.subheader(commun.t("sc.a_retenir"))

    if base.tient and not casses:
        st.success(commun.t("sc.pas_decouvert", n=horizon // 30))
    elif not base.tient:
        st.error(commun.t("sc.deja_sous_zero",
                          date=commun.date_longue(base.premier_jour_negatif)))
    else:
        pire = min(casses, key=lambda r: r.jours_avant_negatif or 10**6)
        st.warning(commun.t("sc.combien_cassent", k=len(casses),
                            total=len(resultats) - 1, nom=pire.nom,
                            jours=pire.jours_avant_negatif))

    plus_couteux = min(resultats[1:], key=lambda r: float(r.ecart_final), default=None)
    if plus_couteux is not None and float(plus_couteux.ecart_final) < 0:
        st.info(commun.t("sc.couteux", nom=plus_couteux.nom,
                         montant=formater_court(plus_couteux.ecart_final),
                         n=horizon // 30))

    # --- Tableau ---
    with st.expander(commun.t("sc.tableau")):
        st.dataframe(pd.DataFrame([{
            commun.t("col.scenario"): r.nom,
            commun.t("col.hypotheses"): r.resume if r.nom != base.nom else "—",
            commun.t("col.solde_a", n=horizon // 30): float(r.solde_final),
            commun.t("col.ecart"): float(r.ecart_final) if r.nom != base.nom else None,
            commun.t("col.point_bas"): float(r.solde_minimum),
            commun.t("col.decouvert_le"): (commun.date_longue(r.premier_jour_negatif)
                                           if r.premier_jour_negatif else "—"),
        } for r in resultats]), use_container_width=True, hide_index=True)
