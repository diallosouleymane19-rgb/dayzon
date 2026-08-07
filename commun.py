"""
ELEMENTS PARTAGES ENTRE LES DEUX PROFILS
Dayzon — SMD Global Consulting LLC

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
    Écrit la sauvegarde. Renvoie True si l'écriture a eu lieu.

    Silencieuse en cas d'échec quand elle est automatique : afficher une
    erreur technique à chaque frappe rendrait l'application inutilisable.
    L'échec reste visible dans l'écran des réglages.
    """
    if not sv.mode_local():
        # Rien à faire : en ligne, les données ne quittent pas la session.
        # L'utilisateur les emporte par « Télécharger mes données ».
        return False

    if not force and not st.session_state.get("sauvegarde_auto", True):
        return False

    table = taux()
    donnees = sv.Donnees(
        profil=st.session_state.get("profil", "Particulier"),
        devise_reference=devise_reference(),
        comptes=portefeuille().vers_liste(),
        operations=_operations_serialisables(),
        taux=[{"base": t.base, "contre": t.contre, "valeur": str(t.valeur),
               "observe_le": t.observe_le.isoformat(), "source": t.source}
              for t in _taux_uniques(table)],
    )
    try:
        sv.enregistrer(donnees)
        st.session_state.derniere_sauvegarde = donnees.enregistre_le
        st.session_state.erreur_sauvegarde = None
        return True
    except sv.ErreurSauvegarde as err:
        st.session_state.erreur_sauvegarde = str(err)
        if force:
            raise
        return False


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
    """1 234,56 € — accepte un Montant, un Decimal, un float ou un int."""
    if isinstance(montant, Montant):
        return montant.formater()
    return Montant.de(montant, devise or devise_reference()).formater()


def formater_court(montant, devise: str | None = None) -> str:
    """Sans les centimes, pour les indicateurs où ils n'apportent rien."""
    if isinstance(montant, Montant):
        return montant.formater(avec_decimales=False)
    return Montant.de(montant, devise or devise_reference()).formater(False)


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
