"""
ABONNEMENTS
Dayzon — SMD Global Consulting LLC

Trois responsabilités, et rien d'autre :
  1. dire ce que chaque plan débloque ;
  2. ouvrir une page de paiement Stripe ;
  3. répondre à la question « cet utilisateur a-t-il le droit ? ».

Ce module ne connaît pas l'interface et n'affiche rien. Il est testable seul,
sans Streamlit et sans réseau.

CONFIGURATION
-------------
Les clés se placent dans `.streamlit/secrets.toml`, jamais dans le code :

    [stripe]
    cle_secrete   = "sk_test_..."
    prix_particulier_mensuel = "price_..."
    prix_particulier_annuel  = "price_..."
    prix_entreprise_mensuel  = "price_..."
    prix_entreprise_annuel   = "price_..."

Tant que rien n'est configuré, l'application fonctionne en mode libre :
toutes les fonctions sont ouvertes. C'est voulu — le produit doit rester
utilisable en local pendant le développement et les démonstrations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum


class Plan(str, Enum):
    LIBRE = "libre"                 # aucun paiement configuré, ou démonstration
    DECOUVERTE = "decouverte"       # gratuit, limité
    PARTICULIER = "particulier"
    ENTREPRISE = "entreprise"


class Periode(str, Enum):
    MENSUELLE = "mensuelle"
    ANNUELLE = "annuelle"


# ---------------------------------------------------------------------------
# Ce que chaque plan permet
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Offre:
    """
    Un plan et ses limites.

    Les limites sont volontairement peu nombreuses. Une grille compliquée se
    retourne contre celui qui la vend : l'acheteur hésite, puis renonce.
    """
    plan: Plan
    nom: str
    resume: str
    prix_mensuel: int = 0           # en cents, monnaie de facturation
    prix_annuel: int = 0
    devise: str = "usd"

    jours_projection: int = 90      # horizon maximal du calendrier
    nb_fichiers: int = 1            # relevés et fichiers de factures cumulés
    scenarios: bool = False
    exports: bool = False
    profil_entreprise: bool = False
    arguments: tuple[str, ...] = ()

    @property
    def gratuit(self) -> bool:
        return self.prix_mensuel == 0

    def prix(self, periode: Periode) -> int:
        return (self.prix_annuel if periode is Periode.ANNUELLE
                else self.prix_mensuel)

    def prix_affiche(self, periode: Periode = Periode.MENSUELLE) -> str:
        if self.gratuit:
            return "Gratuit"
        symbole = {"usd": "$", "eur": "€", "gbp": "£"}.get(self.devise, self.devise)
        if periode is Periode.ANNUELLE:
            return f"{self.prix_annuel / 100:.0f} {symbole} par an"
        return f"{self.prix_mensuel / 100:.0f} {symbole} par mois"

    @property
    def economie_annuelle(self) -> int:
        """Pourcentage gagné en payant à l'année plutôt qu'au mois."""
        if self.prix_mensuel == 0 or self.prix_annuel == 0:
            return 0
        plein = self.prix_mensuel * 12
        return round((plein - self.prix_annuel) / plein * 100)


OFFRES: dict[Plan, Offre] = {

    Plan.DECOUVERTE: Offre(
        plan=Plan.DECOUVERTE,
        nom="Découverte",
        resume="Pour voir si Dayzon vous parle.",
        jours_projection=90,
        nb_fichiers=1,
        scenarios=False,
        exports=False,
        profil_entreprise=False,
        arguments=(
            "Calendrier de trésorerie sur 90 jours",
            "Un relevé bancaire importé",
            "Analyse de vos dépenses en langage clair",
        )),

    Plan.PARTICULIER: Offre(
        plan=Plan.PARTICULIER,
        nom="Particulier",
        resume="Votre budget, votre solde à venir, vos scénarios.",
        prix_mensuel=700,          # 7 $
        prix_annuel=5900,          # 59 $  — 30 % de moins que 12 × 7 $
        jours_projection=365,
        nb_fichiers=99,
        scenarios=True,
        exports=True,
        profil_entreprise=False,
        arguments=(
            "Calendrier sur 12 mois",
            "Import illimité de relevés",
            "Scénarios « et si ? »",
            "Rapports Excel, PDF et Word",
            "Multidevise",
        )),

    Plan.ENTREPRISE: Offre(
        plan=Plan.ENTREPRISE,
        nom="Entreprise",
        resume="Vos indicateurs, vos clients, votre prévision.",
        prix_mensuel=2900,         # 29 $
        prix_annuel=24900,         # 249 $ — 28 % de moins que 12 × 29 $
        jours_projection=730,
        nb_fichiers=999,
        scenarios=True,
        exports=True,
        profil_entreprise=True,
        arguments=(
            "Tout le plan Particulier",
            "Runway, point d'équilibre, marge",
            "DSO, DPO, impayés, dépendance client",
            "Import des factures clients et fournisseurs",
            "Prévision sur 24 mois",
            "Rapport destiné à un banquier ou un investisseur",
        )),

    # Plan interne : aucun paiement configuré, ou démonstration commerciale.
    Plan.LIBRE: Offre(
        plan=Plan.LIBRE,
        nom="Accès complet",
        resume="Toutes les fonctions, sans restriction.",
        jours_projection=730,
        nb_fichiers=999,
        scenarios=True,
        exports=True,
        profil_entreprise=True),
}

OFFRES_VENDUES = [OFFRES[Plan.DECOUVERTE], OFFRES[Plan.PARTICULIER],
                  OFFRES[Plan.ENTREPRISE]]


# ---------------------------------------------------------------------------
# L'abonnement d'un utilisateur
# ---------------------------------------------------------------------------

@dataclass
class Abonnement:
    """L'état d'un compte à un instant donné."""
    plan: Plan = Plan.LIBRE
    periode: Periode = Periode.MENSUELLE
    fin: date | None = None
    identifiant_client: str = ""        # customer Stripe
    identifiant_abonnement: str = ""    # subscription Stripe
    annule: bool = False                # résilié, mais encore valable jusqu'à `fin`

    @property
    def offre(self) -> Offre:
        return OFFRES[self.plan]

    def actif(self, au: date | None = None) -> bool:
        """
        Un abonnement résilié reste actif jusqu'au terme payé. On ne coupe
        jamais un accès déjà réglé : c'est la règle, et c'est aussi la loi
        dans la plupart des juridictions.
        """
        if self.plan in (Plan.LIBRE, Plan.DECOUVERTE):
            return True
        if self.fin is None:
            return False
        return (au or date.today()) <= self.fin

    def jours_restants(self, au: date | None = None) -> int | None:
        if self.fin is None:
            return None
        return max(0, (self.fin - (au or date.today())).days)

    def plan_effectif(self, au: date | None = None) -> Plan:
        """Le plan réellement applicable : on retombe en Découverte si expiré."""
        return self.plan if self.actif(au) else Plan.DECOUVERTE

    def offre_effective(self, au: date | None = None) -> Offre:
        return OFFRES[self.plan_effectif(au)]

    # ---- Droits ---------------------------------------------------------

    def autorise(self, fonction: str, au: date | None = None) -> bool:
        """
        Répond par oui ou par non à une fonction nommée.

        Fonctions reconnues : "scenarios", "exports", "entreprise".
        Une fonction inconnue est autorisée — on n'invente pas de restriction.
        """
        o = self.offre_effective(au)
        return {"scenarios": o.scenarios,
                "exports": o.exports,
                "entreprise": o.profil_entreprise}.get(fonction, True)

    def limite_jours(self, au: date | None = None) -> int:
        return self.offre_effective(au).jours_projection

    def limite_fichiers(self, au: date | None = None) -> int:
        return self.offre_effective(au).nb_fichiers

    def etat(self, au: date | None = None) -> str:
        """Une phrase à afficher, sans jargon."""
        au = au or date.today()
        if self.plan is Plan.LIBRE:
            return "Accès complet — aucun paiement configuré."
        if self.plan is Plan.DECOUVERTE:
            return "Plan Découverte — calendrier sur 90 jours, un fichier."
        if not self.actif(au):
            return (f"Votre abonnement {self.offre.nom} a pris fin le "
                    f"{self.fin.strftime('%d/%m/%Y')}. "
                    f"Vous êtes revenu au plan Découverte.")
        restants = self.jours_restants(au)
        if self.annule:
            return (f"Abonnement {self.offre.nom} résilié. Vous en gardez "
                    f"l'usage encore {restants} jours, jusqu'au "
                    f"{self.fin.strftime('%d/%m/%Y')}.")
        return (f"Abonnement {self.offre.nom} actif, renouvelé le "
                f"{self.fin.strftime('%d/%m/%Y')}.")


# ---------------------------------------------------------------------------
# Configuration Stripe
# ---------------------------------------------------------------------------

@dataclass
class ConfigStripe:
    """Ce que l'application sait de Stripe. Vide = mode libre."""
    cle_secrete: str = ""
    prix: dict[tuple[Plan, Periode], str] = field(default_factory=dict)
    url_retour: str = "http://localhost:8501"

    @property
    def configure(self) -> bool:
        return bool(self.cle_secrete) and bool(self.prix)

    def identifiant_prix(self, plan: Plan, periode: Periode) -> str | None:
        return self.prix.get((plan, periode))


def _depuis(source: dict, cle: str, defaut: str = "") -> str:
    valeur = source.get(cle, defaut)
    return str(valeur) if valeur is not None else defaut


def charger_configuration(secrets: dict | None = None) -> ConfigStripe:
    """
    Lit la configuration dans les secrets Streamlit, sinon dans
    l'environnement. Ne lève jamais d'exception : une configuration absente
    est un cas normal, pas une erreur.
    """
    source: dict = {}
    if secrets:
        source = dict(secrets)
    else:
        try:
            import streamlit as st
            source = dict(st.secrets.get("stripe", {}))
        except Exception:
            source = {}

    if not source:
        source = {c: os.environ.get(f"DAYZON_{c.upper()}", "")
                  for c in ("cle_secrete", "url_retour",
                            "prix_particulier_mensuel", "prix_particulier_annuel",
                            "prix_entreprise_mensuel", "prix_entreprise_annuel")}

    prix: dict[tuple[Plan, Periode], str] = {}
    for plan, prefixe in ((Plan.PARTICULIER, "particulier"),
                          (Plan.ENTREPRISE, "entreprise")):
        for periode, suffixe in ((Periode.MENSUELLE, "mensuel"),
                                 (Periode.ANNUELLE, "annuel")):
            identifiant = _depuis(source, f"prix_{prefixe}_{suffixe}")
            if identifiant:
                prix[(plan, periode)] = identifiant

    return ConfigStripe(
        cle_secrete=_depuis(source, "cle_secrete"),
        prix=prix,
        url_retour=_depuis(source, "url_retour", "http://localhost:8501"),
    )


# ---------------------------------------------------------------------------
# Paiement
# ---------------------------------------------------------------------------

class ErreurPaiement(Exception):
    """Le paiement n'a pas pu être engagé. Le message est destiné à l'écran."""


def ouvrir_paiement(plan: Plan, periode: Periode, config: ConfigStripe,
                    email: str = "", identifiant_client: str = "") -> str:
    """
    Crée une session de paiement Stripe et renvoie l'adresse où envoyer
    l'utilisateur.

    Aucune donnée de carte ne transite par Dayzon : la saisie a lieu sur les
    pages de Stripe. C'est ce qui nous dispense des obligations PCI-DSS.
    """
    if not config.configure:
        raise ErreurPaiement(
            "Le paiement n'est pas encore configuré sur cette installation.")

    identifiant_prix = config.identifiant_prix(plan, periode)
    if not identifiant_prix:
        raise ErreurPaiement(
            f"Aucun tarif n'est configuré pour le plan {OFFRES[plan].nom} "
            f"en formule {periode.value}.")

    try:
        import stripe
    except ImportError:
        raise ErreurPaiement(
            "La bibliothèque Stripe n'est pas installée. "
            "Lancez : py -m pip install stripe")

    stripe.api_key = config.cle_secrete

    parametres = {
        "mode": "subscription",
        "line_items": [{"price": identifiant_prix, "quantity": 1}],
        "success_url": f"{config.url_retour}?paiement=ok",
        "cancel_url": f"{config.url_retour}?paiement=annule",
        "allow_promotion_codes": True,
        "client_reference_id": identifiant_client or None,
        "metadata": {"plan": plan.value, "periode": periode.value,
                     "produit": "dayzon"},
    }
    if identifiant_client:
        parametres["customer"] = identifiant_client
    elif email:
        parametres["customer_email"] = email

    try:
        session = stripe.checkout.Session.create(
            **{k: v for k, v in parametres.items() if v is not None})
    except Exception as erreur:
        raise ErreurPaiement(f"Stripe a refusé la demande : {erreur}")

    return session.url


def lire_abonnement(identifiant_client: str, config: ConfigStripe) -> Abonnement:
    """
    Interroge Stripe et renvoie l'état réel de l'abonnement.

    En cas d'indisponibilité de Stripe, on renvoie le plan Découverte plutôt
    que de lever une exception : une panne de notre côté ne doit pas afficher
    une erreur incompréhensible à quelqu'un qui a payé.
    """
    if not config.configure or not identifiant_client:
        return Abonnement(plan=Plan.LIBRE)

    try:
        import stripe
        stripe.api_key = config.cle_secrete
        liste = stripe.Subscription.list(customer=identifiant_client,
                                         status="all", limit=10)
    except Exception:
        return Abonnement(plan=Plan.DECOUVERTE)

    vivants = [a for a in liste.data
               if a.status in ("active", "trialing", "past_due")]
    if not vivants:
        return Abonnement(plan=Plan.DECOUVERTE,
                          identifiant_client=identifiant_client)

    a = max(vivants, key=lambda x: x.get("current_period_end", 0))
    metadonnees = a.get("metadata") or {}
    valeur = metadonnees.get("plan", "")
    plan = Plan(valeur) if valeur in {p.value for p in Plan} else Plan.PARTICULIER

    # À défaut de métadonnée, on retrouve le plan par l'identifiant de tarif.
    if not valeur:
        try:
            prix_utilise = a["items"]["data"][0]["price"]["id"]
            for (p, _), identifiant in config.prix.items():
                if identifiant == prix_utilise:
                    plan = p
                    break
        except Exception:
            pass

    fin = None
    horodatage = a.get("current_period_end")
    if horodatage:
        fin = datetime.fromtimestamp(horodatage).date()

    periode_valeur = metadonnees.get("periode", "")
    periode = (Periode(periode_valeur) if periode_valeur in {p.value for p in Periode}
               else Periode.MENSUELLE)

    return Abonnement(
        plan=plan,
        periode=periode,
        fin=fin,
        identifiant_client=identifiant_client,
        identifiant_abonnement=a.get("id", ""),
        annule=bool(a.get("cancel_at_period_end")),
    )


def portail_client(identifiant_client: str, config: ConfigStripe) -> str:
    """
    Adresse du portail Stripe où l'utilisateur gère lui-même sa carte,
    ses factures et sa résiliation. Nous n'avons rien à construire pour cela,
    et surtout rien à stocker.
    """
    if not config.configure or not identifiant_client:
        raise ErreurPaiement("Aucun compte de facturation n'est rattaché.")
    try:
        import stripe
        stripe.api_key = config.cle_secrete
        session = stripe.billing_portal.Session.create(
            customer=identifiant_client, return_url=config.url_retour)
        return session.url
    except Exception as erreur:
        raise ErreurPaiement(f"Portail indisponible : {erreur}")
