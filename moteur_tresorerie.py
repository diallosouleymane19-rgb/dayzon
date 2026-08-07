"""
MOTEUR DE TRESORERIE PREVISIONNELLE
SMD Global Consulting LLC — Dayzon

Calcule le solde projete jour par jour a partir d'operations datees.
Independant de tout referentiel comptable national : fonctionne pour un
particulier comme pour une entreprise, dans n'importe quelle devise.

Aucune dependance externe : Python 3.10+ uniquement.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Iterator


# ---------------------------------------------------------------------------
# Recurrences
# ---------------------------------------------------------------------------

class Recurrence(str, Enum):
    """Frequence de repetition d'une operation."""
    PONCTUELLE     = "ponctuelle"
    QUOTIDIENNE    = "quotidienne"
    HEBDOMADAIRE   = "hebdomadaire"
    BIMENSUELLE    = "bimensuelle"      # tous les 14 jours
    MENSUELLE      = "mensuelle"
    TRIMESTRIELLE  = "trimestrielle"
    ANNUELLE       = "annuelle"


def _ajouter_mois(d: date, mois: int) -> date:
    """Ajoute des mois en gerant les fins de mois (31 janvier + 1 mois = 28/29 fevrier)."""
    total = d.month - 1 + mois
    annee = d.year + total // 12
    m = total % 12 + 1
    # Dernier jour du mois cible
    if m == 12:
        dernier = 31
    else:
        dernier = (date(annee, m + 1, 1) - timedelta(days=1)).day
    return date(annee, m, min(d.day, dernier))


# ---------------------------------------------------------------------------
# Operation
# ---------------------------------------------------------------------------

@dataclass
class Operation:
    """
    Une entree ou une sortie d'argent, datee.

    montant : positif = encaissement, negatif = decaissement.
    date_fin : derniere date possible pour une operation recurrente (None = illimite).
    """
    libelle: str
    montant: Decimal
    date_operation: date
    devise: str = "EUR"
    recurrence: Recurrence = Recurrence.PONCTUELLE
    date_fin: date | None = None
    categorie: str = ""
    certaine: bool = True        # False = prevision incertaine (devis, prospect)

    def __post_init__(self):
        if not isinstance(self.montant, Decimal):
            self.montant = Decimal(str(self.montant))
        self.devise = self.devise.upper()

    def occurrences(self, debut: date, fin: date) -> Iterator[date]:
        """Genere toutes les dates d'occurrence comprises entre debut et fin."""
        limite = min(fin, self.date_fin) if self.date_fin else fin
        d = self.date_operation

        if self.recurrence == Recurrence.PONCTUELLE:
            if debut <= d <= limite:
                yield d
            return

        pas_jours = {
            Recurrence.QUOTIDIENNE: 1,
            Recurrence.HEBDOMADAIRE: 7,
            Recurrence.BIMENSUELLE: 14,
        }.get(self.recurrence)

        pas_mois = {
            Recurrence.MENSUELLE: 1,
            Recurrence.TRIMESTRIELLE: 3,
            Recurrence.ANNUELLE: 12,
        }.get(self.recurrence)

        garde_fou = 0
        while d <= limite and garde_fou < 10_000:
            garde_fou += 1
            if d >= debut:
                yield d
            if pas_jours:
                d = d + timedelta(days=pas_jours)
            else:
                d = _ajouter_mois(self.date_operation, pas_mois * garde_fou)


# ---------------------------------------------------------------------------
# Conversion de devises
# ---------------------------------------------------------------------------

@dataclass
class TauxChange:
    """
    Table de conversion vers une devise de reference.
    Exemple : TauxChange("EUR", {"USD": 0.92, "XOF": 0.001524})
    """
    devise_reference: str = "EUR"
    taux: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self):
        self.devise_reference = self.devise_reference.upper()
        self.taux = {k.upper(): Decimal(str(v)) for k, v in self.taux.items()}
        self.taux[self.devise_reference] = Decimal("1")

    def convertir(self, montant: Decimal, devise: str) -> Decimal:
        devise = devise.upper()
        if devise not in self.taux:
            raise ValueError(
                f"Taux manquant pour {devise}. "
                f"Devises connues : {', '.join(sorted(self.taux))}"
            )
        return montant * self.taux[devise]


# ---------------------------------------------------------------------------
# Resultat d'une journee
# ---------------------------------------------------------------------------

@dataclass
class Journee:
    jour: date
    entrees: Decimal
    sorties: Decimal
    solde: Decimal
    operations: list[str] = field(default_factory=list)

    @property
    def variation(self) -> Decimal:
        return self.entrees + self.sorties      # sorties sont negatives


# ---------------------------------------------------------------------------
# Moteur
# ---------------------------------------------------------------------------

class Tresorerie:
    """
    Projette un solde jour par jour.

    >>> t = Tresorerie(solde_initial=1000, devise="EUR")
    >>> t.ajouter(Operation("Salaire", 2500, date(2026, 8, 28), recurrence=Recurrence.MENSUELLE))
    >>> t.ajouter(Operation("Loyer", -900, date(2026, 8, 5), recurrence=Recurrence.MENSUELLE))
    >>> jours = t.projeter(date(2026, 8, 1), 60)
    """

    def __init__(self, solde_initial: Decimal | float | int = 0,
                 devise: str = "EUR",
                 taux: TauxChange | None = None):
        self.solde_initial = Decimal(str(solde_initial))
        self.devise = devise.upper()
        self.taux = taux or TauxChange(self.devise)
        self.operations: list[Operation] = []

    def ajouter(self, operation: Operation) -> "Tresorerie":
        self.operations.append(operation)
        return self

    def ajouter_plusieurs(self, operations: list[Operation]) -> "Tresorerie":
        self.operations.extend(operations)
        return self

    # -- Projection ---------------------------------------------------------

    def projeter(self, debut: date, nb_jours: int = 90,
                 inclure_incertain: bool = True) -> list[Journee]:
        """Renvoie une Journee par jour, du premier au dernier."""
        if nb_jours < 1:
            raise ValueError("nb_jours doit valoir au moins 1")
        fin = debut + timedelta(days=nb_jours - 1)

        # Regroupement des mouvements par date
        mouvements: dict[date, list[tuple[str, Decimal]]] = {}
        for op in self.operations:
            if not inclure_incertain and not op.certaine:
                continue
            montant = self.taux.convertir(op.montant, op.devise)
            for jour in op.occurrences(debut, fin):
                mouvements.setdefault(jour, []).append((op.libelle, montant))

        resultat: list[Journee] = []
        solde = self.solde_initial
        for i in range(nb_jours):
            jour = debut + timedelta(days=i)
            lignes = mouvements.get(jour, [])
            entrees = sum((m for _, m in lignes if m > 0), Decimal("0"))
            sorties = sum((m for _, m in lignes if m < 0), Decimal("0"))
            solde += entrees + sorties
            resultat.append(Journee(
                jour=jour,
                entrees=_arrondi(entrees),
                sorties=_arrondi(sorties),
                solde=_arrondi(solde),
                operations=[lib for lib, _ in lignes],
            ))
        return resultat

    # -- Analyses -----------------------------------------------------------

    def premier_jour_negatif(self, debut: date, nb_jours: int = 90) -> Journee | None:
        """Le jour ou le solde devient negatif — l'alerte la plus utile."""
        for j in self.projeter(debut, nb_jours):
            if j.solde < 0:
                return j
        return None

    def solde_minimum(self, debut: date, nb_jours: int = 90) -> Journee:
        """Le point bas de la periode : c'est lui qui dimensionne le besoin de tresorerie."""
        return min(self.projeter(debut, nb_jours), key=lambda j: j.solde)

    def synthese(self, debut: date, nb_jours: int = 90) -> dict:
        """Resume chiffre, pret a afficher dans un tableau de bord."""
        jours = self.projeter(debut, nb_jours)
        entrees = sum((j.entrees for j in jours), Decimal("0"))
        sorties = sum((j.sorties for j in jours), Decimal("0"))
        point_bas = min(jours, key=lambda j: j.solde)
        negatif = next((j for j in jours if j.solde < 0), None)
        return {
            "devise":            self.devise,
            "periode_debut":     jours[0].jour,
            "periode_fin":       jours[-1].jour,
            "solde_initial":     _arrondi(self.solde_initial),
            "solde_final":       jours[-1].solde,
            "total_entrees":     _arrondi(entrees),
            "total_sorties":     _arrondi(sorties),
            "variation_nette":   _arrondi(entrees + sorties),
            "solde_minimum":     point_bas.solde,
            "date_solde_min":    point_bas.jour,
            "premier_jour_negatif": negatif.jour if negatif else None,
            "jours_avant_negatif":  (negatif.jour - debut).days if negatif else None,
            "alerte":            negatif is not None,
        }


def _arrondi(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
