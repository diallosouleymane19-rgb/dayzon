"""
SCÉNARIOS — « et si ? »
Dayzon — SMD Global Consulting LLC

Un scénario prend vos opérations, applique une hypothèse, et reprojette.
Le moteur de trésorerie ne change pas : on ne modifie que ce qu'on lui donne.

Le vrai apport n'est pas le calcul — c'est la liste d'hypothèses toutes prêtes.
Un dirigeant sait qu'il doit se préparer ; il ne sait pas toujours à quoi.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from moteur_tresorerie import Recurrence, Tresorerie


def _sans_accent(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


# ===========================================================================
# LES HYPOTHÈSES
# ===========================================================================

GENRES = {
    "varier":    "Faire varier des montants",
    "supprimer": "Supprimer une rentrée ou une charge",
    "decaler":   "Décaler des encaissements",
    "ajouter":   "Ajouter une opération",
    "solde":     "Partir d'une trésorerie différente",
}

PORTEES = {
    "entrees": "les entrées d'argent",
    "sorties": "les sorties d'argent",
    "tout":    "toutes les opérations",
}


@dataclass
class Hypothese:
    """
    Une modification, et une seule. Un scénario en empile autant qu'il veut ;
    on les garde séparées pour que l'utilisateur voie ce qu'il a supposé.
    """
    genre: str
    valeur: float = 0.0
    cible: str = ""                 # libellé visé ; vide = tout ce qui entre dans la portée
    portee: str = "tout"
    libelle_ajout: str = ""
    date_ajout: date | None = None
    recurrence_ajout: Recurrence = Recurrence.MENSUELLE

    # ---- Sélection -----------------------------------------------------

    def _concerne(self, operation: dict) -> bool:
        montant = float(operation["montant"])
        if self.portee == "entrees" and montant <= 0:
            return False
        if self.portee == "sorties" and montant >= 0:
            return False
        if self.cible:
            return _sans_accent(self.cible) in _sans_accent(operation["libelle"])
        return True

    # ---- Mise en mots --------------------------------------------------

    def phrase(self) -> str:
        # Une cible est un nom propre : « Alpha SA » ne doit jamais devenir
        # « alpha sa ». On ne met la majuscule que sur les portées génériques.
        if self.cible:
            sur = f"« {self.cible} »"
        else:
            libelle = PORTEES.get(self.portee, "")
            sur = libelle[:1].upper() + libelle[1:]

        if self.genre == "varier":
            sens = "augmentent" if self.valeur > 0 else "baissent"
            return f"{sur} {sens} de {abs(self.valeur):.0f} %"
        if self.genre == "supprimer":
            return f"{sur} {'disparaît' if self.cible else 'disparaissent'}"
        if self.genre == "decaler":
            return (f"{sur} {'est encaissée' if self.cible else 'sont encaissées'} "
                    f"{abs(self.valeur):.0f} jours plus tard")
        if self.genre == "ajouter":
            sens = "Une rentrée" if self.valeur > 0 else "Une charge"
            return (f"{sens} de {abs(self.valeur):,.0f} — « {self.libelle_ajout} » — "
                    f"s'ajoute").replace(",", " ")
        if self.genre == "solde":
            return f"La trésorerie de départ est de {self.valeur:,.0f}".replace(",", " ")
        return self.genre

    # ---- Application ---------------------------------------------------

    def appliquer(self, operations: list[dict], solde: float) -> tuple[list[dict], float]:
        if self.genre == "solde":
            return operations, float(self.valeur)

        if self.genre == "ajouter":
            operations = operations + [{
                "libelle": self.libelle_ajout or "Nouvelle opération",
                "montant": float(self.valeur),
                "date": self.date_ajout or (date.today() + timedelta(days=1)),
                "devise": operations[0].get("devise", "EUR") if operations else "EUR",
                "recurrence": self.recurrence_ajout,
                "date_fin": None,
                "certaine": True,
            }]
            return operations, solde

        if self.genre == "supprimer":
            return [o for o in operations if not self._concerne(o)], solde

        resultat = []
        for o in operations:
            if not self._concerne(o):
                resultat.append(o)
                continue
            o = dict(o)
            if self.genre == "varier":
                o["montant"] = float(o["montant"]) * (1 + self.valeur / 100)
            elif self.genre == "decaler":
                o["date"] = o["date"] + timedelta(days=int(self.valeur))
                if o.get("date_fin"):
                    o["date_fin"] = o["date_fin"] + timedelta(days=int(self.valeur))
            resultat.append(o)
        return resultat, solde


# ===========================================================================
# LES SCÉNARIOS
# ===========================================================================

@dataclass
class Scenario:
    nom: str
    hypotheses: list[Hypothese] = field(default_factory=list)
    explication: str = ""

    def appliquer(self, operations: list[dict],
                  solde: float) -> tuple[list[dict], float]:
        ops, s = copy.deepcopy(operations), solde
        for h in self.hypotheses:
            ops, s = h.appliquer(ops, s)
        return ops, s

    def resume(self) -> str:
        return " · ".join(h.phrase() for h in self.hypotheses) or "aucune hypothèse"


@dataclass
class Resultat:
    """Ce qu'un scénario produit, et ce qu'il coûte par rapport au cas de base."""
    nom: str
    solde_final: Decimal
    solde_minimum: Decimal
    date_solde_min: date
    premier_jour_negatif: date | None
    jours_avant_negatif: int | None
    courbe: list[tuple[date, float]]
    resume: str = ""
    devise: str = "EUR"

    ecart_final: Decimal = Decimal("0")
    ecart_minimum: Decimal = Decimal("0")

    @property
    def tient(self) -> bool:
        return self.premier_jour_negatif is None

    def verdict(self) -> tuple[str, str]:
        """Une phrase qui dit s'il faut s'inquiéter, et pourquoi."""
        if self.tient:
            return ("bon", f"Vous tenez. Point bas : "
                           f"{self._n(self.solde_minimum)} le "
                           f"{self.date_solde_min.strftime('%d/%m/%Y')}.")
        if self.jours_avant_negatif is not None and self.jours_avant_negatif <= 30:
            return ("alerte", f"Vous êtes à découvert dès le "
                              f"{self.premier_jour_negatif.strftime('%d/%m/%Y')}, "
                              f"soit dans {self.jours_avant_negatif} jours.")
        return ("attention", f"Vous passez sous zéro le "
                             f"{self.premier_jour_negatif.strftime('%d/%m/%Y')}, "
                             f"dans {self.jours_avant_negatif} jours.")

    def _n(self, v) -> str:
        """Un verdict se lit seul, hors contexte : il doit porter sa devise."""
        symboles = {"EUR": "€", "USD": "$", "GBP": "£", "CAD": "C$",
                    "CHF": "CHF", "XOF": "FCFA", "XAF": "FCFA", "MAD": "DH",
                    "TRY": "₺", "NGN": "₦", "AED": "AED", "CNY": "¥"}
        montant = f"{float(v):,.0f}".replace(",", " ")
        return f"{montant} {symboles.get(self.devise, self.devise)}"


def projeter_scenario(scenario: Scenario, operations: list[dict], solde: float,
                      devise: str, taux: dict, debut: date,
                      nb_jours: int = 180) -> Resultat:
    """Applique le scénario, reprojette, et renvoie de quoi comparer."""
    from moteur_tresorerie import Operation, TauxChange

    ops, s = scenario.appliquer(operations, solde)

    t = Tresorerie(solde_initial=Decimal(str(s)), devise=devise,
                   taux=TauxChange(devise, taux))
    for o in ops:
        t.ajouter(Operation(
            libelle=o["libelle"],
            montant=Decimal(str(o["montant"])),
            date_operation=o["date"],
            devise=o.get("devise", devise),
            recurrence=o.get("recurrence", Recurrence.PONCTUELLE),
            date_fin=o.get("date_fin"),
            categorie=o.get("categorie", ""),
            certaine=o.get("certaine", True),
        ))

    jours = t.projeter(debut, nb_jours)
    synthese = t.synthese(debut, nb_jours)

    return Resultat(
        nom=scenario.nom,
        solde_final=synthese["solde_final"],
        solde_minimum=synthese["solde_minimum"],
        date_solde_min=synthese["date_solde_min"],
        premier_jour_negatif=synthese["premier_jour_negatif"],
        jours_avant_negatif=synthese["jours_avant_negatif"],
        courbe=[(j.jour, float(j.solde)) for j in jours],
        resume=scenario.resume(),
        devise=devise,
    )


def comparer(scenarios: list[Scenario], operations: list[dict], solde: float,
             devise: str, taux: dict, debut: date,
             nb_jours: int = 180) -> list[Resultat]:
    """
    Projette tous les scénarios, le cas de base en tête.

    Les écarts sont mesurés par rapport au cas de base : c'est ce chiffre
    qui répond vraiment à la question « combien ça me coûte ? ».
    """
    base = Scenario("Situation actuelle", [], "Vos opérations, sans modification")
    resultats = [projeter_scenario(base, operations, solde, devise, taux,
                                   debut, nb_jours)]
    for s in scenarios:
        resultats.append(projeter_scenario(s, operations, solde, devise, taux,
                                           debut, nb_jours))

    reference = resultats[0]
    for r in resultats[1:]:
        r.ecart_final = r.solde_final - reference.solde_final
        r.ecart_minimum = r.solde_minimum - reference.solde_minimum
    return resultats


# ===========================================================================
# LES MODÈLES — le cœur de l'apport
# ===========================================================================

def modeles(profil: str = "Particulier",
            operations: list[dict] | None = None) -> dict[str, Scenario]:
    """
    Des scénarios prêts à l'emploi, adaptés au profil.

    Quand c'est possible, le modèle vise l'opération réellement concernée :
    « je perds mon plus gros client » cible le plus gros encaissement
    effectivement présent dans les données, pas un client théorique.
    """
    operations = operations or []
    entrees = sorted((o for o in operations if float(o["montant"]) > 0),
                     key=lambda o: -float(o["montant"]))
    plus_grosse_entree = entrees[0]["libelle"] if entrees else ""

    if profil == "Entreprise":
        catalogue = {
            "Je perds mon plus gros client": Scenario(
                "Je perds mon plus gros client",
                [Hypothese("supprimer", cible=plus_grosse_entree, portee="entrees")]
                if plus_grosse_entree else
                [Hypothese("varier", -35, portee="entrees")],
                "La question à se poser avant que le client ne la pose."),

            "Mes clients paient 30 jours plus tard": Scenario(
                "Mes clients paient 30 jours plus tard",
                [Hypothese("decaler", 30, portee="entrees")],
                "Le retard de paiement ne change pas votre résultat, "
                "seulement votre capacité à payer vos propres échéances."),

            "Mon activité recule de 20 %": Scenario(
                "Mon activité recule de 20 %",
                [Hypothese("varier", -20, portee="entrees")],
                "Une baisse de commandes, un marché perdu, une saison creuse."),

            "Mes charges augmentent de 10 %": Scenario(
                "Mes charges augmentent de 10 %",
                [Hypothese("varier", 10, portee="sorties")],
                "Énergie, loyers, matières premières, salaires."),

            "J'embauche": Scenario(
                "J'embauche",
                [Hypothese("ajouter", -3000, libelle_ajout="Nouveau salaire",
                           recurrence_ajout=Recurrence.MENSUELLE)],
                "Ajustez le montant à votre marché. Le poste est prélevé "
                "chaque mois, indéfiniment."),

            "Le pire des cas": Scenario(
                "Le pire des cas",
                [Hypothese("varier", -25, portee="entrees"),
                 Hypothese("decaler", 30, portee="entrees"),
                 Hypothese("varier", 10, portee="sorties")],
                "Trois coups en même temps. Si vous tenez ici, "
                "vous tenez partout."),
        }
    else:
        catalogue = {
            "Je perds mon revenu principal": Scenario(
                "Je perds mon revenu principal",
                [Hypothese("supprimer", cible=plus_grosse_entree, portee="entrees")]
                if plus_grosse_entree else
                [Hypothese("varier", -100, portee="entrees")],
                "Combien de temps tenez-vous sans rentrée principale ?"),

            "Mes revenus baissent de 20 %": Scenario(
                "Mes revenus baissent de 20 %",
                [Hypothese("varier", -20, portee="entrees")],
                "Chômage partiel, fin de prime, baisse d'activité."),

            "Le coût de la vie augmente de 10 %": Scenario(
                "Le coût de la vie augmente de 10 %",
                [Hypothese("varier", 10, portee="sorties")],
                "Énergie, alimentation, loyer, assurances."),

            "Une dépense imprévue de 2 000": Scenario(
                "Une dépense imprévue de 2 000",
                [Hypothese("ajouter", -2000, libelle_ajout="Imprévu",
                           recurrence_ajout=Recurrence.PONCTUELLE)],
                "Voiture, santé, réparation. Ajustez le montant."),

            "Je réduis mes dépenses variables de 15 %": Scenario(
                "Je réduis mes dépenses variables de 15 %",
                [Hypothese("varier", -15, portee="sorties")],
                "L'effort d'économie que vous envisagez, chiffré."),

            "Le pire des cas": Scenario(
                "Le pire des cas",
                [Hypothese("varier", -25, portee="entrees"),
                 Hypothese("varier", 10, portee="sorties")],
                "Moins de revenus et plus de charges, en même temps."),
        }

    return catalogue
