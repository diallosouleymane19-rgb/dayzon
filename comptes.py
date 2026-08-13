"""
COMPTES — plusieurs comptes, plusieurs devises
PrevuFlow — SMD Global Consulting LLC

Corrige un défaut de conception : l'application ne connaissait qu'un solde
de départ unique. Un entrepreneur qui travaille entre la France, la Chine et
le Sénégal a un compte par devise, et sa vraie question est double :

  · combien ai-je sur CE compte, dans SA devise ?
  · combien cela fait-il au total, dans MA devise de référence ?

Le total consolidé n'est jamais affiché seul : il vient toujours avec les
taux qui ont servi à le calculer.

Module pur : aucune dépendance à Streamlit, pandas, fichier ou réseau.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import uuid4

from argent import (Conversion, ErreurArgent, Montant, TableTaux, Taux,
                    nom_devise, symbole, valider_devise)


class ErreurCompte(ValueError):
    """Le message est destiné à l'utilisateur."""


def _identifiant() -> str:
    return uuid4().hex[:8]


def _sans_accent(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


# ---------------------------------------------------------------------------
# Un compte
# ---------------------------------------------------------------------------

@dataclass
class Compte:
    """
    Un compte bancaire, une caisse, un portefeuille mobile.

    La devise est celle de tenue du compte : elle ne change jamais après
    création. Changer la devise d'un compte qui contient déjà des mouvements
    reviendrait à réécrire son histoire.
    """
    nom: str
    devise: str
    solde: Decimal = Decimal("0")
    pays: str = ""
    etablissement: str = ""
    identifiant: str = field(default_factory=_identifiant)
    actif: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        self.nom = str(self.nom).strip()
        if not self.nom:
            raise ErreurCompte("Un compte doit avoir un nom.")
        self.devise = valider_devise(self.devise)
        if not isinstance(self.solde, Decimal):
            self.solde = Decimal(str(self.solde))

    @property
    def montant(self) -> Montant:
        return Montant(self.solde, self.devise)

    @property
    def libelle(self) -> str:
        """« Compte courant · Crédit Agricole · EUR »"""
        morceaux = [self.nom]
        if self.etablissement:
            morceaux.append(self.etablissement)
        morceaux.append(self.devise)
        return " · ".join(morceaux)

    def crediter(self, montant: Montant) -> "Compte":
        if montant.devise != self.devise:
            raise ErreurCompte(
                f"Ce compte est tenu en {self.devise} ; le montant est en "
                f"{montant.devise}. Convertissez-le d'abord.")
        self.solde += montant.valeur
        return self


# ---------------------------------------------------------------------------
# Le portefeuille
# ---------------------------------------------------------------------------

@dataclass
class Consolidation:
    """
    Un total, et de quoi le justifier.

    Sans la liste des taux et la ventilation par devise, un total consolidé
    est un chiffre que l'utilisateur doit croire sur parole.
    """
    total: Montant
    par_devise: dict[str, Montant]
    taux_employes: list[Taux]
    comptes_retenus: int

    @property
    def multidevise(self) -> bool:
        return len(self.par_devise) > 1

    @property
    def taux_le_plus_ancien(self) -> Taux | None:
        return min(self.taux_employes, key=lambda t: t.observe_le, default=None)

    def anciennete_max(self, au: date | None = None) -> int:
        t = self.taux_le_plus_ancien
        return t.anciennete(au) if t else 0

    def phrase_taux(self) -> str:
        if not self.taux_employes:
            return "Aucune conversion : tous vos comptes sont dans la même devise."
        return " · ".join(t.phrase() for t in self.taux_employes)


class Portefeuille:
    """L'ensemble des comptes d'un utilisateur, et leur consolidation."""

    def __init__(self, comptes: list[Compte] | None = None,
                 devise_reference: str = "EUR") -> None:
        self.devise_reference = valider_devise(devise_reference)
        self._comptes: list[Compte] = []
        for c in comptes or []:
            self.ajouter(c)

    # ---- Gestion -------------------------------------------------------

    def ajouter(self, compte: Compte) -> Compte:
        if any(c.identifiant == compte.identifiant for c in self._comptes):
            raise ErreurCompte("Ce compte figure déjà dans la liste.")
        doublon = any(_sans_accent(c.nom) == _sans_accent(compte.nom)
                      and c.devise == compte.devise for c in self._comptes)
        if doublon:
            raise ErreurCompte(
                f"Un compte « {compte.nom} » en {compte.devise} existe déjà. "
                f"Choisissez un autre nom pour les distinguer.")
        self._comptes.append(compte)
        return compte

    def retirer(self, identifiant: str) -> bool:
        avant = len(self._comptes)
        self._comptes = [c for c in self._comptes if c.identifiant != identifiant]
        return len(self._comptes) < avant

    def trouver(self, identifiant: str) -> Compte | None:
        return next((c for c in self._comptes if c.identifiant == identifiant), None)

    def definir_reference(self, devise: str) -> "Portefeuille":
        self.devise_reference = valider_devise(devise)
        return self

    # ---- Lecture -------------------------------------------------------

    @property
    def comptes(self) -> list[Compte]:
        return list(self._comptes)

    @property
    def actifs(self) -> list[Compte]:
        return [c for c in self._comptes if c.actif]

    @property
    def vide(self) -> bool:
        return not self._comptes

    @property
    def devises(self) -> list[str]:
        return sorted({c.devise for c in self.actifs})

    def par_devise(self) -> dict[str, list[Compte]]:
        groupes: dict[str, list[Compte]] = {}
        for c in self.actifs:
            groupes.setdefault(c.devise, []).append(c)
        return dict(sorted(groupes.items()))

    def solde_devise(self, devise: str) -> Montant:
        """Total des comptes tenus dans cette devise, sans aucune conversion."""
        devise = valider_devise(devise)
        total = Montant.zero(devise)
        for c in self.actifs:
            if c.devise == devise:
                total = total + c.montant
        return total

    # ---- Consolidation -------------------------------------------------

    def consolider(self, taux: TableTaux,
                   vers: str | None = None) -> Consolidation:
        """
        Additionne tous les comptes actifs dans une devise unique.

        Lève une erreur explicite si un taux manque : afficher un total
        amputé d'un compte serait pire que de ne rien afficher.
        """
        vers = valider_devise(vers or self.devise_reference)

        par_devise: dict[str, Montant] = {}
        for devise, comptes in self.par_devise().items():
            sous_total = Montant.zero(devise)
            for c in comptes:
                sous_total = sous_total + c.montant
            par_devise[devise] = sous_total

        total = Montant.zero(vers)
        employes: dict[tuple[str, str], Taux] = {}
        manquantes: list[str] = []

        for devise, sous_total in par_devise.items():
            try:
                conversion = taux.convertir(sous_total, vers)
            except ErreurArgent:
                manquantes.append(devise)
                continue
            total = total + conversion.resultat
            if conversion.taux is not None:
                employes[(conversion.taux.base, conversion.taux.contre)] = conversion.taux

        if manquantes:
            raise ErreurCompte(
                f"Impossible de calculer un total en {vers} : aucun taux connu "
                f"pour {', '.join(sorted(manquantes))}. "
                f"Renseignez ces taux, ou choisissez une devise de référence "
                f"parmi celles de vos comptes.")

        return Consolidation(total=total, par_devise=par_devise,
                             taux_employes=list(employes.values()),
                             comptes_retenus=len(self.actifs))

    def peut_consolider(self, taux: TableTaux, vers: str | None = None) -> bool:
        try:
            self.consolider(taux, vers)
            return True
        except ErreurCompte:
            return False

    # ---- Sérialisation -------------------------------------------------

    def vers_liste(self) -> list[dict]:
        return [{"nom": c.nom, "devise": c.devise, "solde": str(c.solde),
                 "pays": c.pays, "etablissement": c.etablissement,
                 "identifiant": c.identifiant, "actif": c.actif, "note": c.note}
                for c in self._comptes]

    @classmethod
    def depuis_liste(cls, donnees: list[dict],
                     devise_reference: str = "EUR") -> "Portefeuille":
        p = cls(devise_reference=devise_reference)
        for d in donnees or []:
            p._comptes.append(Compte(
                nom=d.get("nom", "Compte"),
                devise=d.get("devise", devise_reference),
                solde=Decimal(str(d.get("solde", "0"))),
                pays=d.get("pays", ""),
                etablissement=d.get("etablissement", ""),
                identifiant=d.get("identifiant") or _identifiant(),
                actif=bool(d.get("actif", True)),
                note=d.get("note", "")))
        return p


# ---------------------------------------------------------------------------
# Reprise de l'ancien réglage
# ---------------------------------------------------------------------------

def portefeuille_depuis_solde_unique(solde, devise: str = "EUR",
                                     nom: str = "Compte principal") -> Portefeuille:
    """
    Convertit l'ancien réglage — un solde, une devise — en portefeuille.

    Personne ne doit perdre son paramétrage parce que l'application a évolué.
    """
    return Portefeuille([Compte(nom=nom, devise=devise,
                                solde=Decimal(str(solde)))],
                        devise_reference=devise)
