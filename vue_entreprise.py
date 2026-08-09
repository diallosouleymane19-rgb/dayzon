"""
PROFIL ENTREPRISE — affichage
Dayzon — SMD Global Consulting LLC

Analyse financiere pure : aucun plan de comptes, aucun referentiel national.
Les indicateurs portent les memes noms partout dans le monde.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from analyse_entreprise import (calculer_indicateurs, factures_vers_operations,
                                lire_factures)
import commun
import theme
from commun import formater, formater_court, solde_de_depart
from vue_calendrier import afficher_calendrier

VERT, ROUGE, ORANGE = theme.VERT, theme.ROUGE, theme.AMBRE


# ---------------------------------------------------------------------------
# Barre laterale
# ---------------------------------------------------------------------------

def barre_laterale_entreprise() -> None:
    """Les trois sources de donnees. Aucune n'est obligatoire."""
    st.subheader("📥 " + commun.t("ent.vos_donnees"))
    st.caption(commun.t("ent.chaque_fichier"))

    for cle, etiquette, sens, aide in [
        ("fc", commun.t("ent.fc_titre"), "client",
         "Ce que vos clients vous doivent. Donne le délai d'encaissement, "
         "les impayés et la dépendance client."),
        ("ff", commun.t("ent.ff_titre"), "fournisseur",
         "Ce que vous devez. Donne le délai de paiement et l'encours à régler."),
    ]:
        st.markdown(etiquette)
        st.caption(aide)
        fichier = st.file_uploader(etiquette, type=["csv", "xlsx", "xls", "xlsm"],
                                   key=f"up_{cle}", label_visibility="collapsed")
        if fichier is not None and st.button(commun.t("ent.lire_fichier"), key=f"btn_{cle}",
                                             use_container_width=True):
            try:
                lecture = lire_factures(fichier, fichier.name, sens=sens,
                                        devise_defaut=st.session_state.devise)
                st.session_state[f"lecture_{cle}"] = lecture
                st.rerun()
            except Exception as erreur:
                st.error(str(erreur))

        lecture = st.session_state.get(f"lecture_{cle}")
        if lecture:
            st.success(f"{len(lecture.factures)} factures · "
                       f"{formater_court(lecture.total)}")
            if st.button(commun.t("ent.retirer"), key=f"del_{cle}", use_container_width=True):
                del st.session_state[f"lecture_{cle}"]
                st.rerun()
        st.divider()


# ---------------------------------------------------------------------------
# Petits blocs d'affichage
# ---------------------------------------------------------------------------

def _bloc(colonne, titre: str, valeur: str, note: str = "",
          couleur: str = theme.ENCRE) -> None:
    """Conserve pour ne pas reecrire tous les appels ; delegue au theme."""
    theme.kpi(colonne, titre, valeur, note, couleur)


def _messages(ind) -> None:
    for niveau, texte in ind.messages():
        theme.message_phrase(niveau, texte)


# ---------------------------------------------------------------------------
# Onglet 1 — Tableau de bord
# ---------------------------------------------------------------------------

def _tableau_de_bord(ind) -> None:
    st.subheader(commun.t("ent.gagne_depense"))

    a, b, c, d = st.columns(4)
    _bloc(a, commun.t("ent.encaisse"), formater_court(ind.encaissements_par_mois),
          "argent réellement reçu", VERT)
    _bloc(b, commun.t("ent.decaisse"), formater_court(ind.decaissements_par_mois),
          "argent réellement sorti", ROUGE)
    resultat_ok = ind.resultat_par_mois >= 0
    _bloc(c, commun.t("ent.resultat"), formater_court(ind.resultat_par_mois),
          f"{ind.marge:.0f} % de vos encaissements",
          VERT if resultat_ok else ROUGE)
    _bloc(d, commun.t("ent.tresorerie"), formater_court(ind.tresorerie),
          "solde saisi dans le panneau de gauche")

    st.write("")
    e, f, g, h = st.columns(4)

    if ind.runway_mois is not None:
        couleur = (ROUGE if ind.runway_mois < 3
                   else ORANGE if ind.runway_mois < 6 else VERT)
        _bloc(e, commun.t("ent.autonomie"), f"{ind.runway_mois:.1f} mois",
              "avant épuisement de la trésorerie", couleur)
    elif resultat_ok:
        _bloc(e, commun.t("ent.autonomie"), "Illimitée",
              "votre activité s'autofinance", VERT)
    else:
        _bloc(e, commun.t("ent.autonomie"), "—", "trésorerie non renseignée")

    if ind.point_mort is not None:
        atteint = ind.encaissements_par_mois >= ind.point_mort
        _bloc(f, commun.t("ent.point_equilibre"), formater_court(ind.point_mort),
              "atteint" if atteint else "non atteint",
              VERT if atteint else ROUGE)
    else:
        _bloc(f, commun.t("ent.point_equilibre"), "—", "importez un relevé bancaire")

    _bloc(g, commun.t("ent.charges_fixes"), formater_court(ind.charges_fixes),
          f"{ind.part_fixe:.0f} % de vos charges",
          ORANGE if ind.part_fixe > 70 else "#1F4E79")
    _bloc(h, commun.t("ent.charges_var"), formater_court(ind.charges_variables),
          "sur lesquelles vous pouvez agir")

    st.write("")
    st.divider()
    st.subheader(commun.t("ent.ce_que_ca_veut"))
    _messages(ind)

    st.caption(commun.t("ent.periode",
                        debut=commun.date_longue(ind.debut),
                        fin=commun.date_longue(ind.fin),
                        mois=f"{ind.nb_mois:.1f}"))


# ---------------------------------------------------------------------------
# Onglet 2 — Clients et fournisseurs
# ---------------------------------------------------------------------------

def _clients(ind, factures_clients, factures_fournisseurs) -> None:
    if not factures_clients and not factures_fournisseurs:
        st.info("Importez vos factures dans le panneau de gauche pour obtenir "
                "vos délais de règlement, vos impayés et votre dépendance client.")
        st.markdown("""
**Le fichier attendu est un simple tableau.** Deux colonnes suffisent — une date
et un montant. Les autres améliorent l'analyse :

| Colonne | Rôle |
|---|---|
| Date de facture | obligatoire |
| Montant | obligatoire |
| Client / Fournisseur | dépendance et classement par tiers |
| Échéance | détection des retards |
| Date de paiement *(ou colonne Statut)* | délai réel de règlement |
| Devise | analyse multidevise |

Les intitulés sont reconnus en français comme en anglais : *Invoice date, Customer,
Amount, Due date, Paid on, Status…*
        """)
        return

    if factures_clients:
        st.subheader(commun.t("ent.vos_clients"))
        a, b, c, d = st.columns(4)
        _bloc(a, commun.t("ent.facture"), formater_court(ind.ca_facture), "sur la période")
        _bloc(b, commun.t("ent.reste_encaisser"), formater_court(ind.encours_client),
              "factures non réglées",
              ORANGE if ind.encours_client > 0 else VERT)
        _bloc(c, commun.t("ent.dont_retard"), formater_court(ind.retard_client),
              "échéance dépassée",
              ROUGE if ind.retard_client > 0 else VERT)
        if ind.dso is not None:
            _bloc(d, commun.t("ent.delai_encaiss"), f"{ind.dso:.0f} jours",
                  "moyenne pondérée par les montants",
                  ROUGE if ind.dso > 60 else VERT)
        else:
            _bloc(d, commun.t("ent.delai_encaiss"), "—", "aucun paiement daté")

        st.write("")
        g, h = st.columns([3, 2])

        with g:
            st.markdown("**" + commun.t("ent.repartition_ca") + "**")
            for c_ in ind.concentration[:8]:
                l1, l2, l3 = st.columns([3, 1.4, 2])
                l1.write(c_.tiers[:34])
                l2.markdown(f"<div style='text-align:right'>"
                            f"{formater_court(c_.montant)}</div>",
                            unsafe_allow_html=True)
                couleur = ROUGE if c_.part > 0.3 else "#888"
                l3.markdown(f"<div style='color:{couleur};font-size:13px'>"
                            f"{'█' * max(1, int(c_.part * 20))} {c_.part:.0%}</div>",
                            unsafe_allow_html=True)

        with h:
            st.markdown("**" + commun.t("ent.recouvrement") + "**")
            if ind.taux_recouvrement is not None:
                st.progress(min(1.0, ind.taux_recouvrement / 100),
                            text=f"{ind.taux_recouvrement:.0f} % de vos factures "
                                 f"sont encaissées")
            impayees = [f for f in factures_clients if not f.payee]
            if impayees:
                st.markdown("**" + commun.t("ent.a_relancer") + "**")
                retards = sorted(impayees, key=lambda f: -f.jours_de_retard())
                st.dataframe(pd.DataFrame([{
                    "Client": f.tiers[:26],
                    "Montant": float(f.montant),
                    "Retard (j)": f.jours_de_retard() or None,
                } for f in retards[:15]]),
                    use_container_width=True, hide_index=True)

    if factures_fournisseurs:
        st.divider()
        st.subheader(commun.t("ent.vos_fournisseurs"))
        a, b, c = st.columns(3)
        _bloc(a, "Facturé par vos fournisseurs",
              formater_court(ind.achats_factures), "sur la période")
        _bloc(b, commun.t("ent.reste_payer"), formater_court(ind.encours_fournisseur),
              "dettes non réglées", ORANGE)
        if ind.dpo is not None:
            _bloc(c, commun.t("ent.delai_paiement"), f"{ind.dpo:.0f} jours",
                  "moyenne pondérée par les montants")
        else:
            _bloc(c, commun.t("ent.delai_paiement"), "—", "aucun paiement daté")

    ecart = ind.ecart_de_financement
    if ecart is not None:
        st.write("")
        st.markdown("**" + commun.t("ent.qui_finance") + "**")
        if ecart > 0:
            st.warning(
                f"Vous êtes payé en {ind.dso:.0f} jours et vous payez en "
                f"{ind.dpo:.0f} jours. Pendant {ecart:.0f} jours, c'est votre "
                f"trésorerie qui finance l'activité de vos clients.")
        else:
            st.success(
                f"Vous êtes payé en {ind.dso:.0f} jours et vous payez en "
                f"{ind.dpo:.0f} jours. Vos fournisseurs financent votre cycle "
                f"d'exploitation sur {abs(ecart):.0f} jours.")


# ---------------------------------------------------------------------------
# Onglet 4 — Rapport
# ---------------------------------------------------------------------------

def _rapport(ind, syn) -> None:
    st.subheader(commun.t("rap.telecharger"))

    titre = st.text_input("Titre du rapport", value="Analyse financière",
                          key="titre_ent")
    horodatage = date.today().strftime("%Y%m%d")

    r1, r2, r3 = st.columns(3)
    try:
        from export_rapport import (exporter_entreprise_excel, exporter_pdf,
                                    exporter_word)
        with r1:
            st.download_button(
                "📊 Excel", key="x_ent",
                data=exporter_entreprise_excel(
                    ind, syn, st.session_state.get("mouvements"),
                    devise=st.session_state.devise, titre=titre),
                file_name=f"analyse_entreprise_{horodatage}.xlsx",
                mime="application/vnd.openxmlformats-officedocument."
                     "spreadsheetml.sheet",
                use_container_width=True, type="primary")
            st.caption("Indicateurs, clients, opérations")
        if syn is not None:
            with r2:
                st.download_button(
                    "📄 PDF", key="p_ent",
                    data=exporter_pdf(syn, devise=st.session_state.devise,
                                      titre=titre),
                    file_name=f"analyse_{horodatage}.pdf",
                    mime="application/pdf", use_container_width=True)
                st.caption("Une page, prêt à transmettre")
            with r3:
                st.download_button(
                    "📝 Word", key="w_ent",
                    data=exporter_word(syn, devise=st.session_state.devise,
                                       titre=titre),
                    file_name=f"analyse_{horodatage}.docx",
                    mime="application/vnd.openxmlformats-officedocument."
                         "wordprocessingml.document",
                    use_container_width=True)
                st.caption("Modifiable")
        else:
            r2.caption("Le PDF et le Word détaillés demandent un relevé bancaire.")
    except Exception as err:
        st.error(f"Export indisponible : {err}")
        st.caption("Installez les dépendances :  "
                   "py -m pip install openpyxl reportlab python-docx")


# ---------------------------------------------------------------------------
# Assemblage
# ---------------------------------------------------------------------------

def afficher_entreprise() -> None:
    lecture_fc = st.session_state.get("lecture_fc")
    lecture_ff = st.session_state.get("lecture_ff")
    factures_clients = lecture_fc.factures if lecture_fc else []
    factures_fournisseurs = lecture_ff.factures if lecture_ff else []
    mouvements = st.session_state.get("mouvements") or []

    if not mouvements and not factures_clients and not factures_fournisseurs:
        st.info(commun.t("ent.trois_fichiers"))
        a, b, c = st.columns(3)
        a.markdown(f"#### 🏦 {commun.t('ent.releve')}\n{commun.t('ent.releve_quoi')}\n\n"
                   f"{commun.t('ent.releve_donne')}")
        b.markdown(f"#### 🧾 {commun.t('ent.factures_clients')}\n{commun.t('ent.fc_quoi')}\n\n"
                   f"{commun.t('ent.fc_donne')}")
        c.markdown(f"#### 📥 {commun.t('ent.factures_fourn')}\n{commun.t('ent.ff_quoi')}\n\n"
                   f"{commun.t('ent.ff_donne')}")
        st.divider()
        st.caption(commun.t("ent.formats"))
        return

    ind = calculer_indicateurs(
        mouvements=mouvements,
        factures_clients=factures_clients,
        factures_fournisseurs=factures_fournisseurs,
        tresorerie=solde_de_depart())

    syn = None
    if mouvements:
        try:
            from analyse_lisible import analyser_lisible
            syn = analyser_lisible(mouvements)
        except Exception:
            syn = None

    o1, o2, o3, o5, o4 = st.tabs(
        ["📈 " + commun.t("ent.tableau_bord"), "👥 " + commun.t("ent.clients_fourn"),
         "📅 " + commun.t("ent.tresorerie_prev"), "🔮 " + commun.t("sc.titre"),
         "📄 " + commun.t("rap.titre")])

    with o5:
        from vue_scenarios import afficher_scenarios
        afficher_scenarios("Entreprise")

    with o1:
        _tableau_de_bord(ind)

    with o2:
        _clients(ind, factures_clients, factures_fournisseurs)

    with o3:
        attendues = factures_vers_operations(factures_clients + factures_fournisseurs)
        if attendues:
            deja = {(o["libelle"], o["date"]) for o in st.session_state.operations}
            nouvelles = [o for o in attendues if (o["libelle"], o["date"]) not in deja]
            if nouvelles:
                st.info(f"**{len(nouvelles)} factures non réglées** peuvent être "
                        f"placées dans le calendrier à leur date d'échéance.")
                if st.button("Placer ces factures dans le calendrier",
                             type="primary", key="injecter"):
                    st.session_state.operations.extend(nouvelles)
                    commun.enregistrer()
                    st.rerun()
                st.caption("Les factures déjà en retard sont reportées au lendemain "
                           "et marquées incertaines : l'argent est attendu, "
                           "pas promis.")
                st.divider()

        if st.session_state.operations:
            afficher_calendrier(cle="ent", mots={
                "solde_actuel": "Trésorerie aujourd'hui",
                "point_bas": "Trésorerie au plus bas",
                "incertain": "Inclure les encaissements incertains",
                "aide_incertain": "Factures en retard, devis, commandes non fermes",
            })
        else:
            st.info("Aucune opération à projeter. Placez vos factures ci-dessus, "
                    "ou ajoutez vos échéances dans le panneau de gauche.")

    with o4:
        _rapport(ind, syn)
