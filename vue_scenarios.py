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
    with st.expander("Construire mon propre scénario"):
        nom = st.text_input("Nom du scénario", key="sc_nom",
                            placeholder="Ex. : je change de local")

        genre = st.selectbox("Que voulez-vous supposer ?", list(GENRES),
                             format_func=lambda g: GENRES[g], key="sc_genre")

        libelles = sorted({o["libelle"] for o in operations})
        h = None

        if genre in ("varier", "supprimer", "decaler"):
            c1, c2 = st.columns(2)
            with c1:
                portee = st.selectbox("Sur quoi ?", list(PORTEES),
                                      format_func=lambda p: PORTEES[p],
                                      key="sc_portee")
            with c2:
                cible = st.selectbox(
                    "Une opération en particulier ?", ["— toutes —"] + libelles,
                    key="sc_cible")
            cible = "" if cible == "— toutes —" else cible

            if genre == "varier":
                valeur = st.slider("Variation", -100, 100, -20, 5,
                                   format="%d %%", key="sc_var")
                h = Hypothese("varier", valeur, cible, portee)
            elif genre == "decaler":
                valeur = st.slider("Décalage", 0, 120, 30, 5,
                                   format="%d jours", key="sc_dec")
                h = Hypothese("decaler", valeur, cible, portee)
            else:
                h = Hypothese("supprimer", cible=cible, portee=portee)

        elif genre == "ajouter":
            c1, c2 = st.columns(2)
            with c1:
                intitule = st.text_input("Intitulé", key="sc_lib",
                                         placeholder="Nouveau salaire, loyer...")
                sens = st.radio("Type", ["Sortie", "Entrée"], horizontal=True,
                                key="sc_sens")
            with c2:
                montant = st.number_input("Montant", min_value=0.0, value=1000.0,
                                          step=100.0, key="sc_mt")
                quand = st.date_input("À partir du", value=date.today(),
                                      key="sc_date")
            freq = st.selectbox("Fréquence", ["Chaque mois", "Une seule fois",
                                              "Chaque semaine", "Chaque année"],
                                key="sc_freq")
            h = Hypothese("ajouter",
                          montant if sens == "Entrée" else -montant,
                          libelle_ajout=intitule or "Nouvelle opération",
                          date_ajout=quand,
                          recurrence_ajout={
                              "Chaque mois": Recurrence.MENSUELLE,
                              "Une seule fois": Recurrence.PONCTUELLE,
                              "Chaque semaine": Recurrence.HEBDOMADAIRE,
                              "Chaque année": Recurrence.ANNUELLE}[freq])

        else:  # solde
            valeur = st.number_input("Trésorerie de départ", value=0.0, step=500.0,
                                     key="sc_solde")
            h = Hypothese("solde", valeur)

        if h is not None:
            st.caption(f"Hypothèse : **{h.phrase()}**")
            if st.button("Ajouter ce scénario", type="primary", key="sc_ok"):
                st.session_state.setdefault("scenarios_perso", [])
                st.session_state.scenarios_perso.append(
                    Scenario(nom or h.phrase(), [h], "Scénario que vous avez défini"))
                st.rerun()


# ---------------------------------------------------------------------------
# Affichage principal
# ---------------------------------------------------------------------------

def afficher_scenarios(profil: str = "Particulier") -> None:
    operations = st.session_state.operations
    if not operations:
        st.info("Les scénarios reposent sur vos opérations. Importez un relevé "
                "et validez les récurrences, ou ajoutez vos échéances dans "
                "le panneau de gauche.")
        return

    st.subheader("Et si ?")
    st.caption("Un scénario reprend vos opérations, applique une hypothèse, "
               "et recalcule votre solde jour par jour. Vos données ne sont "
               "jamais modifiées.")

    catalogue = modeles(profil, operations)
    perso = st.session_state.get("scenarios_perso", [])
    tous = {**catalogue, **{s.nom: s for s in perso}}

    defaut = list(catalogue)[:2]
    choisis = st.multiselect(
        "Que voulez-vous tester ?", list(tous),
        default=[n for n in defaut if n in tous],
        help="Chaque scénario est comparé à votre situation actuelle.")

    c1, c2 = st.columns([2, 3])
    with c1:
        horizon = st.select_slider("Sur combien de temps",
                                   options=[90, 180, 365, 730],
                                   value=180,
                                   format_func=lambda j: f"{j // 30} mois",
                                   key="sc_hor")
    with c2:
        debut = st.date_input("À partir du", value=date.today(), key="sc_deb")

    _formulaire_sur_mesure(operations)

    if perso and st.button("Effacer mes scénarios personnels"):
        del st.session_state.scenarios_perso
        st.rerun()

    if not choisis:
        st.info("Sélectionnez au moins un scénario ci-dessus.")
        return

    retenus = [tous[n] for n in choisis]
    for s in retenus:
        if s.explication:
            st.caption(f"**{s.nom}** — {s.explication}")

    resultats = comparer(retenus, operations,
                         float(solde_de_depart()),
                         st.session_state.devise, _taux(), debut, horizon)

    base = resultats[0]

    # --- Courbes superposées ---
    st.divider()
    st.subheader("Votre solde selon chaque hypothèse")
    courbes = pd.DataFrame({r.nom: dict(r.courbe) for r in resultats})
    courbes.index.name = "Date"
    st.line_chart(courbes, height=340)
    st.caption("La ligne « Situation actuelle » est votre trajectoire sans "
               "changement. Tout ce qui passe sous zéro est un découvert.")

    # --- Verdict par scénario ---
    st.divider()
    st.subheader("Ce que chaque scénario vous coûte")

    for r in resultats:
        reference = r.nom == base.nom
        niveau, phrase = r.verdict()
        couleur = {"bon": VERT, "attention": ORANGE, "alerte": ROUGE}[niveau]

        c1, c2, c3 = st.columns([3.2, 2, 2])
        with c1:
            st.markdown(f"**{r.nom}**")
            if not reference:
                st.caption(r.resume)
            else:
                st.caption("Votre trajectoire actuelle, sans modification")
        with c2:
            st.markdown(
                f"<div style='text-align:right'>"
                f"<span style='font-size:19px;font-weight:700;color:{couleur}'>"
                f"{formater_court(r.solde_minimum)}</span><br>"
                f"<span style='font-size:11px;color:#888'>point bas le "
                f"{r.date_solde_min.strftime('%d/%m/%y')}</span></div>",
                unsafe_allow_html=True)
        with c3:
            if reference:
                st.markdown("<div style='text-align:right;color:#888;"
                            "font-size:12px;padding-top:6px'>référence</div>",
                            unsafe_allow_html=True)
            else:
                signe = "" if float(r.ecart_final) < 0 else "+"
                st.markdown(
                    f"<div style='text-align:right'>"
                    f"<span style='font-size:17px;font-weight:600;color:"
                    f"{ROUGE if float(r.ecart_final) < 0 else VERT}'>"
                    f"{signe}{formater_court(r.ecart_final)}</span><br>"
                    f"<span style='font-size:11px;color:#888'>écart à "
                    f"{horizon // 30} mois</span></div>",
                    unsafe_allow_html=True)

        {"alerte": st.error, "attention": st.warning,
         "bon": st.success}[niveau](phrase)

    # --- Ce qu'il faut retenir ---
    casses = [r for r in resultats[1:] if not r.tient]
    st.divider()
    st.subheader("Ce qu'il faut retenir")

    if base.tient and not casses:
        st.success(
            f"**Aucun des scénarios testés ne vous met à découvert** sur "
            f"{horizon // 30} mois. Votre situation absorbe ces chocs.")
    elif not base.tient:
        st.error(
            f"**Votre situation actuelle passe déjà sous zéro** le "
            f"{base.premier_jour_negatif.strftime('%d/%m/%Y')}. Les scénarios "
            f"ne font qu'aggraver un problème qui existe déjà — c'est lui "
            f"qu'il faut traiter d'abord.")
    else:
        pire = min(casses, key=lambda r: r.jours_avant_negatif or 10**6)
        st.warning(
            f"**{len(casses)} scénario{'s' if len(casses) > 1 else ''} sur "
            f"{len(resultats) - 1} vous met{'tent' if len(casses) > 1 else ''} "
            f"à découvert.** Le plus rapide est « {pire.nom} » : "
            f"{pire.jours_avant_negatif} jours. C'est le délai dont vous "
            f"disposez pour vous y préparer.")

    plus_couteux = min(resultats[1:], key=lambda r: float(r.ecart_final), default=None)
    if plus_couteux is not None and float(plus_couteux.ecart_final) < 0:
        st.info(f"Le scénario le plus coûteux est « {plus_couteux.nom} » : "
                f"{formater_court(plus_couteux.ecart_final)} de trésorerie en "
                f"moins à {horizon // 30} mois, par rapport à aujourd'hui.")

    # --- Tableau ---
    with st.expander("Voir le tableau comparatif"):
        st.dataframe(pd.DataFrame([{
            "Scénario": r.nom,
            "Hypothèses": r.resume if r.nom != base.nom else "—",
            f"Solde à {horizon // 30} mois": float(r.solde_final),
            "Écart": float(r.ecart_final) if r.nom != base.nom else None,
            "Point bas": float(r.solde_minimum),
            "Découvert le": (r.premier_jour_negatif.strftime("%d/%m/%Y")
                             if r.premier_jour_negatif else "—"),
        } for r in resultats]), use_container_width=True, hide_index=True)
