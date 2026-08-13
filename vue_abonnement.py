"""
ÉCRAN D'ABONNEMENT — les formules, le choix, le paiement
PrevuFlow — SMD Global Consulting LLC

Trois partis pris, parce qu'une page de tarifs se juge en dix secondes :

  · trois formules et pas une de plus, côte à côte, comparables d'un regard ;
  · le prix s'écrit dans la langue et la typographie du lecteur — « 7,00 $ »
    et « $7.00 » ne se lisent pas de la même façon ;
  · aucun bouton qui promet ce qu'il ne peut pas tenir : si le paiement
    n'est pas configuré, on le dit et on n'affiche pas de bouton mort.

Le règlement lui-même a lieu sur les pages de Stripe. PrevuFlow ne voit jamais
un numéro de carte, ce qui la dispense des obligations PCI-DSS.
"""

from __future__ import annotations

import streamlit as st

import abonnement as ab
import commun
import compte
import langues as lg
import theme
from abonnement import OFFRES_VENDUES, Periode, Plan


# ---------------------------------------------------------------------------
# Lecture de l'état
# ---------------------------------------------------------------------------

def _config() -> ab.ConfigStripe:
    """Relit la configuration une fois par session, pas à chaque rendu."""
    if "config_stripe" not in st.session_state:
        st.session_state.config_stripe = ab.charger_configuration()
    return st.session_state.config_stripe


def etat_abonnement() -> ab.Abonnement:
    """
    L'abonnement de la personne connectée, tel que Stripe le connaît.

    Mis en cache dans la session : chaque appel coûte deux requêtes réseau,
    et l'écran se redessine à chaque clic. `oublier_etat()` force la relecture
    au retour d'un paiement.
    """
    if "abonnement" in st.session_state:
        return st.session_state.abonnement

    config = _config()
    if not config.configure:
        st.session_state.abonnement = ab.Abonnement(plan=Plan.LIBRE)
        return st.session_state.abonnement

    if not compte.connecte():
        # Sans compte, aucun essai : il suffirait d'effacer son navigateur
        # pour en redemander un. On montre le produit dans sa version
        # gratuite, et l'écran d'abonnement dit comment obtenir les 14 jours.
        st.session_state.abonnement = ab.Abonnement(plan=Plan.DECOUVERTE)
        return st.session_state.abonnement

    s = compte.session()

    # La base d'abord : le webhook y a inscrit la formule payée. C'est une
    # lecture locale, immédiate, qui survit à une indisponibilité de Stripe.
    paye = compte.lire_abonnement_en_base()

    # Stripe ensuite, seulement si la base ne sait rien. Cela couvre les
    # premières minutes après un paiement, avant que le webhook ait été
    # traité, et les installations où il n'est pas branché.
    identifiant = paye.identifiant_client if paye else ""
    if paye is None or paye.plan in (Plan.DECOUVERTE, Plan.LIBRE):
        identifiant = identifiant or ab.trouver_client(s.email, config)
        depuis_stripe = (ab.lire_abonnement(identifiant, config)
                         if identifiant else None)
        if depuis_stripe is not None and depuis_stripe.plan in (
                Plan.PARTICULIER, Plan.ENTREPRISE):
            paye = depuis_stripe

    # Un abonnement payant l'emporte toujours sur l'essai : quelqu'un qui
    # paie le troisième jour ne doit pas retomber en Découverte le
    # quinzième.
    if paye is not None and paye.plan in (Plan.PARTICULIER, Plan.ENTREPRISE):
        st.session_state.abonnement = paye
        return paye

    en_essai = ab.essai(s.inscrit_le)
    if en_essai.actif():
        en_essai.identifiant_client = identifiant
        st.session_state.abonnement = en_essai
    else:
        st.session_state.abonnement = ab.Abonnement(
            plan=Plan.DECOUVERTE, identifiant_client=identifiant)
    return st.session_state.abonnement


def oublier_etat() -> None:
    st.session_state.pop("abonnement", None)


# ---------------------------------------------------------------------------
# Affichage d'un prix
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Droits — ce que la formule en cours autorise
# ---------------------------------------------------------------------------
#
# Ces quatre fonctions sont le seul point par lequel les ecrans interrogent
# l'abonnement. Les vues n'importent jamais `abonnement` directement : elles
# demandent « ai-je le droit ? », pas « quel est le plan ? ». Le jour ou la
# grille change, rien ne bouge dans les ecrans.

def offre_courante() -> ab.Offre:
    return etat_abonnement().offre_effective()


def autorise(fonction: str) -> bool:
    """« scenarios », « exports », « entreprise »."""
    return etat_abonnement().autorise(fonction)


def limite_jours() -> int:
    return etat_abonnement().limite_jours()


def limite_fichiers() -> int:
    return etat_abonnement().limite_fichiers()


def mur(fonction: str) -> bool:
    """
    Affiche l'encart « cette fonction demande une formule payante » et rend
    `False` quand l'acces est ferme, `True` quand il est ouvert.

    Le message nomme la formule qui debloque et propose d'y aller. Un mur
    qui dit seulement « non » fait partir ; un mur qui dit « voici comment »
    vend.
    """
    if autorise(fonction):
        return True

    requis = (ab.OFFRES[Plan.ENTREPRISE] if fonction == "entreprise"
              else ab.OFFRES[Plan.PARTICULIER])
    theme.message("info", commun.t("abo.mur_titre"),
                  commun.t("abo.mur_texte", plan=requis.nom(commun.t)))
    if st.button(commun.t("abo.voir_formules"), key=f"mur_{fonction}",
                 type="primary"):
        st.session_state.page = "abonnement"
        st.rerun()
    return False


def bandeau_abonnement() -> None:
    """
    Le décompte de l'essai, en haut de l'application.

    Sans lui, la période d'essai se terminerait sans que personne l'ait vue
    passer : la page d'abonnement n'est visitée que par ceux qui la
    cherchent, c'est-à-dire presque personne.
    """
    if not _config().configure:
        return

    etat = etat_abonnement()
    if etat.plan is Plan.ESSAI and etat.actif():
        restants = etat.jours_restants() or 0
        niveau = "attention" if restants <= 3 else "info"
        theme.message(niveau, commun.t("abo.essai_titre", jours=restants),
                      commun.t("abo.essai_texte"))
    elif (etat.plan is Plan.ESSAI
          or (etat.plan is Plan.DECOUVERTE and compte.connecte())):
        theme.message("info", commun.t("abo.fini_titre"),
                      commun.t("abo.fini_texte"))
    else:
        return

    if st.button(commun.t("abo.voir_formules"), key="bandeau_abo",
                 type="primary"):
        st.session_state.page = "abonnement"
        st.rerun()


def _prix(offre, periode: Periode) -> str:
    """
    « 7,00 $ par mois » en français, « $7.00 per month » en anglais.

    Le montant est stocké en cents entiers ; il est divisé ici, une seule
    fois, au moment de l'écrire.
    """
    if offre.gratuit:
        return commun.t("abo.gratuit")
    montant = lg.formater_montant(offre.prix(periode) / 100,
                                  offre.devise.upper(), commun.langue())
    return commun.t("abo.par_an" if periode is Periode.ANNUELLE
                    else "abo.par_mois", montant=montant)


# ---------------------------------------------------------------------------
# Écran
# ---------------------------------------------------------------------------

def afficher_abonnement() -> None:
    _retour_de_paiement()

    config = _config()
    courant = etat_abonnement()

    theme.hero(commun.t("abo.plan_actuel"),
               courant.offre_effective().nom(commun.t),
               courant.etat(commun.t, date_lisible=commun.date_longue))

    if not config.configure:
        theme.message_phrase("info", commun.t("abo.non_configure"))
        return

    st.subheader(commun.t("abo.titre"))
    st.caption(commun.t("abo.sous_titre"))

    periode = _choix_periode()

    colonnes = st.columns(len(OFFRES_VENDUES))
    for colonne, offre in zip(colonnes, OFFRES_VENDUES):
        with colonne:
            _carte_offre(offre, periode, courant, config)

    if courant.identifiant_client:
        st.divider()
        _portail(courant, config)


def _choix_periode() -> Periode:
    choix = st.radio(
        commun.t("abo.rythme"), ["mensuelle", "annuelle"], horizontal=True,
        key="abo_periode", format_func=lambda v: commun.t("abo." + v))
    return Periode.ANNUELLE if choix == "annuelle" else Periode.MENSUELLE


def _carte_offre(offre, periode: Periode, courant: ab.Abonnement,
                 config: ab.ConfigStripe) -> None:
    nom = offre.nom(commun.t)
    actuel = offre.plan is courant.plan_effectif()

    lignes = "".join(theme.ligne("· " + argument, "")
                     for argument in offre.arguments(commun.t))
    remise = ("" if offre.gratuit or periode is not Periode.ANNUELLE
              else commun.t("abo.economie", pourcent=offre.economie_annuelle))

    theme.scenario(nom, offre.resume(commun.t),
                   [(commun.t("abo." + periode.value), _prix(offre, periode),
                     theme.VERT if not offre.gratuit else theme.ESTOMPE)],
                   reference=actuel)
    theme.carte(lignes)
    if remise:
        st.caption(remise)

    if offre.gratuit:
        return
    if actuel:
        st.caption(commun.t("abo.deja"))
        return

    if st.button(commun.t("abo.choisir", plan=nom), key=f"abo_{offre.plan.value}",
                 type="primary", use_container_width=True):
        _engager(offre.plan, periode, config, courant)


def _engager(plan: Plan, periode: Periode, config: ab.ConfigStripe,
             courant: ab.Abonnement) -> None:
    """
    Prépare la session de paiement et affiche le lien.

    On n'ouvre pas la page à la place de l'utilisateur : Streamlit ne sait
    pas rediriger sans passer par du JavaScript, et un lien sur lequel on
    clique soi-même est plus clair qu'une fenêtre qui s'ouvre toute seule.
    """
    if compte.comptes_disponibles() and not compte.connecte():
        st.warning(commun.t("abo.connexion_requise"))
        return

    email = compte.session().email if compte.connecte() else ""
    try:
        adresse = ab.ouvrir_paiement(
            plan, periode, config, t=commun.t, email=email,
            identifiant_client=courant.identifiant_client)
    except ab.ErreurPaiement as erreur:
        st.error(str(erreur))
        return

    st.link_button(commun.t("abo.aller_payer"), adresse,
                   type="primary", use_container_width=True)
    st.caption(commun.t("abo.redirection"))


def _portail(courant: ab.Abonnement, config: ab.ConfigStripe) -> None:
    """Le portail Stripe : carte, factures, résiliation. Rien à construire."""
    try:
        adresse = ab.portail_client(courant.identifiant_client, config,
                                    t=commun.t)
    except ab.ErreurPaiement:
        return
    st.link_button(commun.t("abo.gerer"), adresse, use_container_width=True)
    st.caption(commun.t("abo.gerer_aide"))


def _retour_de_paiement() -> None:
    """
    Lit le paramètre laissé par Stripe dans l'adresse de retour.

    Sans cela, quelqu'un qui vient de payer retrouverait l'écran de vente
    inchangé, sans un mot — le moment exact où l'on doute d'avoir été
    débité pour rien.
    """
    valeur = st.query_params.get("paiement")
    if not valeur:
        return
    if valeur == "ok":
        oublier_etat()
        theme.message_phrase("bon", commun.t("abo.retour_ok"))
    elif valeur == "annule":
        theme.message_phrase("info", commun.t("abo.retour_annule"))
    st.query_params.clear()
