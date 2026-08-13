# PrevuFlow

**Votre solde, n'importe quel jour à venir.**
*See your cash, day by day.*

PrevuFlow place vos revenus, vos factures et vos dépenses aux dates où ils tombent,
puis affiche votre solde pour chaque jour à venir — **sans jamais se connecter
à votre banque**.

---

## Le problème

Une personne ou une entreprise ne fait pas faillite parce qu'elle perd de
l'argent. Elle fait faillite parce qu'elle n'en a plus **le jour où il faut
payer**. Ce sont deux problèmes différents, et le second n'est visible que sur
un calendrier.

## Ce qui distingue PrevuFlow

Les outils comparables partent tous d'une connexion bancaire automatique.
PrevuFlow part d'un fichier — un relevé PDF, un CSV, un tableau Excel.

Ce n'est pas un pis-aller. C'est ce qui le rend utilisable **là où l'open
banking n'existe pas**, et **là où l'utilisateur ne souhaite pas confier ses
identifiants bancaires**.

Aucun plan comptable national : ni PCG, ni SYSCOHADA, ni IFRS, ni US GAAP.
PrevuFlow travaille sur ce qu'une entreprise possède partout dans le monde — des
flux bancaires et des factures. Le même produit sert à Dakar, Istanbul, Londres
ou Austin, sans adaptation.

---

## Deux profils

### Particulier

| Onglet | Ce qu'il donne |
|---|---|
| 📅 Calendrier | Solde de fin de journée, jour par jour |
| 📊 Mon analyse | Ce qui rentre, ce qui sort, ce qui reste · charges fixes contre dépenses variables |
| 🔮 Scénarios | « Je perds mon revenu principal », « le coût de la vie augmente de 10 % »… |
| 📄 Rapport | Excel, PDF, Word |

### Entreprise

| Onglet | Ce qu'il donne |
|---|---|
| 📈 Tableau de bord | Runway, point d'équilibre, marge, charges fixes et variables |
| 👥 Clients & fournisseurs | DSO, DPO, impayés, dépendance client |
| 📅 Trésorerie prévisionnelle | Les factures non réglées se placent à leur échéance |
| 🔮 Scénarios | « Je perds mon plus gros client », « mes clients paient 30 jours plus tard »… |
| 📄 Rapport | Excel dédié entreprise, PDF, Word |

---

## Ce que l'application lit

| Fichier | Format | Ce qu'il apporte |
|---|---|---|
| Relevé bancaire | PDF, CSV, Excel | Flux réels, résultat, charges, point d'équilibre, runway |
| Factures clients | CSV, Excel | DSO, impayés, dépendance client |
| Factures fournisseurs | CSV, Excel | DPO, encours à payer |

**Aucun n'est obligatoire.** Pour un fichier de factures, deux colonnes
suffisent : une date et un montant. Les intitulés sont reconnus en français
comme en anglais — *Invoice date, Customer, Amount, Due date, Paid on, Status*.

---

## Principes de conception

Ces règles ne sont pas des intentions : chacune est protégée par des tests.

**Aucun montant n'est un nombre flottant.** Tout est en `Decimal`, et chaque
montant porte sa devise. Additionner des euros et des dollars lève une erreur
au lieu de produire un total faux.

**Le nombre de décimales vient de la devise.** Le yen n'en a aucune, le dinar
koweïtien en a trois. Aucune hypothèse « deux décimales ».

**Un taux de change porte sa date et sa source.** Une conversion rend toujours
le taux employé : un total consolidé doit pouvoir être justifié.

**Un scénario ne modifie jamais les données de référence.** Il applique des
hypothèses à une copie, puis compare.

**Vos données restent chez vous.** La sauvegarde est locale, l'écriture est
atomique — une coupure de courant laisse l'ancien fichier intact, jamais un
fichier tronqué. Un fichier abîmé est renommé, jamais écrasé.

---

## Installation

```bash
pip install -r requirements.txt
streamlit run app_tresorerie.py
```

Python 3.10 ou supérieur.

## Tests

423 contrôles automatiques. Chaque valeur attendue est calculée à la main et
inscrite en commentaire dans le fichier de test.

```bash
python test_argent.py              # montants, devises, taux, triangulation
python test_comptes.py             # multi-comptes, consolidation
python test_moteur_tresorerie.py   # récurrences, projection, calendrier
python test_scenarios.py           # hypothèses, comparaison
python test_analyse_entreprise.py  # DSO, DPO, runway, point mort
python test_sauvegarde.py          # atomicité, migration, fichier abîmé
python test_abonnement.py          # plans, droits, échéances
```

---

## Architecture

Le noyau financier ne connaît ni l'interface, ni les fichiers, ni le réseau.
Il est testable seul.

```
NOYAU PUR
  moteur_tresorerie.py    projection jour par jour, récurrences
  argent.py               Montant, Taux daté et sourcé, Conversion
  comptes.py              Compte, Portefeuille, Consolidation
  scenarios.py            hypothèses immuables, comparaison
  analyse_lisible.py      catégories et postes, en langage clair
  analyse_entreprise.py   factures et indicateurs
  abonnement.py           plans et droits
  sauvegarde.py           persistance atomique et versionnée

LIAISON
  commun.py               état de session, formatage, projection

INTERFACE
  app_tresorerie.py       aiguillage des profils
  vue_*.py                comptes, calendrier, entreprise, scénarios
  export_rapport.py       Excel, PDF, Word
  import_intelligent.py   lecture PDF, CSV, Excel
```

---

## Licence

**Code visible, pas open source.** Copyright © 2026 SMD GLOBAL CONSULTING LLC.
Tous droits réservés. Voir [LICENSE](LICENSE).

Vous pouvez lire ce code et exécuter l'application pour votre évaluation
personnelle. Toute copie, modification, distribution ou usage commercial
requiert une autorisation écrite.

---

## Avertissement

PrevuFlow produit des **projections indicatives**. Il ne constitue ni un conseil
comptable, ni fiscal, ni juridique, ni en investissement. Chaque chiffre doit
être vérifié avant toute décision.

---

*SMD GLOBAL CONSULTING LLC — Wyoming, États-Unis*
