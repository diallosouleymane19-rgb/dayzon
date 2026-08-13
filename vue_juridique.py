"""
PAGES JURIDIQUES — conditions, confidentialité, mentions légales
PrevuFlow — SMD Global Consulting LLC

Les textes vivent dans `juridique/*.md`, pas dans le code : ils sont
relus, corrigés et datés par des humains, parfois par un juriste. Un
fichier Markdown se relit et se compare ; une chaîne noyée dans du Python
ne se relit pas.

Ils ne sont pour l'instant rédigés qu'en français. Une traduction
approximative d'un texte juridique engage plus qu'elle ne protège : mieux
vaut une version unique et claire, en attendant une traduction faite par
quelqu'un dont c'est le métier.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import commun

DOSSIER = Path(__file__).parent / "juridique"

DOCUMENTS = [
    ("jur.cgv", "CGV.md"),
    ("jur.confidentialite", "CONFIDENTIALITE.md"),
    ("jur.mentions", "MENTIONS_LEGALES.md"),
]


def _lire(nom: str) -> str:
    chemin = DOSSIER / nom
    try:
        return chemin.read_text(encoding="utf-8")
    except OSError:
        return ""


def afficher_juridique() -> None:
    st.title(commun.t("jur.titre"))

    if commun.langue() != "fr":
        st.info(commun.t("jur.langue_unique"))

    onglets = st.tabs([commun.t(cle) for cle, _ in DOCUMENTS])
    for onglet, (_, fichier) in zip(onglets, DOCUMENTS):
        with onglet:
            texte = _lire(fichier)
            if texte:
                # Les avertissements « à faire relire » sont écrits en
                # citation dans le fichier : ils restent visibles ici, et
                # c'est voulu tant qu'un juriste n'a pas relu.
                st.markdown(texte)
                st.download_button(
                    commun.t("jur.telecharger"), data=texte.encode("utf-8"),
                    file_name=fichier, mime="text/markdown",
                    key=f"dl_{fichier}")
            else:
                st.warning(commun.t("jur.absent", fichier=fichier))


def lien_pied_de_page() -> None:
    """Le renvoi discret présent en bas de chaque écran."""
    if st.button(commun.t("jur.titre"), key="aller_juridique"):
        st.session_state.page = "juridique"
        st.rerun()
