"""
SCÉNARIOS — « et si ? »
PrevuFlow — SMD Global Consulting LLC

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

# Les cles sont stables ; le libelle lu vient toujours de la traduction.
GENRES = ("varier", "supprimer", "decaler", "ajouter", "solde")
PORTEES = ("entrees", "sorties", "tout")


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

    def phrase(self, t=None) -> str:
        """
        Met l'hypothese en mots, dans la langue de lecture.

        Le singulier et le pluriel sont deux cles distinctes : une cible
        precise se dit au singulier (« Alpha SA disparait »), une portee
        generique au pluriel (« les entrees d'argent disparaissent »).
        """
        t = t or _texte

        # Une cible est un nom propre : « Alpha SA » ne doit jamais devenir
        # « alpha sa ». On ne met la majuscule que sur les portées génériques.
        if self.cible:
            sur = f"« {self.cible} »"
        else:
            libelle = t("por." + self.portee)
            sur = libelle[:1].upper() + libelle[1:]

        montant = f"{abs(self.valeur):,.0f}".replace(",", "\u202f")

        if self.genre == "varier":
            cle = "ph.hausse" if self.valeur > 0 else "ph.baisse"
            return t(cle, sur=sur, n=f"{abs(self.valeur):.0f}")
        if self.genre == "supprimer":
            return t("ph.supprimer_un" if self.cible else "ph.supprimer_pl",
                     sur=sur)
        if self.genre == "decaler":
            return t("ph.decaler_un" if self.cible else "ph.decaler_pl",
                     sur=sur, n=f"{abs(self.valeur):.0f}")
        if self.genre == "ajouter":
            cle = "ph.ajout_entree" if self.valeur > 0 else "ph.ajout_sortie"
            return t(cle, montant=montant, libelle=self.libelle_ajout)
        if self.genre == "solde":
            return t("ph.solde", montant=f"{self.valeur:,.0f}".replace(",", "\u202f"))
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

    def resume(self, t=None) -> str:
        t = t or _texte
        return (" · ".join(h.phrase(t) for h in self.hypotheses)
                or t("ph.aucune"))


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

    def verdict(self, t=None, date_lisible=None, montant_lisible=None
                ) -> tuple[str, str]:
        """
        Une phrase qui dit s'il faut s'inquiéter, et pourquoi.

        `date_lisible` ecrit la date selon la langue. Par defaut on garde le
        format francais : ce module ne connait pas la langue de lecture,
        c'est l'interface qui la lui donne.
        """
        t = t or _texte
        ecrire = date_lisible or (lambda j: j.strftime("%d/%m/%Y"))
        somme = montant_lisible or self._n

        if self.tient:
            return ("bon", t("vd.tient", montant=somme(self.solde_minimum),
                             date=ecrire(self.date_solde_min)))
        if self.jours_avant_negatif is not None and self.jours_avant_negatif <= 30:
            return ("alerte", t("vd.alerte",
                                date=ecrire(self.premier_jour_negatif),
                                n=self.jours_avant_negatif))
        return ("attention", t("vd.attention",
                               date=ecrire(self.premier_jour_negatif),
                               n=self.jours_avant_negatif))

    def _n(self, v) -> str:
        """
        Repli quand l'interface ne fournit pas de formateur.

        Un verdict se lit seul, hors contexte : il doit porter sa devise.
        La typographie est francaise — c'est a l'appelant de passer
        `montant_lisible` s'il connait la langue de lecture.
        """
        symboles = {"EUR": "€", "USD": "$", "GBP": "£", "CAD": "C$",
                    "CHF": "CHF", "XOF": "FCFA", "XAF": "FCFA", "MAD": "DH",
                    "TRY": "₺", "NGN": "₦", "AED": "AED", "CNY": "¥"}
        montant = f"{float(v):,.0f}".replace(",", " ")
        return f"{montant} {symboles.get(self.devise, self.devise)}"


def projeter_scenario(scenario: Scenario, operations: list[dict], solde: float,
                      devise: str, taux: dict, debut: date,
                      nb_jours: int = 180, traduire=None) -> Resultat:
    """
    Applique le scénario, reprojette, et renvoie de quoi comparer.

    Le parametre s'appelle `traduire` et non `t` : `t` designe deja la
    tresorerie dans le corps de cette fonction, et la collision avait
    casse la projection.
    """
    from moteur_tresorerie import Operation, TauxChange

    traduire = traduire or _texte

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
        resume=scenario.resume(traduire),
        devise=devise,
    )


def _texte(cle: str, **variables) -> str:
    """
    Repli quand aucune fonction de traduction n'est fournie.

    La signature accepte les memes variables que `commun.t` : un module
    appele hors interface — un test, un export — doit obtenir la meme
    phrase, en francais.
    """
    from langues import traduire
    return traduire(cle, "fr", **variables)


def comparer(scenarios: list[Scenario], operations: list[dict], solde: float,
             devise: str, taux: dict, debut: date,
             nb_jours: int = 180, t=None) -> list[Resultat]:
    """
    Projette tous les scénarios, le cas de base en tête.

    Les écarts sont mesurés par rapport au cas de base : c'est ce chiffre
    qui répond vraiment à la question « combien ça me coûte ? ».
    """
    t = t or _texte
    base = Scenario(t("sc.base_nom"), [], t("sc.base_resume"))
    resultats = [projeter_scenario(base, operations, solde, devise, taux,
                                   debut, nb_jours, t)]
    for s in scenarios:
        resultats.append(projeter_scenario(s, operations, solde, devise, taux,
                                           debut, nb_jours, t))

    reference = resultats[0]
    for r in resultats[1:]:
        r.ecart_final = r.solde_final - reference.solde_final
        r.ecart_minimum = r.solde_minimum - reference.solde_minimum
    return resultats


# ===========================================================================
# LES MODÈLES — le cœur de l'apport
# ===========================================================================

def modeles(profil: str = "Particulier",
            operations: list[dict] | None = None, t=None) -> dict[str, Scenario]:
    """
    Des scénarios prêts à l'emploi, adaptés au profil.

    Quand c'est possible, le modèle vise l'opération réellement concernée :
    « je perds mon plus gros client » cible le plus gros encaissement
    effectivement présent dans les données, pas un client théorique.

    `t` est la fonction de traduction. Elle est passée en argument plutôt
    qu'importée : ce module reste pur, sans dépendance à l'interface, et
    les tests peuvent l'appeler dans n'importe quelle langue.
    """
    t = t or _texte
    operations = operations or []
    entrees = sorted((o for o in operations if float(o["montant"]) > 0),
                     key=lambda o: -float(o["montant"]))
    plus_grosse_entree = entrees[0]["libelle"] if entrees else ""

    def scenario(cle_nom: str, hypotheses, cle_texte: str) -> tuple[str, Scenario]:
        nom = t(cle_nom)
        return nom, Scenario(nom, hypotheses, t(cle_texte))

    if profil == "Entreprise":
        entrees_du_catalogue = [
            scenario("mod.ent.client_nom",
                     [Hypothese("supprimer", cible=plus_grosse_entree,
                                portee="entrees")]
                     if plus_grosse_entree else
                     [Hypothese("varier", -35, portee="entrees")],
                     "mod.ent.client_txt"),
            scenario("mod.ent.retard_nom",
                     [Hypothese("decaler", 30, portee="entrees")],
                     "mod.ent.retard_txt"),
            scenario("mod.ent.recul_nom",
                     [Hypothese("varier", -20, portee="entrees")],
                     "mod.ent.recul_txt"),
            scenario("mod.ent.charges_nom",
                     [Hypothese("varier", 10, portee="sorties")],
                     "mod.ent.charges_txt"),
            scenario("mod.ent.embauche_nom",
                     [Hypothese("ajouter", -3000,
                                libelle_ajout=t("mod.ent.salaire"),
                                recurrence_ajout=Recurrence.MENSUELLE)],
                     "mod.ent.embauche_txt"),
            scenario("mod.pire_nom",
                     [Hypothese("varier", -25, portee="entrees"),
                      Hypothese("decaler", 30, portee="entrees"),
                      Hypothese("varier", 10, portee="sorties")],
                     "mod.ent.pire_txt"),
        ]
    else:
        entrees_du_catalogue = [
            scenario("mod.part.revenu_nom",
                     [Hypothese("supprimer", cible=plus_grosse_entree,
                                portee="entrees")]
                     if plus_grosse_entree else
                     [Hypothese("varier", -100, portee="entrees")],
                     "mod.part.revenu_txt"),
            scenario("mod.part.baisse_nom",
                     [Hypothese("varier", -20, portee="entrees")],
                     "mod.part.baisse_txt"),
            scenario("mod.part.vie_nom",
                     [Hypothese("varier", 10, portee="sorties")],
                     "mod.part.vie_txt"),
            scenario("mod.part.imprevu_nom",
                     [Hypothese("ajouter", -2000,
                                libelle_ajout=t("mod.part.imprevu"),
                                recurrence_ajout=Recurrence.PONCTUELLE)],
                     "mod.part.imprevu_txt"),
            scenario("mod.part.economie_nom",
                     [Hypothese("varier", -15, portee="sorties")],
                     "mod.part.economie_txt"),
            scenario("mod.pire_nom",
                     [Hypothese("varier", -25, portee="entrees"),
                      Hypothese("varier", 10, portee="sorties")],
                     "mod.part.pire_txt"),
        ]

    return dict(entrees_du_catalogue)
