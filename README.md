# DAMA Lite — incubateur 8 caméras

DAMA Lite pilote un incubateur de laboratoire basé sur **Raspberry Pi 4 (Incub-resa, 192.168.1.201)**. Son interface tactile est inspirée du visage, de la charte et des animations de `DamTheo/dama-companion-interface`, mais son logiciel est **indépendant** de DAMA Companion.

> **Statut : code de développement GitHub, pas encore installé ni qualifié sur la machine.** Le chauffage est désactivé par défaut dans la configuration fournie. Aucun changement sur le Pi ou sur SharePoint n'est effectué en construisant ce dépôt.

## Contrat fonctionnel

- Écran tactile rectangulaire Raspberry Pi **7 pouces** : visage DAMA, toucher pour ouvrir « Nouvelle analyse » ou « Visualiser une caméra », écran de suivi et animation de démarrage / extinction.
- **8 emplacements USB indépendants** : une caméra = une analyse ; photographie immédiate puis toutes les **5 minutes** ; démarrages et arrêts indépendants.
- **Température de l'enceinte** : DS18B20 `28-0000006ca681` sur **BCM GPIO22** ; consigne **37 °C** ; démarrage d'une nouvelle analyse seulement à partir de **35 °C** (si les vérifications et sécurités sont satisfaites).
- **Chauffage** : relais ON/OFF sur **BCM GPIO21** ; coupure sur sonde incohérente/perdue, défaut thermique et extinction ; hystérésis, journal d'événements. Polarité du relais et thermostat matériel à valider avant toute activation.
- **Température CPU du Pi 4** : avertissement à **65 °C** ; ce capteur **ne remplace pas** la sécurité thermique de l'enceinte.
- **64 NeoPixels** sur **BCM GPIO12**, luminosité 10 %, **8 LED par caméra** : vert disponible, jaune analyse en cours, rouge défaut, éteint si non disponible. Extinction temporaire des LED pendant chaque photographie pour ne pas modifier le signal colorimétrique.
- **SharePoint** par Microsoft Graph : **un dossier directement par test**, sans dossier par caméra ni sous-dossier journalier, sous `03_Projets/04_Résazurine/03_Expérimentations & Résultats/DAMA-Lite/<Nom du test>/`. Les photos sont enregistrées dans une file locale persistante jusqu'à confirmation du transfert.
- **Autonomie** : backend supervisé par systemd, kiosque plein écran au démarrage, chauffe démarrée par le service (après qualification et activation explicite), bouton physique d'extinction à raccorder, animation puis arrêt propre du système.

## Structure

- `backend/dama_lite/` : API locale, contrôleur thermique, caméras, NeoPixels, gestion des tests, SQLite et transferts Graph.
- `ui/` : React + TypeScript + Vite, écran tactile responsive 7 pouces ; animations de visage et de mise sous tension adaptées de DAMA.
- `backend/tests/` : tests unitaires hors matériel.
- `deploy/` : exemples de configuration et de services ; **aucun déploiement automatique**.
- `docs/` : sécurité, qualification et architecture.

## Sécurité de déploiement

**NE PAS** activer la chauffe sans vérifier sur la machine : polarité physique et comportement à la perte d'alimentation du relais, contact normalement ouvert, protection thermique matérielle indépendante, précision/position de la sonde, répartition thermique aux huit emplacements, GPIO du bouton d'extinction et alimentation LED/caméras. Le logiciel, même supervisé, ne suffit pas à garantir une coupure sûre si un relais reste mécaniquement collé.

Le serveur HTTP doit écouter **exclusivement 127.0.0.1**. Les clés SSH et certificats SharePoint ne doivent jamais être présents dans Git. Le chemin Windows synchronisé de SharePoint sur PC01 n'est pas accessible directement au Pi : l'envoi se fait via Microsoft Graph.

## Utilisation en développement

Voir `docs/INSTALLATION.md` pour installation, configuration, tests et conditions préalables. Ne pas déployer sur la machine avant revue matérielle et essais progressifs.

## Origines

Sources du contrôleur : scripts de laboratoire `Programme_complet.py`, `Test_LED.py` et `temperature.py` (audités le 23 octobre 2026). Animations et identité graphique inspirées de `DamTheo/dama-companion-interface`. Le simulateur clinique, le LLM et les modules DAMA historiques ne font pas partie de DAMA Lite.
