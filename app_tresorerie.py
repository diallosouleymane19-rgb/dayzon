"""
PREVUFLOW — GESTION FINANCIÈRE
SMD Global Consulting LLC

Deux profils, un seul moteur :
  · Particulier — le calendrier budgétaire et l'analyse des dépenses ;
  · Entreprise  — les indicateurs financiers, les clients et la prévision.

Analyse financière pure : aucun plan comptable, aucun référentiel national.
Lancer :  streamlit run app_tresorerie.py
"""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st

import commun
from commun import DEVISES_PROPOSEES, RECURRENCES, formater, symbole
from moteur_tresorerie import Recurrence
from vue_compte import bandeau_essai, panneau_compte
from vue_comptes import panneau_comptes, panneau_sauvegarde, panneau_taux

st.set_page_config(page_title="PrevuFlow — Gestion financière",
                   page_icon="app/static/favicon.png", layout="wide",
                   initial_sidebar_state="expanded")

# Rend l'application installable sur téléphone et adapte l'affichage mobile.
import pwa
pwa.activer()

# Apparence commune : palette, cartes, adaptation téléphone.
import theme
theme.appliquer()

# Prépare la session et recharge la sauvegarde si elle existe.
commun.initialiser()


# ---------------------------------------------------------------------------
# Barre laterale
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("PrevuFlow")
    commun.selecteur_langue()
    st.caption(commun.t("app.signature"))

    panneau_compte()

    # L'abonnement est une page à part, pas un onglet : les onglets du profil
    # Particulier n'existent qu'une fois des données saisies, et quelqu'un
    # doit pouvoir s'abonner avant d'avoir rien tapé.
    if st.button(commun.t("abo.onglet"), use_container_width=True,
                 key="aller_abonnement"):
        st.session_state.page = "abonnement"
        st.rerun()

    st.divider()

    _PROFILS = ["Particulier", "Entreprise"]
    st.session_state.profil = st.radio(
        commun.t("app.profil_question"), _PROFILS, horizontal=True,
        index=_PROFILS.index(st.session_state.profil),
        format_func=lambda p: commun.t(
            "app.entreprise" if p == "Entreprise" else "app.particulier"))

    entreprise = st.session_state.profil == "Entreprise"
    st.caption(commun.t("app.sous_titre_ent" if entreprise
                        else "app.sous_titre_part"))

    st.divider()
    panneau_comptes(entreprise)
    panneau_taux()

    st.divider()
    st.subheader(commun.t("app.releve"))
    st.caption(commun.t("app.releve_aide"))

    fichier = st.file_uploader(commun.t("app.deposez"),
                               type=["pdf", "csv", "xlsx", "xls", "xlsm"],
                               label_visibility="collapsed")

    if fichier is not None and st.button(commun.t("app.analyser"),
                                         use_container_width=True, type="primary"):
        # La formule Decouverte n'ouvre qu'un fichier. On verifie avant de
        # lire : faire travailler quelqu'un puis lui refuser le resultat
        # serait la pire des facons de le lui apprendre.
        from vue_abonnement import limite_fichiers

        deja = commun.fichiers_importes()
        if deja >= limite_fichiers():
            st.warning(commun.t("app.limite_fichiers", n=limite_fichiers()))
            if st.button(commun.t("abo.voir_formules"), key="limite_fichier"):
                st.session_state.page = "abonnement"
                st.rerun()
        else:
            try:
                from import_intelligent import analyser
                resultat = analyser(fichier, fichier.name)
                st.session_state.analyse = resultat
                st.session_state.mouvements = resultat["mouvements"]
                st.session_state.nom_fichier = fichier.name
                commun.compter_import()
                st.rerun()
            except Exception as erreur:
                st.error(commun.t("app.lecture_ko", erreur=erreur))

    st.divider()

    if entreprise:
        from vue_abonnement import autorise
        if autorise("entreprise"):
            from vue_entreprise import barre_laterale_entreprise
            barre_laterale_entreprise()

    st.subheader(commun.t("app.ajout_echeance" if entreprise else "app.ajout_op"))

    with st.form("ajout", clear_on_submit=True):
        libelle = st.text_input(
            commun.t("app.intitule"),
            placeholder=commun.t("app.ph_ent" if entreprise else "app.ph_part"))
        c1, c2 = st.columns(2)
        with c1:
            sens = st.radio(commun.t("app.type"), ["entree", "sortie"],
                            horizontal=True,
                            format_func=lambda s: commun.t("app." + s))
        with c2:
            devise_op = st.selectbox(
                commun.t("app.devise"), DEVISES_PROPOSEES,
                index=DEVISES_PROPOSEES.index(st.session_state.devise)
                if st.session_state.devise in DEVISES_PROPOSEES else 0)
        montant = st.number_input(commun.t("app.montant"), min_value=0.0,
                                  value=0.0, step=50.0)
        date_op = st.date_input(commun.t("app.date"), value=date.today())
        recur = st.selectbox(commun.t("app.frequence"), list(RECURRENCES),
                             format_func=lambda r: commun.t("rec." + r))
        avec_fin = st.checkbox(commun.t("app.a_une_fin"))
        date_fin = (st.date_input(commun.t("app.jusquau"),
                                  value=date.today() + timedelta(days=365))
                    if avec_fin else None)
        certaine = st.checkbox(commun.t("app.certain"), value=True,
                               help=commun.t("app.aide_certain"))

        if st.form_submit_button(commun.t("app.ajouter"), use_container_width=True,
                                 type="primary"):
            if libelle and montant > 0:
                st.session_state.operations.append({
                    "libelle": libelle,
                    "montant": montant if sens == "entree" else -montant,
                    "date": date_op,
                    "devise": devise_op,
                    "recurrence": RECURRENCES[recur],
                    "date_fin": date_fin,
                    "certaine": certaine,
                })
                commun.enregistrer()
                st.rerun()
            else:
                st.warning(commun.t("app.faut_intitule"))

    if st.session_state.operations:
        st.divider()
        st.subheader(commun.t("app.operations_n",
                              n=len(st.session_state.operations)))
        for n, o in enumerate(st.session_state.operations):
            l1, l2 = st.columns([5, 1])
            marque = "" if o.get("certaine", True) else " ~"
            signe = "+" if o["montant"] > 0 else "−"
            l1.caption(f"{'▲' if o['montant'] > 0 else '▼'} {o['libelle']}{marque} · "
                       f"{signe}{commun.nombre(abs(o['montant']))} {o['devise']}")
            if l2.button("✕", key=f"del{n}"):
                st.session_state.operations.pop(n)
                commun.enregistrer()
                st.rerun()
        if st.button(commun.t("app.tout_effacer"), use_container_width=True):
            st.session_state.operations = []
            commun.enregistrer()
            st.rerun()

    st.divider()
    panneau_sauvegarde()
    pwa.message_installation()


# ---------------------------------------------------------------------------
# Corps — validation d'un import, commune aux deux profils
# ---------------------------------------------------------------------------

st.title(commun.t("app.titre_page") + " — " +
         commun.t("app.entreprise" if entreprise else "app.particulier"))

# Page d'abonnement : elle remplace tout le corps, dans les deux profils.
# Stripe renvoie sur `?paiement=ok` — on l'ouvre alors sans rien demander,
# sinon le règlement se terminerait sur un écran muet.
if (st.session_state.get("page") == "abonnement"
        or st.query_params.get("paiement")):
    from vue_abonnement import afficher_abonnement
    afficher_abonnement()
    if st.button(commun.t("app.retour"), key="quitter_abonnement"):
        st.session_state.pop("page", None)
        st.rerun()
    st.stop()

from vue_abonnement import bandeau_abonnement
bandeau_abonnement()
bandeau_essai()

if "analyse" in st.session_state:
    a = st.session_state.analyse
    st.success(commun.t("app.import_ok", fichier=st.session_state.nom_fichier,
                        n=len(a["mouvements"]),
                        debut=commun.date_longue(a["periode"][0]),
                        fin=commun.date_longue(a["periode"][1])))
    st.caption(commun.t("app.colonnes", resume=a["colonnes"].resume()))

    if not a["recurrences"]:
        st.warning(commun.t("app.pas_recurrence"))
        if st.button(commun.t("app.fermer")):
            del st.session_state.analyse
            st.rerun()
    else:
        st.markdown("### " + commun.t("app.n_recurrences",
                                      n=len(a["recurrences"])))
        st.caption(commun.t("app.decochez"))

        choix = []
        for n, r in enumerate(a["recurrences"]):
            c1, c2, c3, c4 = st.columns([0.5, 4, 1.5, 2])
            garder = c1.checkbox("garder", value=r.fiable, key=f"rec{n}",
                                 label_visibility="collapsed")
            c2.write(f"**{r.libelle[:44]}**")
            c2.caption(commun.t("app.occurrences", n=r.occurrences,
                                r=f"{r.regularite:.0%}",
                                date=commun.date_longue(r.prochaine_date)))
            c3.markdown(f":{'green' if r.montant > 0 else 'red'}"
                        f"[**{formater(r.montant)}**]")
            c4.write(r.recurrence.value)
            if garder:
                choix.append(r)

        b1, b2 = st.columns([1, 4])
        if b1.button(commun.t("app.valider"), type="primary",
                     use_container_width=True):
            for r in choix:
                st.session_state.operations.append({
                    "libelle": r.libelle,
                    "montant": float(r.montant),
                    "date": r.prochaine_date,
                    "devise": st.session_state.devise,
                    "recurrence": r.recurrence,
                    "date_fin": None,
                    "certaine": r.fiable,
                })
            del st.session_state.analyse
            commun.enregistrer()
            st.rerun()
        if b2.button(commun.t("app.annuler")):
            del st.session_state.analyse
            st.rerun()

    st.divider()


# ===========================================================================
# PROFIL ENTREPRISE
# ===========================================================================

if entreprise:
    from vue_abonnement import mur
    if mur("entreprise"):
        from vue_entreprise import afficher_entreprise
        afficher_entreprise()

# ===========================================================================
# PROFIL PARTICULIER
# ===========================================================================

else:
    a_des_mouvements = bool(st.session_state.get("mouvements"))
    a_des_operations = bool(st.session_state.operations)

    if not a_des_mouvements and not a_des_operations:
        st.info(commun.t("app.rien_encore"))

        st.markdown(commun.t("app.exemple_titre"))
        if st.button(commun.t("app.charger_exemple"), type="primary"):
            j = date.today()
            # L'exemple crée un vrai compte : la démonstration doit montrer
            # l'application telle qu'elle fonctionne, pas un cas particulier.
            portefeuille = commun.portefeuille()
            if portefeuille.vide:
                from comptes import Compte
                portefeuille.ajouter(Compte(commun.t("ex.compte"), "EUR",
                                            Decimal("2500")))
            st.session_state.operations = [
                {"libelle": commun.t("ex.salaire"), "montant": 2800,
                 "date": j.replace(day=min(28, j.day)), "devise": "EUR",
                 "recurrence": Recurrence.MENSUELLE, "certaine": True},
                {"libelle": commun.t("ex.loyer"), "montant": -950, "date": j.replace(day=5),
                 "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "certaine": True},
                {"libelle": commun.t("ex.credit"), "montant": -320, "date": j.replace(day=10),
                 "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "certaine": True},
                {"libelle": commun.t("ex.courses"), "montant": -120, "date": j,
                 "devise": "EUR", "recurrence": Recurrence.HEBDOMADAIRE,
                 "certaine": True},
                {"libelle": commun.t("ex.assurance"), "montant": -680,
                 "date": j + timedelta(days=25), "devise": "EUR",
                 "recurrence": Recurrence.ANNUELLE, "certaine": True},
                {"libelle": commun.t("ex.mission"), "montant": 1500,
                 "date": j + timedelta(days=40), "devise": "USD",
                 "recurrence": Recurrence.PONCTUELLE, "certaine": False},
            ]
            commun.enregistrer()
            st.rerun()
        st.stop()

    syn = None
    if a_des_mouvements:
        try:
            from analyse_lisible import analyser_lisible
            syn = analyser_lisible(st.session_state.mouvements)
        except Exception as err:
            st.error(f"Analyse impossible : {err}")

    if syn is not None:
        onglet_cal, onglet_ana, onglet_sce, onglet_rap = st.tabs(
            ["📅 " + commun.t("cal.titre"), "📊 " + commun.t("ana.titre_onglet"),
             "🔮 " + commun.t("sc.titre"), "📄 " + commun.t("rap.titre")])
    else:
        onglet_cal, onglet_sce = st.tabs(
            ["📅 " + commun.t("cal.titre"), "🔮 " + commun.t("sc.titre")])
        onglet_ana = onglet_rap = None

    with onglet_sce:
        from vue_abonnement import mur
        if mur("scenarios"):
            from vue_scenarios import afficher_scenarios
            afficher_scenarios("Particulier")

    # --- Calendrier ---
    with onglet_cal:
        if not a_des_operations:
            st.info(commun.t("app.rien_a_projeter"))
        else:
            from vue_calendrier import afficher_calendrier
            afficher_calendrier(cle="part")

    # --- Mon analyse ---
    if onglet_ana is not None:
        with onglet_ana:
            st.subheader(commun.t("ana.titre"))
            c_a, c_b, c_c = st.columns(3)
            c_a.metric(commun.t("ana.rentre"), formater(syn.entrees_par_mois))
            c_b.metric(commun.t("ana.sort"), formater(syn.sorties_par_mois))
            c_c.metric(commun.t("ana.reste"), formater(syn.reste_par_mois),
                       delta=commun.t("ana.pct_revenus",
                                      p=f"{syn.taux_epargne:.0f}"),
                       delta_color="normal" if syn.reste_par_mois >= 0 else "inverse")

            c_d, c_e = st.columns(2)
            c_d.metric(commun.t("ana.charges_fixes"), formater(syn.charges_fixes),
                       delta=commun.t("ana.pct_charges",
                                      p=f"{syn.part_fixe:.0f}"),
                       delta_color="off")
            c_e.metric(commun.t("ana.variables"), formater(syn.depenses_variables),
                       delta=commun.t("ana.agir"), delta_color="off")

            st.divider()
            st.subheader(commun.t("ana.ce_que_ca_veut"))
            for niveau, texte in syn.messages(
                    commun.t, commun.nombre, symbole(st.session_state.devise)):
                theme.message_phrase(niveau, texte)

            st.divider()
            col_g, col_d = st.columns([3, 2])

            with col_g:
                st.subheader(commun.t("ana.postes"))
                for p in syn.postes[:12]:
                    p1, p2 = st.columns([3, 2])
                    p1.write(f"{'🟢' if p.est_une_entree else '🔴'} **{p.nom}**")
                    p1.caption(f"{p.categorie}"
                               f"{' · ' + commun.t('ana.charge_fixe') if p.fixe else ''}"
                               f" — {p.phrase(commun.t, commun.nombre, symbole(st.session_state.devise))}")
                    p2.markdown(
                        f"<div style='text-align:right;font-size:15px;font-weight:600;"
                        f"color:{'#1F7244' if p.est_une_entree else '#C0392B'}'>"
                        f"{formater(p.par_mois)}<br>"
                        f"<span style='font-size:11px;color:#888;font-weight:400'>"
                        f"{commun.t('ana.par_mois')}</span></div>",
                        unsafe_allow_html=True)

            with col_d:
                st.subheader(commun.t("ana.par_categorie"))
                depenses = {k: abs(float(v)) for k, v in syn.par_categorie.items()
                            if float(v) < 0}
                if depenses:
                    st.bar_chart(pd.Series(depenses).sort_values(), horizontal=True,
                                 height=min(420, 34 * len(depenses)))

    # --- Rapport ---
    if onglet_rap is not None:
        with onglet_rap:
            from vue_abonnement import mur
            if mur("exports"):
                st.subheader(commun.t("rap.telecharger"))
                st.caption(commun.t("rap.aide"))

                nom_rapport = st.text_input(commun.t("rap.titre_rapport"),
                                            value=commun.t("rap.valeur_titre"))
                horodatage = date.today().strftime("%Y%m%d")

                r1, r2, r3 = st.columns(3)
                try:
                    from export_rapport import exporter_excel, exporter_pdf, exporter_word
                    with r1:
                        st.download_button(
                            "📊 Excel",
                            data=exporter_excel(syn, st.session_state.mouvements,
                                                devise=st.session_state.devise,
                                                titre=nom_rapport, t=commun.t,
                                              nombre=commun.formater_court),
                            file_name=f"analyse_{horodatage}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument."
                                 "spreadsheetml.sheet",
                            use_container_width=True, type="primary")
                        st.caption(commun.t("rap.excel_aide"))
                    with r2:
                        st.download_button(
                            "📄 PDF",
                            data=exporter_pdf(syn, devise=st.session_state.devise,
                                              titre=nom_rapport, t=commun.t,
                                              nombre=commun.formater_court),
                            file_name=f"analyse_{horodatage}.pdf",
                            mime="application/pdf", use_container_width=True)
                        st.caption(commun.t("rap.pdf_aide"))
                    with r3:
                        st.download_button(
                            "📝 Word",
                            data=exporter_word(syn, devise=st.session_state.devise,
                                               titre=nom_rapport, t=commun.t,
                                              nombre=commun.formater_court),
                            file_name=f"analyse_{horodatage}.docx",
                            mime="application/vnd.openxmlformats-officedocument."
                                 "wordprocessingml.document",
                            use_container_width=True)
                        st.caption(commun.t("rap.word_aide"))
                except Exception as err:
                    st.error(commun.t("rap.export_ko", erreur=err))
                    st.caption("Installez les dépendances :  "
                               "py -m pip install openpyxl reportlab python-docx")

                st.divider()
                st.subheader(commun.t("rap.apercu"))
                st.dataframe(pd.DataFrame([{
                    commun.t("col.poste"): p.nom,
                    commun.t("col.categorie"): p.categorie,
                    commun.t("col.type"): commun.t("col.charge_fixe") if p.fixe else (
                        commun.t("app.entree") if p.est_une_entree
                        else commun.t("col.variable")),
                    commun.t("col.nombre"): p.nombre,
                    commun.t("col.par_mois"): float(p.par_mois),
                } for p in syn.postes]), use_container_width=True, hide_index=True)


st.caption("PrevuFlow — SMD Global Consulting LLC · " +
           commun.t("gen.avertissement"))
