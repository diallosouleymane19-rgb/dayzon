"""
PANNEAU DES COMPTES ET DES TAUX
Dayzon — SMD Global Consulting LLC

Remplace l'ancien réglage à solde unique. Trois choses y sont visibles :

  · vos comptes, chacun dans sa devise de tenue ;
  · le total consolidé, **accompagné des taux qui l'ont produit** ;
  · l'état de la sauvegarde.

Le total n'est jamais affiché seul. L'audit l'exige, et c'est de toute façon
la seule façon honnête de présenter une somme convertie.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import streamlit as st

import argent
import commun
import theme
import sauvegarde as sv
from argent import ErreurArgent, Montant, Taux, nom_devise
from comptes import Compte, ErreurCompte

VERT, ROUGE, ORANGE = "#1F7244", "#C0392B", "#E67E22"

# Au-delà, un taux mérite d'être revérifié avant de servir à décider.
JOURS_AVANT_ALERTE_TAUX = 60


# ---------------------------------------------------------------------------
# Les comptes
# ---------------------------------------------------------------------------

def panneau_comptes(entreprise: bool) -> None:
    p = commun.portefeuille()

    st.subheader("💼 " + commun.t("comptes.titre"))

    if p.vide:
        st.caption(commun.t("comptes.vide"))
    else:
        for c in p.comptes:
            l1, l2 = st.columns([4, 1])
            couleur = "#111" if c.actif else "#aaa"
            l1.markdown(
                f"<div style='line-height:1.25'>"
                f"<span style='font-weight:600;color:{couleur}'>{c.nom}</span>"
                f"<span style='font-size:11px;color:#888'> · {c.devise}"
                f"{' · ' + c.etablissement if c.etablissement else ''}"
                f"{'' if c.actif else ' · ' + commun.t('comptes.clos')}</span><br>"
                f"<span style='font-size:13px;font-weight:600;color:"
                f"{ROUGE if c.solde < 0 else '#333'}'>"
                f"{commun.afficher(c.montant)}</span></div>",
                unsafe_allow_html=True)
            if l2.button("✕", key=f"del_cpt_{c.identifiant}",
                         help=commun.t("comptes.retirer", nom=c.nom)):
                p.retirer(c.identifiant)
                commun.enregistrer()
                st.rerun()

    with st.expander(commun.t("comptes.ajouter"), expanded=p.vide):
        with st.form("ajout_compte", clear_on_submit=True):
            nom = st.text_input(
                commun.t("comptes.nom"),
                placeholder="Compte courant, Caisse, Wave Sénégal…")
            c1, c2 = st.columns(2)
            with c1:
                devise = st.selectbox(
                    commun.t("comptes.devise"), commun.DEVISES_PROPOSEES,
                    format_func=lambda d: f"{d} — {nom_devise(d)}",
                    help=commun.t("comptes.aide_devise"))
            with c2:
                solde = st.number_input(commun.t("comptes.solde"), value=0.0, step=100.0,
                                        format="%.2f")
            etablissement = st.text_input(
                commun.t("comptes.etablissement"),
                placeholder="Crédit Agricole, Wise, Orange Money…")

            if st.form_submit_button(commun.t("comptes.valider"), type="primary",
                                     use_container_width=True):
                try:
                    p.ajouter(Compte(nom=nom or "Compte", devise=devise,
                                     solde=Decimal(str(solde)),
                                     etablissement=etablissement.strip()))
                    commun.enregistrer()
                    st.rerun()
                except (ErreurCompte, ErreurArgent) as err:
                    st.error(str(err))

    if p.vide:
        return

    # --- Devise de référence ---
    devises_possibles = sorted(set(commun.DEVISES_PROPOSEES) | set(p.devises))
    actuelle = commun.devise_reference()
    choisie = st.selectbox(
        commun.t("comptes.afficher_en"), devises_possibles,
        index=devises_possibles.index(actuelle) if actuelle in devises_possibles else 0,
        format_func=lambda d: f"{d} — {nom_devise(d)}",
        help=commun.t("comptes.aide_totaux"))
    if choisie != actuelle:
        st.session_state.devise = choisie
        p.definir_reference(choisie)
        commun.enregistrer()
        st.rerun()

    _total_consolide(p)


def _total_consolide(p) -> None:
    """Le total, et ce qui permet de le vérifier."""
    cons = commun.consolidation()

    if cons is None:
        st.warning(commun.t("comptes.total_impossible",
                            devise=commun.devise_reference()))
        partiel = p.solde_devise(commun.devise_reference())
        st.caption(commun.t("comptes.sans_conversion",
                            montant=commun.afficher(partiel)))
        return

    # Le total consolide est le chiffre de tete du panneau : il passe par
    # le theme, comme celui du calendrier.
    theme.hero(commun.t("comptes.total"),
               commun.afficher(cons.total),
               commun.t("comptes.n_comptes", c=cons.comptes_retenus,
                        d=len(cons.par_devise)))

    if not cons.multidevise:
        return

    # C'est ici que se corrige le défaut relevé : le taux employé est visible,
    # daté et sourcé, au lieu d'un total converti sans justification.
    with st.expander(commun.t("comptes.origine_total")):
        for devise, sous_total in cons.par_devise.items():
            st.caption(commun.t("comptes.en_devise",
                                montant=commun.afficher(sous_total),
                                devise=nom_devise(devise)))
        st.divider()
        st.caption("**" + commun.t("taux.employes") + "**")
        for t in cons.taux_employes:
            age = t.anciennete()
            couleur = ORANGE if age > JOURS_AVANT_ALERTE_TAUX else "#666"
            st.markdown(
                f"<div style='font-size:11px;color:{couleur}'>{t.phrase()} "
                f"— il y a {age} jour{'s' if age > 1 else ''}</div>",
                unsafe_allow_html=True)

    age_max = cons.anciennete_max()
    if age_max > JOURS_AVANT_ALERTE_TAUX:
        st.caption(f"⚠️ Le taux le plus ancien date de {age_max} jours. "
                   f"Vérifiez-le avant de décider sur ce total.")


# ---------------------------------------------------------------------------
# Les taux
# ---------------------------------------------------------------------------

def panneau_taux() -> None:
    table = commun.taux()
    p = commun.portefeuille()
    reference = commun.devise_reference()

    besoins = [d for d in p.devises if d != reference]
    manquants = [d for d in besoins if table.trouver(d, reference) is None]

    titre = "💱 " + commun.t("taux.titre")
    if manquants:
        titre += " — " + commun.t("taux.n_manquants", n=len(manquants))

    with st.expander(titre, expanded=bool(manquants)):
        st.caption(commun.t("taux.explication"))

        if manquants:
            st.warning(commun.t("taux.a_renseigner", devises=", ".join(manquants)))

        for devise in besoins:
            t = table.trouver(devise, reference)
            if t is None:
                st.markdown(f"**{devise} → {reference}** · {commun.t('taux.vide')}")
                continue
            age = t.anciennete()
            marque = "⚠️ " if age > JOURS_AVANT_ALERTE_TAUX else ""
            st.markdown(
                f"<div style='font-size:11px'>{marque}<b>1 {t.base}</b> = "
                f"{t.valeur.normalize():f} {t.contre}<br>"
                f"<span style='color:#888'>{commun.date_longue(t.observe_le)} · "
                f"{t.source}</span></div>", unsafe_allow_html=True)

        st.divider()
        with st.form("ajout_taux", clear_on_submit=True):
            st.caption(commun.t("taux.corriger"))
            c1, c2 = st.columns(2)
            with c1:
                base = st.selectbox(commun.t("taux.de"), commun.DEVISES_PROPOSEES,
                                    index=commun.DEVISES_PROPOSEES.index(
                                        manquants[0]) if manquants else 1)
            with c2:
                contre = st.selectbox(
                    commun.t("taux.vers"), commun.DEVISES_PROPOSEES,
                    index=commun.DEVISES_PROPOSEES.index(reference)
                    if reference in commun.DEVISES_PROPOSEES else 0)
            valeur = st.number_input(commun.t("taux.une_unite"), value=1.0, step=0.01,
                                     format="%.6f")
            c3, c4 = st.columns(2)
            with c3:
                observe = st.date_input(commun.t("taux.constate_le"), value=date.today())
            with c4:
                source = st.text_input(commun.t("taux.source"),
                                       value=commun.t("taux.saisie"),
                                       help=commun.t("taux.aide_source"))

            if st.form_submit_button(commun.t("taux.enregistrer"),
                                     use_container_width=True):
                try:
                    table.ajouter(Taux(base=base, contre=contre,
                                       valeur=Decimal(str(valeur)),
                                       observe_le=observe,
                                       source=source or commun.t("taux.saisie")))
                    commun.enregistrer()
                    st.rerun()
                except ErreurArgent as err:
                    st.error(str(err))


# ---------------------------------------------------------------------------
# La sauvegarde
# ---------------------------------------------------------------------------

def panneau_sauvegarde() -> None:
    """
    L'écran de sauvegarde, différent selon l'endroit où l'application tourne.

    En ligne, l'enregistrement automatique n'existe pas : le serveur est
    partagé entre tous les visiteurs. On le dit clairement plutôt que de
    laisser croire à une sauvegarde qui n'aurait pas lieu.
    """
    local = sv.mode_local()
    titre = "💾 " + (commun.t("sauv.titre") if local else commun.t("sauv.vos_donnees"))

    with st.expander(titre):
        st.caption(sv.raison_mode())

        if local:
            _sauvegarde_locale()
        else:
            st.info(commun.t("sauv.rien_serveur"))

        st.divider()
        _emporter_et_reprendre()


def _emporter_et_reprendre() -> None:
    """Télécharger son fichier, et le redéposer plus tard ou ailleurs."""
    st.caption("**" + commun.t("sauv.emporter") + "**")
    try:
        st.download_button(
            "⬇️ " + commun.t("sauv.telecharger"),
            data=commun.exporter_octets(),
            file_name=sv.nom_fichier_export(),
            mime="application/json",
            use_container_width=True,
            help=commun.t("sauv.aide_telech"))
    except sv.ErreurSauvegarde as err:
        st.error(str(err))

    st.caption("**" + commun.t("sauv.reprendre") + "**")
    depose = st.file_uploader("Fichier Dayzon", type=["json"],
                              key="reprise_fichier",
                              label_visibility="collapsed")
    if depose is not None and st.button(commun.t("sauv.charger"),
                                        use_container_width=True,
                                        key="btn_reprise"):
        try:
            donnees = commun.importer_octets(depose.getvalue())
            st.success(commun.t("sauv.repris", resume=donnees.resume()))
            st.rerun()
        except sv.ErreurSauvegarde as err:
            st.error(str(err))


def _sauvegarde_locale() -> None:
    """Enregistrement automatique sur le poste de l'utilisateur."""
    st.session_state.sauvegarde_auto = st.toggle(
        commun.t("sauv.auto"),
        value=st.session_state.sauvegarde_auto,
        help=commun.t("sauv.aide_local"))

    infos = sv.informations()
    if infos:
        st.caption(commun.t(
            "sauv.dernier",
            date=f"{commun.date_longue(infos['modifie_le'])} "
                 f"{infos['modifie_le'].strftime('%H:%M')}",
            taille=infos["taille_ko"]))
        st.caption(commun.t("sauv.emplacement", chemin=infos["chemin"]))
    else:
        st.caption(commun.t("sauv.aucune"))

    erreur = st.session_state.get("erreur_sauvegarde")
    if erreur:
        st.error(erreur)

    c1, c2 = st.columns(2)
    if c1.button(commun.t("compte.enregistrer"), use_container_width=True):
        try:
            commun.enregistrer(force=True)
            st.success(commun.t("sauv.enregistre"))
        except sv.ErreurSauvegarde as err:
            st.error(str(err))

    if infos and c2.button(commun.t("sauv.effacer"), use_container_width=True,
                           help=commun.t("sauv.aide_effacer")):
        st.session_state.confirmer_effacement = True

    if st.session_state.get("confirmer_effacement"):
        st.warning(commun.t("sauv.confirmer"))
        d1, d2 = st.columns(2)
        if d1.button(commun.t("sauv.oui_effacer"), type="primary",
                     use_container_width=True):
            sv.supprimer()
            st.session_state.confirmer_effacement = False
            st.session_state.sauvegarde_auto = False
            st.rerun()
        if d2.button(commun.t("sauv.annuler"), use_container_width=True):
            st.session_state.confirmer_effacement = False
            st.rerun()
