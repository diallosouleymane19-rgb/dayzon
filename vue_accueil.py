"""
ÉCRAN D'ACCUEIL — ce que fait PrevuFlow, et pour qui
PrevuFlow — SMD Global Consulting LLC

Un visiteur qui arrivait sur l'application tombait directement sur un outil
vide : un panneau de saisie, un calendrier sans données, aucun mot sur ce
qu'il avait sous les yeux. Il fallait avoir compris le produit avant de le
voir pour ne pas repartir.

Cet écran répond à trois questions, dans cet ordre — celui dans lequel on
se les pose :

  1. Qu'est-ce que ça fait ? Une phrase, pas un paragraphe.
  2. Est-ce que ça marche avec ma banque ? C'est la question qui bloque,
     parce que les concurrents exigent une connexion bancaire.
  3. Combien ça coûte ? Affiché avant l'inscription, jamais après.

Il ne s'affiche qu'une fois : celui qui a commencé à travailler ne doit
plus le revoir. Le bouton « Voir la présentation » le ramène au besoin.
"""

from __future__ import annotations

import streamlit as st

import commun
import theme


def doit_afficher() -> bool:
    """
    Vrai quand le visiteur n'a encore rien fait.

    Trois cas font disparaître l'accueil : un compte ouvert, des données
    saisies, ou un passage explicite dans l'application. On ne le remontre
    jamais de lui-même — réafficher une page de vente à quelqu'un qui
    travaille est le meilleur moyen de le faire partir.
    """
    if st.session_state.get("accueil_vu"):
        return False
    if st.session_state.get("operations"):
        return False
    if st.session_state.get("mouvements"):
        return False
    if not commun.portefeuille().vide:
        return False

    import compte
    return not compte.connecte()


def _formule(colonne, offre, periode, en_avant: bool = False) -> None:
    """Une formule : son nom, son prix, ce qu'elle ouvre."""
    from vue_abonnement import _prix

    with colonne:
        cadre = "dz-sc ref" if en_avant else "dz-sc"
        arguments = "".join(
            f'<div class="res">· {theme._e(a)}</div>'
            for a in offre.arguments(commun.t))
        st.markdown(
            f'<div class="{cadre}">'
            f'<div class="nom">{theme._e(offre.nom(commun.t))}</div>'
            f'<div class="grille" style="grid-template-columns:1fr">'
            f'<div><div class="v" style="color:{theme.VERT}">'
            f'{theme._e(_prix(offre, periode))}</div></div></div>'
            f'{arguments}</div>',
            unsafe_allow_html=True)


def afficher_accueil() -> None:
    from abonnement import OFFRES_VENDUES, Periode

    # Le logo est deja en haut de la barre laterale : le remettre ici, plus
    # le nom dans le bandeau, ferait trois fois la marque sur le meme ecran.
    # L'etiquette du bandeau sert donc a situer le produit, pas a le nommer.
    theme.hero(commun.t("acc.categorie"), commun.t("acc.promesse"),
               commun.t("acc.sous_promesse"))

    # --- Ce qui nous distingue -------------------------------------------
    # C'est le premier bloc parce que c'est la première objection : tous
    # les concurrents demandent une connexion bancaire.
    a, b, c = st.columns(3)
    theme.kpi(a, commun.t("acc.arg1_titre"), commun.t("acc.arg1_valeur"),
              commun.t("acc.arg1_note"), theme.VERT)
    theme.kpi(b, commun.t("acc.arg2_titre"), commun.t("acc.arg2_valeur"),
              commun.t("acc.arg2_note"), theme.MARINE)
    theme.kpi(c, commun.t("acc.arg3_titre"), commun.t("acc.arg3_valeur"),
              commun.t("acc.arg3_note"), theme.MARINE)

    st.write("")
    st.subheader(commun.t("acc.comment_titre"))
    e1, e2, e3 = st.columns(3)
    for colonne, numero in ((e1, 1), (e2, 2), (e3, 3)):
        colonne.markdown(f"#### {numero}. {commun.t(f'acc.etape{numero}')}")
        colonne.caption(commun.t(f"acc.etape{numero}_detail"))

    st.divider()

    # --- Entrer ----------------------------------------------------------
    g, d = st.columns([2, 3])
    with g:
        if st.button(commun.t("acc.commencer"), type="primary",
                     use_container_width=True):
            st.session_state.accueil_vu = True
            st.rerun()
    with d:
        st.caption(commun.t("acc.sans_compte"))

    st.divider()

    # --- Les formules ----------------------------------------------------
    st.subheader(commun.t("acc.formules_titre"))
    st.caption(commun.t("acc.formules_sous_titre"))

    colonnes = st.columns(len(OFFRES_VENDUES))
    for colonne, offre in zip(colonnes, OFFRES_VENDUES):
        _formule(colonne, offre, Periode.MENSUELLE,
                 en_avant=offre.prix_mensuel == 700)

    st.caption(commun.t("acc.essai_rappel"))

    st.divider()

    # --- Ce que PrevuFlow ne fait pas -------------------------------------
    # Dit avant l'inscription plutôt que découvert après : une attente
    # déçue coûte un remboursement et un avis négatif.
    theme.message("info", commun.t("acc.limites_titre"),
                  commun.t("acc.limites_texte"))

    st.caption(commun.t("acc.pied", annee=2026))
