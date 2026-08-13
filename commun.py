"""
ELEMENTS PARTAGES ENTRE LES DEUX PROFILS
PrevuFlow — SMD Global Consulting LLC

Devises, formatage, portefeuille et projection : un seul endroit, une seule
vérité. Ce module fait le lien entre le noyau pur (`argent`, `comptes`,
`moteur_tresorerie`, `sauvegarde`) et l'état de la session Streamlit.

Il ne contient aucune règle financière : celles-ci vivent dans les modules
purs, testables sans interface.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import streamlit as st

import argent
import langues as lg
import sauvegarde as sv
from argent import (Conversion, ErreurArgent, Montant, TableTaux, Taux,
                    nom_devise, table_par_defaut, valider_devise)
from comptes import (Compte, Consolidation, ErreurCompte, Portefeuille,
                     portefeuille_depuis_solde_unique)
from moteur_tresorerie import Operation, Recurrence, Tresorerie, TauxChange

# Devises proposées dans les menus. La liste vient d'`argent`, qui est la
# seule source de vérité : deux tables de devises finiraient par diverger.
DEVISES_PROPOSEES = argent.DEVISES_PROPOSEES

MOIS_FR = {1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
           5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
           9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"}

# La clé est stable et jamais affichée : ce que l'utilisateur lit passe par
# la traduction. Une application multilingue ne peut pas dépendre d'un
# libellé français pour retrouver une valeur — changer la langue casserait
# la lecture des données enregistrées.
RECURRENCES = {
    "ponctuelle":   Recurrence.PONCTUELLE,
    "hebdo":        Recurrence.HEBDOMADAIRE,
    "bimensuelle":  Recurrence.BIMENSUELLE,
    "mensuelle":    Recurrence.MENSUELLE,
    "trimestrielle": Recurrence.TRIMESTRIELLE,
    "annuelle":     Recurrence.ANNUELLE,
}

# Conservé pour compatibilité : d'anciennes sauvegardes portent le libellé
# français en clair.
LIBELLES_RECURRENCE = {
    "Une seule fois":        Recurrence.PONCTUELLE,
    "Chaque semaine":        Recurrence.HEBDOMADAIRE,
    "Toutes les 2 semaines": Recurrence.BIMENSUELLE,
    "Chaque mois":           Recurrence.MENSUELLE,
    "Chaque trimestre":      Recurrence.TRIMESTRIELLE,
    "Chaque année":          Recurrence.ANNUELLE,
}

# Conservé pour les modules qui l'importent encore. Construit à partir
# d'`argent`, donc jamais en désaccord avec lui.
DEVISES: dict[str, tuple[str, Decimal]] = {
    d: (argent.symbole(d), Decimal("1")) for d in DEVISES_PROPOSEES
}


# ---------------------------------------------------------------------------
# État de session
# ---------------------------------------------------------------------------

def initialiser() -> None:
    """
    Prépare l'état de session, en rechargeant la sauvegarde si elle existe.

    Appelée une fois au démarrage. Toute erreur de lecture est signalée à
    l'écran mais n'empêche jamais l'application de s'ouvrir : on ne bloque
    pas quelqu'un hors de son propre outil.
    """
    if st.session_state.get("_initialise"):
        return

    st.session_state.setdefault("profil", "Particulier")
    st.session_state.setdefault("devise", "EUR")
    st.session_state.setdefault("operations", [])
    st.session_state.setdefault("portefeuille", Portefeuille(devise_reference="EUR"))
    st.session_state.setdefault("taux", table_par_defaut())
    # L'enregistrement automatique n'a de sens que sur le poste de
    # l'utilisateur. En ligne, il exporterait ses données vers un fichier
    # partagé avec les autres visiteurs.
    st.session_state.setdefault("sauvegarde_auto", sv.mode_local())
    st.session_state.setdefault("message_demarrage", None)

    # En ligne, `charger()` renvoie None de lui-même : le fichier du serveur
    # appartiendrait à un autre visiteur.
    try:
        donnees = sv.charger()
    except sv.ErreurSauvegarde as err:
        st.session_state.message_demarrage = ("attention", str(err))
        donnees = None

    if donnees is not None and not donnees.vide:
        _appliquer(donnees)
        st.session_state.message_demarrage = (
            "info", f"Données rechargées : {donnees.resume()}.")

    st.session_state._initialise = True


def _appliquer(donnees: sv.Donnees) -> None:
    """Recharge une sauvegarde dans la session."""
    st.session_state.profil = donnees.profil or "Particulier"
    st.session_state.devise = donnees.devise_reference or "EUR"
    if getattr(donnees, "langue", None):
        st.session_state.langue = donnees.langue
    st.session_state.portefeuille = Portefeuille.depuis_liste(
        donnees.comptes, donnees.devise_reference or "EUR")

    operations = []
    for o in donnees.operations or []:
        o = dict(o)
        valeur = o.get("recurrence")
        if isinstance(valeur, str):
            o["recurrence"] = next(
                (r for r in Recurrence if r.value == valeur), Recurrence.PONCTUELLE)
        operations.append(o)
    st.session_state.operations = operations

    if donnees.taux:
        table = TableTaux()
        for t in donnees.taux:
            try:
                table.ajouter(Taux(
                    base=t["base"], contre=t["contre"],
                    valeur=Decimal(str(t["valeur"])),
                    observe_le=date.fromisoformat(str(t["observe_le"])),
                    source=t.get("source", "saisie manuelle")))
            except (KeyError, ValueError, ErreurArgent):
                continue            # un taux abîmé ne doit pas bloquer le reste
        if table.devises_connues:
            st.session_state.taux = table


def portefeuille() -> Portefeuille:
    return st.session_state.portefeuille


def taux() -> TableTaux:
    return st.session_state.taux


def devise_reference() -> str:
    return st.session_state.get("devise", "EUR")


# ---------------------------------------------------------------------------
# Sauvegarde
# ---------------------------------------------------------------------------

def _operations_serialisables() -> list[dict]:
    sortie = []
    for o in st.session_state.operations:
        o = dict(o)
        recurrence = o.get("recurrence")
        if isinstance(recurrence, Recurrence):
            o["recurrence"] = recurrence.value
        o["montant"] = Decimal(str(o["montant"]))
        sortie.append(o)
    return sortie


def enregistrer(force: bool = False) -> bool:
    """
    Enregistre l'état courant, là où il doit aller.

    Trois situations, et l'utilisateur n'a jamais à choisir :

      · connecté        → en base, sur son compte, depuis n'importe quel appareil ;
      · local sans compte → dans un fichier sur son ordinateur ;
      · en ligne sans compte → nulle part, et l'écran le dit franchement.

    Appelée après chaque modification. Personne ne devrait avoir à penser
    à cliquer sur « Enregistrer » : on l'oublie exactement le jour où ça
    compte.
    """
    # --- Connecté : la base fait autorité -------------------------------
    try:
        import compte
        if compte.connecte():
            return _enregistrer_en_base(force)
    except ImportError:
        pass

    # --- En ligne sans compte : rien à enregistrer -----------------------
    if not sv.mode_local():
        return False

    # --- Local : fichier sur le poste -----------------------------------
    if not force and not st.session_state.get("sauvegarde_auto", True):
        return False

    donnees = donnees_courantes()
    try:
        sv.enregistrer(donnees)
        st.session_state.derniere_sauvegarde = donnees.enregistre_le
        st.session_state.erreur_sauvegarde = None
        st.session_state.modifications_en_attente = False
        return True
    except sv.ErreurSauvegarde as err:
        st.session_state.erreur_sauvegarde = str(err)
        if force:
            raise
        return False


def _enregistrer_en_base(force: bool = False) -> bool:
    """Écrit dans le compte de l'utilisateur connecté."""
    import compte
    from datetime import datetime

    donnees = donnees_courantes()
    try:
        compte.enregistrer_espace(
            profil=donnees.profil,
            devise_reference=donnees.devise_reference,
            comptes=donnees.comptes,
            operations=donnees.operations,
            taux=donnees.taux)
    except compte.ErreurCompte as err:
        st.session_state.erreur_sauvegarde = str(err)
        st.session_state.modifications_en_attente = True
        if force:
            raise
        return False

    st.session_state.dernier_enregistrement_base = \
        datetime.now().strftime("%H:%M")
    st.session_state.erreur_sauvegarde = None
    st.session_state.modifications_en_attente = False
    return True


def _taux_uniques(table: TableTaux) -> list[Taux]:
    """Une paire et son inverse décrivent le même taux : on n'en garde qu'un."""
    vus: dict[tuple[str, str], Taux] = {}
    for t in table._taux.values():
        cle = tuple(sorted((t.base, t.contre)))
        if cle not in vus:
            vus[cle] = t
    return list(vus.values())


# ---------------------------------------------------------------------------
# Formatage
# ---------------------------------------------------------------------------

def symbole(devise: str | None = None) -> str:
    return argent.symbole(devise or devise_reference())


def formater(montant, devise: str | None = None) -> str:
    """
    Un montant écrit selon la langue de lecture.

    « 1 234,56 € » en français, « $1,234.56 » en anglais : ce n'est pas
    une coquetterie, c'est ce qui évite qu'un lecteur espagnol comprenne
    mille là où un anglophone lit un.
    """
    if isinstance(montant, Montant):
        return lg.formater_montant(montant.valeur, montant.devise, langue())
    d = devise or devise_reference()
    return lg.formater_montant(Montant.de(montant, d).valeur, d, langue())


def formater_court(montant, devise: str | None = None) -> str:
    """
    Un montant, avec les decimales de sa devise.

    Le nom vient d'une version qui supprimait les centimes. Ils sont
    retablis : sur un outil de tresorerie, « 7 650 » et « 7 650,00 » ne
    disent pas la meme chose — le premier laisse croire a un arrondi.

    Le nombre de decimales reste celui de la devise, jamais deux par
    defaut : l'euro et le dollar en ont deux, le yen et le franc CFA
    aucune, le dinar koweitien trois.
    """
    if isinstance(montant, Montant):
        return lg.formater_montant(montant.valeur, montant.devise, langue())
    d = devise or devise_reference()
    return lg.formater_montant(Montant.de(montant, d).valeur, d, langue())


def formater_date(jour) -> str:
    """Une date écrite selon la langue de lecture."""
    return lg.formater_date(jour, langue())


def afficher(montant) -> str:
    """
    Un objet `Montant` écrit selon la langue de lecture.

    `Montant.formater()` applique toujours la typographie française : le
    module `argent` est volontairement pur et ne connaît pas la langue.
    C'est ici, et seulement ici, que la présentation devient localisée.
    Toute vue qui appelle `montant.formater()` directement affichera un
    montant français à un lecteur anglophone.
    """
    return lg.formater_montant(montant.valeur, montant.devise, langue())


def nombre(valeur, decimales: int | None = None) -> str:
    """
    Un nombre nu, aux separateurs de la langue.

    Sert la ou la devise est deja connue du contexte — les cases du
    calendrier, par exemple, ou la repeter sur chaque jour surchargerait
    la grille sans rien apporter.

    Sans precision, le nombre de decimales est celui de la devise de
    reference : deux pour l'euro et le dollar, aucune pour le yen.
    """
    if decimales is None:
        decimales = argent.decimales(devise_reference())
    return lg.formater_nombre(valeur, decimales, langue())


def date_longue(jour) -> str:
    """Date complète : 07/08/2026, 07 Aug 2026, 2026年08月07日."""
    return lg.formater_date(jour, langue())


def date_courte(jour) -> str:
    """
    Date sans l'année, pour les indicateurs où la place manque.

    Le jour et le mois ne s'ordonnent pas pareil partout : « 08/07 » se lit
    juillet aux États-Unis et août en France. On garde donc l'ordre de la
    langue, en retirant seulement l'année du motif complet.
    """
    l = lg.locale(langue())
    if l.code == "zh":
        return f"{jour.month}月{jour.day}日"
    if l.code == "en":
        return lg.formater_date(jour, "en")[:6]        # « 07 Aug »
    return jour.strftime("%d/%m")


def nom_mois(numero: int) -> str:
    return lg.nom_mois(numero, langue())


def jours_semaine() -> list[str]:
    return lg.jours_semaine(langue())


def premier_jour() -> int:
    """0 = lundi, 6 = dimanche — pour `calendar.Calendar(firstweekday=…)`."""
    return lg.locale(langue()).premier_jour_semaine


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

def solde_de_depart() -> Decimal:
    """
    Le point de départ de la projection : le total consolidé du portefeuille.

    Si la consolidation échoue faute de taux, on se replie sur les seuls
    comptes déjà dans la devise de référence, et l'interface le signale.
    Mieux vaut une projection partielle et annoncée qu'un total inventé.
    """
    p = portefeuille()
    if p.vide:
        return Decimal("0")
    try:
        return p.consolider(taux(), devise_reference()).total.valeur
    except ErreurCompte:
        return p.solde_devise(devise_reference()).valeur


def consolidation() -> Consolidation | None:
    """La consolidation complète, avec ses taux. None si elle est impossible."""
    p = portefeuille()
    if p.vide:
        return None
    try:
        return p.consolider(taux(), devise_reference())
    except ErreurCompte:
        return None


def construire_tresorerie(operations: list[dict] | None = None,
                          solde_initial=None,
                          devise: str | None = None) -> Tresorerie:
    """Assemble la projection à partir des opérations en mémoire."""
    operations = (st.session_state.operations if operations is None else operations)
    solde = solde_de_depart() if solde_initial is None else solde_initial
    dev = devise or devise_reference()

    table = taux()
    conversions: dict[str, Decimal] = {dev: Decimal("1")}
    for d in {o.get("devise", dev) for o in operations}:
        if d == dev:
            continue
        trouve = table.trouver(d, dev)
        if trouve is not None:
            conversions[d] = trouve.valeur

    t = Tresorerie(solde_initial=Decimal(str(solde)), devise=dev,
                   taux=TauxChange(dev, conversions))
    for o in operations:
        t.ajouter(Operation(
            libelle=o["libelle"],
            montant=Decimal(str(o["montant"])),
            date_operation=o["date"],
            devise=o.get("devise", dev),
            recurrence=o.get("recurrence", Recurrence.PONCTUELLE),
            date_fin=o.get("date_fin"),
            categorie=o.get("categorie", ""),
            certaine=o.get("certaine", True),
        ))
    return t


# ---------------------------------------------------------------------------
# Compatibilité avec l'ancien réglage
# ---------------------------------------------------------------------------

def solde_initial_compatible() -> float:
    """
    Ancien nom du point de départ, encore lu par quelques vues.
    Conservé le temps que toutes basculent sur `solde_de_depart()`.
    """
    return float(solde_de_depart())


# ---------------------------------------------------------------------------
# Emporter et reprendre ses données
# ---------------------------------------------------------------------------

def donnees_courantes() -> sv.Donnees:
    """L'état de la session, sous une forme enregistrable."""
    return sv.Donnees(
        profil=st.session_state.get("profil", "Particulier"),
        devise_reference=devise_reference(),
        langue=st.session_state.get("langue", "fr"),
        comptes=portefeuille().vers_liste(),
        operations=_operations_serialisables(),
        taux=[{"base": t.base, "contre": t.contre, "valeur": str(t.valeur),
               "observe_le": t.observe_le.isoformat(), "source": t.source}
              for t in _taux_uniques(taux())],
    )


def exporter_octets() -> bytes:
    """Le fichier de sauvegarde, prêt à être téléchargé."""
    return sv.vers_octets(donnees_courantes())


def importer_octets(donnees_brutes: bytes) -> sv.Donnees:
    """Reprend une sauvegarde déposée par l'utilisateur."""
    donnees = sv.depuis_octets(donnees_brutes)
    _appliquer(donnees)
    return donnees


# ---------------------------------------------------------------------------
# Fichiers importés — le décompte de la formule
# ---------------------------------------------------------------------------

def fichiers_importes() -> int:
    """
    Combien de fichiers ont été importés ce mois-ci.

    En base pour qui a un compte, en session sinon. Le compteur vivait
    uniquement dans la session : un rechargement de page le remettait à
    zéro, et la limite d'un fichier se contournait sans le vouloir.

    Le visiteur sans compte garde le compteur de session. Contourner la
    limite lui coûterait de tout ressaisir, puisqu'il perd aussi ses
    données au rechargement.
    """
    import compte

    if compte.connecte():
        if "imports_du_mois" not in st.session_state:
            st.session_state.imports_du_mois = compte.imports_du_mois()
        return st.session_state.imports_du_mois
    return st.session_state.get("fichiers_importes", 0)


def compter_import() -> None:
    """Enregistre un fichier de plus, en base si un compte existe."""
    import compte

    if compte.connecte():
        st.session_state.imports_du_mois = compte.enregistrer_import()
    else:
        st.session_state.fichiers_importes = \
            st.session_state.get("fichiers_importes", 0) + 1


# ---------------------------------------------------------------------------
# Langue
# ---------------------------------------------------------------------------

def langue() -> str:
    """La langue choisie, ou celle du navigateur au premier passage."""
    if "langue" not in st.session_state:
        entete = None
        try:
            entete = st.context.headers.get("Accept-Language")
        except Exception:
            pass
        st.session_state.langue = lg.detecter(entete)
    return st.session_state.langue


def t(cle: str, **variables) -> str:
    """
    Raccourci de traduction, volontairement court.

    Il apparaîtra des centaines de fois dans les écrans : un nom long
    rendrait le code illisible.
    """
    return lg.traduire(cle, langue(), **variables)


def tp(cle_singulier: str, cle_pluriel: str, nombre: int, **variables) -> str:
    """Traduction avec accord en nombre."""
    return lg.pluriel(cle_singulier, cle_pluriel, nombre, langue(), **variables)


def _langue_choisie() -> None:
    """
    Appelée par Streamlit au moment où l'utilisateur change le menu,
    avant le réaffichage. C'est ce qui permet de distinguer un changement
    venu de lui d'un changement venu du code.
    """
    st.session_state.langue = st.session_state._widget_langue
    try:
        enregistrer()
    except Exception:
        # Changer de langue ne doit jamais faire tomber l'application.
        # Si l'enregistrement échoue, la langue change quand même et
        # la prochaine modification des données le rattrapera.
        st.session_state.modifications_en_attente = True


def selecteur_langue() -> None:
    """
    Le choix de langue, en haut du panneau de gauche.

    Deux clés, et deux sens de circulation à ne pas confondre :

      · l'UTILISATEUR change le menu → `_langue_choisie` recopie son choix
        dans `langue`, au moment même du clic ;
      · le CODE change `langue` — chargement d'un compte, import d'un
        fichier — → on réaligne le menu avant de le réafficher.

    Deux tentatives ont échoué avant celle-ci, et chacune cassait un sens :
    un menu avec sa propre clé écrasait la langue chargée d'un compte ;
    un menu lié directement à `langue` rendait cette clé inmodifiable par
    le code, et recharger un compte levait une erreur.
    """
    langue()                                # pose la langue si elle manque

    # Réalignement : uniquement quand le code a modifié la langue ailleurs.
    # Le choix de l'utilisateur, lui, est déjà passé par `_langue_choisie`,
    # donc les deux valeurs sont alors identiques et rien ne bouge.
    if st.session_state.get("_widget_langue") != st.session_state.langue:
        st.session_state._widget_langue = st.session_state.langue

    st.selectbox(
        lg.traduire("gen.langue", st.session_state.langue),
        lg.LANGUES_DISPONIBLES,
        format_func=lambda c: f"{lg.LOCALES[c].drapeau}  {lg.LOCALES[c].nom_natif}",
        label_visibility="collapsed",
        key="_widget_langue",
        on_change=_langue_choisie)
