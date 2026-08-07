"""
DAYZON — GESTION FINANCIÈRE
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
from commun import DEVISES_PROPOSEES, LIBELLES_RECURRENCE, formater, symbole
from moteur_tresorerie import Recurrence
from vue_compte import bandeau_essai, panneau_compte
from vue_comptes import panneau_comptes, panneau_sauvegarde, panneau_taux

st.set_page_config(page_title="Dayzon — Gestion financière",
                   page_icon="app/static/favicon.png", layout="wide",
                   initial_sidebar_state="expanded")

# Rend l'application installable sur téléphone et adapte l'affichage mobile.
import pwa
pwa.activer()

# Prépare la session et recharge la sauvegarde si elle existe.
commun.initialiser()


# ---------------------------------------------------------------------------
# Barre laterale
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Dayzon")
    commun.selecteur_langue()
    st.caption(commun.t("app.signature"))

    panneau_compte()
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
    st.subheader("🏦 Relevé bancaire")
    st.caption("PDF, CSV ou Excel. Les colonnes et les opérations récurrentes "
               "sont reconnues automatiquement.")

    fichier = st.file_uploader("Déposez votre relevé",
                               type=["pdf", "csv", "xlsx", "xls", "xlsm"],
                               label_visibility="collapsed")

    if fichier is not None and st.button("Analyser le relevé",
                                         use_container_width=True, type="primary"):
        try:
            from import_intelligent import analyser
            resultat = analyser(fichier, fichier.name)
            st.session_state.analyse = resultat
            st.session_state.mouvements = resultat["mouvements"]
            st.session_state.nom_fichier = fichier.name
            st.rerun()
        except Exception as erreur:
            st.error(f"Lecture impossible : {erreur}")

    st.divider()

    if entreprise:
        from vue_entreprise import barre_laterale_entreprise
        barre_laterale_entreprise()

    st.subheader("Ajouter une échéance" if entreprise else "Ajouter une opération")

    with st.form("ajout", clear_on_submit=True):
        libelle = st.text_input(
            "Intitulé",
            placeholder="Facture client, loyer, salaires..." if entreprise
            else "Salaire, loyer, courses...")
        c1, c2 = st.columns(2)
        with c1:
            sens = st.radio("Type", ["Entrée", "Sortie"], horizontal=True)
        with c2:
            devise_op = st.selectbox(
                "Devise", DEVISES_PROPOSEES,
                index=DEVISES_PROPOSEES.index(st.session_state.devise)
                if st.session_state.devise in DEVISES_PROPOSEES else 0)
        montant = st.number_input("Montant", min_value=0.0, value=0.0, step=50.0)
        date_op = st.date_input("Date", value=date.today())
        recur = st.selectbox("Fréquence", list(LIBELLES_RECURRENCE))
        avec_fin = st.checkbox("Cette opération a une fin")
        date_fin = (st.date_input("Jusqu'au", value=date.today() + timedelta(days=365))
                    if avec_fin else None)
        certaine = st.checkbox(
            "Montant certain", value=True,
            help="Décochez pour un devis ou une rentrée hypothétique")

        if st.form_submit_button("Ajouter", use_container_width=True, type="primary"):
            if libelle and montant > 0:
                st.session_state.operations.append({
                    "libelle": libelle,
                    "montant": montant if sens == "Entrée" else -montant,
                    "date": date_op,
                    "devise": devise_op,
                    "recurrence": LIBELLES_RECURRENCE[recur],
                    "date_fin": date_fin,
                    "certaine": certaine,
                })
                commun.enregistrer()
                st.rerun()
            else:
                st.warning("Il faut un intitulé et un montant.")

    if st.session_state.operations:
        st.divider()
        st.subheader(f"Opérations ({len(st.session_state.operations)})")
        for n, o in enumerate(st.session_state.operations):
            l1, l2 = st.columns([5, 1])
            marque = "" if o.get("certaine", True) else " ~"
            l1.caption(f"{'▲' if o['montant'] > 0 else '▼'} {o['libelle']}{marque} · "
                       f"{o['montant']:+,.0f} {o['devise']}")
            if l2.button("✕", key=f"del{n}"):
                st.session_state.operations.pop(n)
                commun.enregistrer()
                st.rerun()
        if st.button("Tout effacer", use_container_width=True):
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

bandeau_essai()

if "analyse" in st.session_state:
    a = st.session_state.analyse
    st.success(f"**{st.session_state.nom_fichier}** — {len(a['mouvements'])} mouvements "
               f"lus du {a['periode'][0].strftime('%d/%m/%Y')} au "
               f"{a['periode'][1].strftime('%d/%m/%Y')}")
    st.caption(f"Colonnes reconnues : {a['colonnes'].resume()}")

    if not a["recurrences"]:
        st.warning("Aucune opération récurrente identifiée. Il faut au moins "
                   "3 occurrences régulières. Votre analyse reste disponible "
                   "dans les onglets ci-dessous.")
        if st.button("Fermer ce message"):
            del st.session_state.analyse
            st.rerun()
    else:
        st.markdown(f"### {len(a['recurrences'])} opérations récurrentes détectées")
        st.caption("Décochez celles que vous ne voulez pas projeter, puis validez.")

        choix = []
        for n, r in enumerate(a["recurrences"]):
            c1, c2, c3, c4 = st.columns([0.5, 4, 1.5, 2])
            garder = c1.checkbox("garder", value=r.fiable, key=f"rec{n}",
                                 label_visibility="collapsed")
            c2.write(f"**{r.libelle[:44]}**")
            c2.caption(f"{r.occurrences} occurrences · régularité {r.regularite:.0%} · "
                       f"prochaine le {r.prochaine_date.strftime('%d/%m/%Y')}")
            c3.markdown(f":{'green' if r.montant > 0 else 'red'}"
                        f"[**{formater(r.montant)}**]")
            c4.write(r.recurrence.value)
            if garder:
                choix.append(r)

        b1, b2 = st.columns([1, 4])
        if b1.button("Valider", type="primary", use_container_width=True):
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
        if b2.button("Annuler l'import"):
            del st.session_state.analyse
            st.rerun()

    st.divider()


# ===========================================================================
# PROFIL ENTREPRISE
# ===========================================================================

if entreprise:
    from vue_entreprise import afficher_entreprise
    afficher_entreprise()

# ===========================================================================
# PROFIL PARTICULIER
# ===========================================================================

else:
    a_des_mouvements = bool(st.session_state.get("mouvements"))
    a_des_operations = bool(st.session_state.operations)

    if not a_des_mouvements and not a_des_operations:
        st.info("Importez un relevé bancaire ou ajoutez vos revenus et vos dépenses "
                "dans le panneau de gauche. Le calendrier affichera votre solde "
                "pour chaque jour à venir.")

        st.markdown("#### Vous pouvez aussi partir d'un exemple")
        if st.button("Charger un exemple", type="primary"):
            j = date.today()
            # L'exemple crée un vrai compte : la démonstration doit montrer
            # l'application telle qu'elle fonctionne, pas un cas particulier.
            portefeuille = commun.portefeuille()
            if portefeuille.vide:
                from comptes import Compte
                portefeuille.ajouter(Compte("Compte courant", "EUR",
                                            Decimal("2500")))
            st.session_state.operations = [
                {"libelle": "Salaire", "montant": 2800,
                 "date": j.replace(day=min(28, j.day)), "devise": "EUR",
                 "recurrence": Recurrence.MENSUELLE, "certaine": True},
                {"libelle": "Loyer", "montant": -950, "date": j.replace(day=5),
                 "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "certaine": True},
                {"libelle": "Crédit auto", "montant": -320, "date": j.replace(day=10),
                 "devise": "EUR", "recurrence": Recurrence.MENSUELLE, "certaine": True},
                {"libelle": "Courses", "montant": -120, "date": j,
                 "devise": "EUR", "recurrence": Recurrence.HEBDOMADAIRE,
                 "certaine": True},
                {"libelle": "Assurance", "montant": -680,
                 "date": j + timedelta(days=25), "devise": "EUR",
                 "recurrence": Recurrence.ANNUELLE, "certaine": True},
                {"libelle": "Mission freelance", "montant": 1500,
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
            ["📅 Calendrier", "📊 Mon analyse", "🔮 Scénarios", "📄 Rapport"])
    else:
        onglet_cal, onglet_sce = st.tabs(["📅 Calendrier", "🔮 Scénarios"])
        onglet_ana = onglet_rap = None

    with onglet_sce:
        from vue_scenarios import afficher_scenarios
        afficher_scenarios("Particulier")

    # --- Calendrier ---
    with onglet_cal:
        if not a_des_operations:
            st.info("Aucune opération à projeter pour le moment. Validez les "
                    "récurrences détectées ci-dessus, ou ajoutez vos revenus "
                    "et charges dans le panneau de gauche.")
        else:
            from vue_calendrier import afficher_calendrier
            afficher_calendrier(cle="part")

    # --- Mon analyse ---
    if onglet_ana is not None:
        with onglet_ana:
            st.subheader("Vos chiffres, chaque mois")
            c_a, c_b, c_c = st.columns(3)
            c_a.metric("Ce qui rentre", formater(syn.entrees_par_mois))
            c_b.metric("Ce qui sort", formater(syn.sorties_par_mois))
            c_c.metric("Il vous reste", formater(syn.reste_par_mois),
                       delta=f"{syn.taux_epargne:.0f} % de vos revenus",
                       delta_color="normal" if syn.reste_par_mois >= 0 else "inverse")

            c_d, c_e = st.columns(2)
            c_d.metric("Charges fixes", formater(syn.charges_fixes),
                       delta=f"{syn.part_fixe:.0f} % des revenus", delta_color="off")
            c_e.metric("Dépenses variables", formater(syn.depenses_variables),
                       delta="sur lesquelles vous pouvez agir", delta_color="off")

            st.divider()
            st.subheader("Ce que ça veut dire")
            for niveau, texte in syn.messages():
                {"alerte": st.error, "attention": st.warning,
                 "bon": st.success}.get(niveau, st.info)(texte)

            st.divider()
            col_g, col_d = st.columns([3, 2])

            with col_g:
                st.subheader("Vos principaux postes")
                for p in syn.postes[:12]:
                    p1, p2 = st.columns([3, 2])
                    p1.write(f"{'🟢' if p.est_une_entree else '🔴'} **{p.nom}**")
                    p1.caption(f"{p.categorie}{' · charge fixe' if p.fixe else ''} "
                               f"— {p.phrase()}")
                    p2.markdown(
                        f"<div style='text-align:right;font-size:15px;font-weight:600;"
                        f"color:{'#1F7244' if p.est_une_entree else '#C0392B'}'>"
                        f"{formater(p.par_mois)}<br>"
                        f"<span style='font-size:11px;color:#888;font-weight:400'>"
                        f"par mois</span></div>", unsafe_allow_html=True)

            with col_d:
                st.subheader("Par catégorie")
                depenses = {k: abs(float(v)) for k, v in syn.par_categorie.items()
                            if float(v) < 0}
                if depenses:
                    st.bar_chart(pd.Series(depenses).sort_values(), horizontal=True,
                                 height=min(420, 34 * len(depenses)))

    # --- Rapport ---
    if onglet_rap is not None:
        with onglet_rap:
            st.subheader("Télécharger votre analyse")
            st.caption("Le rapport reprend vos chiffres clés, vos postes de dépense "
                       "et la répartition par catégorie.")

            nom_rapport = st.text_input("Titre du rapport", value="Analyse financière")
            horodatage = date.today().strftime("%Y%m%d")

            r1, r2, r3 = st.columns(3)
            try:
                from export_rapport import exporter_excel, exporter_pdf, exporter_word
                with r1:
                    st.download_button(
                        "📊 Excel",
                        data=exporter_excel(syn, st.session_state.mouvements,
                                            devise=st.session_state.devise,
                                            titre=nom_rapport),
                        file_name=f"analyse_{horodatage}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument."
                             "spreadsheetml.sheet",
                        use_container_width=True, type="primary")
                    st.caption("4 feuilles, filtrables")
                with r2:
                    st.download_button(
                        "📄 PDF",
                        data=exporter_pdf(syn, devise=st.session_state.devise,
                                          titre=nom_rapport),
                        file_name=f"analyse_{horodatage}.pdf",
                        mime="application/pdf", use_container_width=True)
                    st.caption("Une page, prêt à transmettre")
                with r3:
                    st.download_button(
                        "📝 Word",
                        data=exporter_word(syn, devise=st.session_state.devise,
                                           titre=nom_rapport),
                        file_name=f"analyse_{horodatage}.docx",
                        mime="application/vnd.openxmlformats-officedocument."
                             "wordprocessingml.document",
                        use_container_width=True)
                    st.caption("Modifiable, à personnaliser")
            except Exception as err:
                st.error(f"Export indisponible : {err}")
                st.caption("Installez les dépendances :  "
                           "py -m pip install openpyxl reportlab python-docx")

            st.divider()
            st.subheader("Aperçu du contenu")
            st.dataframe(pd.DataFrame([{
                "Poste": p.nom,
                "Catégorie": p.categorie,
                "Type": "Charge fixe" if p.fixe else (
                    "Entrée" if p.est_une_entree else "Variable"),
                "Nombre": p.nombre,
                "Par mois": float(p.par_mois),
            } for p in syn.postes]), use_container_width=True, hide_index=True)


st.caption("Dayzon — SMD Global Consulting LLC · " +
           commun.t("gen.avertissement"))
