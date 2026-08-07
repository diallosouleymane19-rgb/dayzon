"""
ÉCRAN DE COMPTE — connexion, inscription, état de la session
Dayzon — SMD Global Consulting LLC

Trois principes de rédaction, parce qu'un écran de connexion est le moment
où l'on perd le plus de gens :

  · aucun jargon technique dans les messages ;
  · l'utilisateur peut toujours essayer l'application sans créer de compte ;
  · on dit où vont les données avant de les demander.
"""

from __future__ import annotations

import streamlit as st

import commun
import compte
import sauvegarde as sv


# ---------------------------------------------------------------------------
# Panneau latéral
# ---------------------------------------------------------------------------

def panneau_compte() -> None:
    """Affiché en haut du panneau de gauche, avant toute autre chose."""
    if not compte.comptes_disponibles():
        return                      # installation sans base : rien à montrer

    if compte.connecte():
        _connecte()
    else:
        _deconnecte()


def _connecte() -> None:
    s = compte.session()
    st.caption(f"Connecté · **{s.email}**")

    # L'écran doit dire la vérité sur l'état, pas afficher un « Enregistré »
    # rassurant alors que des modifications attendent.
    if st.session_state.get("erreur_sauvegarde"):
        st.error(f"⚠️ Non enregistré : {st.session_state.erreur_sauvegarde}")
    elif st.session_state.get("modifications_en_attente"):
        st.warning("Modifications non enregistrées.")
    else:
        dernier = st.session_state.get("dernier_enregistrement_base")
        if dernier:
            st.caption(f"✓ Enregistré à {dernier}")
        else:
            st.caption("Vos données sont enregistrées automatiquement.")

    c1, c2 = st.columns(2)
    if c1.button("Enregistrer", use_container_width=True,
                 help="L'enregistrement est automatique ; ce bouton force "
                      "une écriture immédiate."):
        _enregistrer()

    if c2.button("Déconnexion", use_container_width=True):
        compte.deconnecter()
        st.rerun()


def _enregistrer() -> None:
    """
    Force une écriture immédiate.

    L'enregistrement est automatique après chaque modification ; ce bouton
    ne sert qu'à rassurer, ou à réessayer après un échec réseau.
    """
    try:
        if commun.enregistrer(force=True):
            st.success("Enregistré dans votre compte.")
        else:
            st.warning("Rien à enregistrer.")
    except compte.ErreurCompte as err:
        st.error(str(err))
    except sv.ErreurSauvegarde as err:
        st.error(str(err))


def _deconnecte() -> None:
    with st.expander("👤 Se connecter / créer un compte", expanded=False):
        st.caption("Un compte permet de retrouver vos données à chaque visite, "
                   "sur n'importe quel appareil. Sans compte, l'application "
                   "fonctionne aussi — mais tout disparaît en fermant l'onglet.")

        onglet_connexion, onglet_creation, onglet_oubli = st.tabs(
            ["Connexion", "Créer un compte", "Mot de passe oublié"])

        with onglet_connexion:
            with st.form("connexion"):
                email = st.text_input("Adresse e-mail", key="cx_email")
                mot = st.text_input("Mot de passe", type="password", key="cx_mot")
                if st.form_submit_button("Se connecter", type="primary",
                                         use_container_width=True):
                    try:
                        compte.connecter(email, mot)
                        _recharger_depuis_base()
                        st.rerun()
                    except compte.ErreurCompte as err:
                        st.error(str(err))

        with onglet_creation:
            with st.form("creation"):
                email = st.text_input("Adresse e-mail", key="cr_email")
                mot = st.text_input("Mot de passe", type="password", key="cr_mot",
                                    help="Au moins 8 caractères.")
                st.caption("Vos données financières restent les vôtres. "
                           "Nous ne les consultons pas et ne les revendons pas.")
                if st.form_submit_button("Créer mon compte", type="primary",
                                         use_container_width=True):
                    try:
                        message = compte.inscrire(email, mot)
                        if compte.connecte():
                            st.success(message)
                            st.rerun()
                        else:
                            st.info(message)
                    except compte.ErreurCompte as err:
                        st.error(str(err))

        with onglet_oubli:
            with st.form("oubli"):
                email = st.text_input("Adresse de votre compte", key="ob_email")
                if st.form_submit_button("Recevoir un lien",
                                         use_container_width=True):
                    try:
                        st.info(compte.reinitialiser_mot_de_passe(email))
                    except compte.ErreurCompte as err:
                        st.error(str(err))


def _recharger_depuis_base() -> None:
    """
    Remplace l'état de la session par les données du compte.

    Si l'utilisateur avait saisi des choses avant de se connecter, elles
    sont écrasées. C'est voulu : se connecter signifie « retrouver mes
    données », pas « fusionner avec ce qui traîne ». On le signale.
    """
    avait_saisi = bool(st.session_state.get("operations")) or \
                  not commun.portefeuille().vide
    try:
        donnees = compte.charger_espace()
    except compte.ErreurCompte as err:
        st.warning(f"Connexion réussie, mais lecture impossible : {err}")
        return

    depuis_base = sv.Donnees(
        profil=donnees["profil"],
        devise_reference=donnees["devise_reference"],
        comptes=donnees["comptes"],
        operations=donnees["operations"],
        taux=donnees["taux"])

    if depuis_base.vide and avait_saisi:
        # Compte neuf et travail en cours : on garde ce qui est à l'écran
        # plutôt que de l'effacer au nom d'un compte vide.
        st.session_state.message_demarrage = (
            "info", "Votre compte est vide. Vos données actuelles ont été "
                    "conservées — utilisez « Enregistrer » pour les y placer.")
        return

    commun._appliquer(depuis_base)
    if not depuis_base.vide:
        st.session_state.message_demarrage = (
            "info", f"Données rechargées depuis votre compte : "
                    f"{depuis_base.resume()}.")


# ---------------------------------------------------------------------------
# Écran d'accueil quand les comptes existent mais que personne n'est connecté
# ---------------------------------------------------------------------------

def bandeau_essai() -> None:
    """
    Rappelle discrètement l'intérêt d'un compte, sans bloquer l'usage.

    Une application financière qui exige un compte avant d'avoir montré
    quoi que ce soit perd la majorité de ses visiteurs.
    """
    if not compte.comptes_disponibles() or compte.connecte():
        return
    if st.session_state.get("_bandeau_essai_vu"):
        return

    a_des_donnees = (bool(st.session_state.get("operations"))
                     or not commun.portefeuille().vide)
    if not a_des_donnees:
        return

    st.session_state._bandeau_essai_vu = True
    st.info("**Vos données disparaîtront en fermant cet onglet.** "
            "Créez un compte dans le panneau de gauche pour les retrouver "
            "à chaque visite, ou téléchargez votre fichier.")
