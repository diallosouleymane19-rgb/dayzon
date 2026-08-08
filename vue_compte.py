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
    st.caption(commun.t("cpt.connecte", email=s.email))

    # L'écran doit dire la vérité sur l'état, pas afficher un « Enregistré »
    # rassurant alors que des modifications attendent.
    if st.session_state.get("erreur_sauvegarde"):
        st.error(commun.t("cpt.non_enregistre",
                          erreur=st.session_state.erreur_sauvegarde))
    elif st.session_state.get("modifications_en_attente"):
        st.warning(commun.t("cpt.en_attente"))
    else:
        dernier = st.session_state.get("dernier_enregistrement_base")
        if dernier:
            st.caption(commun.t("cpt.enregistre_a", heure=dernier))
        else:
            st.caption(commun.t("cpt.auto"))

    c1, c2 = st.columns(2)
    if c1.button(commun.t("cpt.enregistrer"), use_container_width=True,
                 help=commun.t("cpt.aide_enr")):
        _enregistrer()

    if c2.button(commun.t("cpt.deconnexion"), use_container_width=True):
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
            st.success(commun.t("cpt.enr_ok"))
        else:
            st.warning(commun.t("cpt.rien"))
    except compte.ErreurCompte as err:
        st.error(str(err))
    except sv.ErreurSauvegarde as err:
        st.error(str(err))


def _deconnecte() -> None:
    with st.expander(commun.t("cpt.se_connecter"), expanded=False):
        st.caption(commun.t("cpt.pourquoi"))

        onglet_connexion, onglet_creation, onglet_oubli = st.tabs(
            [commun.t("cpt.onglet_cx"), commun.t("cpt.onglet_cr"),
             commun.t("cpt.onglet_ob")])

        with onglet_connexion:
            with st.form("connexion"):
                email = st.text_input(commun.t("cpt.email"), key="cx_email")
                mot = st.text_input(commun.t("cpt.mot"), type="password",
                                    key="cx_mot")
                if st.form_submit_button(commun.t("cpt.bouton_cx"), type="primary",
                                         use_container_width=True):
                    try:
                        compte.connecter(email, mot)
                        _recharger_depuis_base()
                        st.rerun()
                    except compte.ErreurCompte as err:
                        st.error(str(err))

        with onglet_creation:
            with st.form("creation"):
                email = st.text_input(commun.t("cpt.email"), key="cr_email")
                mot = st.text_input(commun.t("cpt.mot"), type="password",
                                    key="cr_mot", help=commun.t("cpt.aide_mot"))
                st.caption(commun.t("cpt.confidentiel"))
                if st.form_submit_button(commun.t("cpt.bouton_cr"), type="primary",
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
            _mot_de_passe_oublie()


def _mot_de_passe_oublie() -> None:
    """
    Deux étapes : recevoir un code, puis choisir un mot de passe.

    L'ancienne version envoyait un lien et s'arrêtait là. Le lien ramenait
    bien l'utilisateur sur l'application, mais avec le jeton dans le
    fragment de l'URL — invisible pour Streamlit — et aucun écran pour
    saisir quoi que ce soit. La promesse était affichée, jamais tenue.
    """
    st.caption(commun.t("cpt.oubli_explication"))

    with st.form("oubli_demande"):
        email = st.text_input(commun.t("cpt.email_compte"), key="ob_email")
        if st.form_submit_button(commun.t("cpt.recevoir_code"),
                                 use_container_width=True):
            try:
                st.session_state.attente_code = True
                st.info(compte.reinitialiser_mot_de_passe(email))
            except compte.ErreurCompte as err:
                st.error(str(err))

    if not st.session_state.get("attente_code"):
        return

    st.divider()
    with st.form("oubli_code"):
        st.caption(commun.t("cpt.code_recu"))
        code = st.text_input(commun.t("cpt.code"), key="ob_code",
                             max_chars=10, placeholder="123456")
        nouveau = st.text_input(commun.t("cpt.nouveau_mot"), type="password",
                                key="ob_mot", help=commun.t("cpt.aide_mot"))
        if st.form_submit_button(commun.t("cpt.valider_mot"), type="primary",
                                 use_container_width=True):
            try:
                # L'ordre compte : le code ouvre la session, la session
                # autorise le changement. L'inverse échouerait.
                compte.verifier_code(st.session_state.get("ob_email", ""), code)
                message = compte.changer_mot_de_passe(nouveau)
                st.session_state.pop("attente_code", None)
                st.success(message)
                _recharger_depuis_base()
                st.rerun()
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
        st.warning(commun.t("cpt.lecture_ko", erreur=err))
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
            "info", commun.t("cpt.compte_vide"))
        return

    commun._appliquer(depuis_base)
    if not depuis_base.vide:
        st.session_state.message_demarrage = (
            "info", commun.t("cpt.rechargees", resume=depuis_base.resume()))


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
    st.info(commun.t("cpt.bandeau"))
