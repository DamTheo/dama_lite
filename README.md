# DAMA Lite — incubateur 8 caméras

DAMA Lite pilote un incubateur de laboratoire basé sur **Raspberry Pi 4 (Incub-resa, 192.168.1.201)**. Son interface tactile est inspirée du visage, de la charte et des animations de `DamTheo/dama-companion-interface`, mais son logiciel est **indépendant** de DAMA Companion.

> **Statut (23/10/2026) : V0.1 installée en staging sur Incub-resa, écran tactile DSI 800×480 et service systemd activés au démarrage et vérifiés après reboot.** Deux webcams UC60 reconnues et aperçus HTTP 200. **Chauffage, LED physiques et extinction OS désactivés** dans ce service de validation ; régulation sous charge et Microsoft Entra encore en attente. Aucun fichier SharePoint transféré par DAMA Lite.

## Contrat fonctionnel

- Écran tactile rectangulaire Raspberry Pi **7 pouces** : visage DAMA, toucher pour ouvrir « Nouvelle analyse » ou « Visualiser une caméra », écran de suivi et animation de démarrage / extinction.
- **8 emplacements USB indépendants** : une caméra = une analyse ; photographie immédiate puis toutes les **5 minutes** ; démarrages et arrêts indépendants.
- **Température de l'enceinte** : DS18B20 `28-0000006ca681` sur **BCM GPIO22** ; consigne **37 °C** ; démarrage d'une nouvelle analyse seulement à partir de **35 °C** (si les vérifications et sécurités sont satisfaites).
- **Chauffage** : relais ON/OFF sur **BCM GPIO21** ; coupure sur sonde incohérente/perdue, défaut thermique et extinction ; hystérésis, journal d'événements. Polarité du relais et thermostat matériel à valider avant toute activation.
- **Température CPU du Pi 4** : avertissement à **65 °C** ; ce capteur **ne remplace pas** la sécurité thermique de l'enceinte.
- **64 NeoPixels** sur **BCM GPIO12**, luminosité **plafonnée à 10 %**, **8 LED par caméra** : vert disponible, jaune analyse en cours, rouge défaut, éteint si indisponible. Extinction temporaire du bandeau pendant chaque photographie.
- **SharePoint** par Microsoft Graph : **un dossier directement par test**, sans dossier par caméra ni sous-dossier journalier, sous `03_Projets/04_Résazurine/03_Expérimentations & Résultats/DAMA-Lite/<Nom du test>/`. Les photos sont enregistrées dans une file locale persistante jusqu'à confirmation du transfert.
- **Autonomie** : backend supervisé par systemd, kiosque plein écran au démarrage, chauffe démarrée par le service (après qualification et activation explicite), bouton physique d'extinction à raccorder, animation puis arrêt propre du système.

## Structure

- `backend/dama_lite/` : API locale, contrôleur thermique, caméras, NeoPixels, gestion des tests, SQLite et transferts Graph.
- `ui/` : React + TypeScript + Vite, écran tactile responsive 7 pouces ; animations de visage et de mise sous tension adaptées de DAMA.
- `backend/tests/` : tests unitaires hors matériel.
- `deploy/` : configuration et unités système ; service de staging sécurisé réellement activé, service de production non activé.
- `docs/` : sécurité, qualification et architecture.

## Sécurité de déploiement

**NE PAS** activer la chauffe sans vérifier sur la machine : polarité physique et comportement à la perte d'alimentation du relais, contact normalement ouvert, protection thermique matérielle indépendante, précision/position de la sonde, répartition thermique aux huit emplacements, GPIO du bouton d'extinction et alimentation LED/caméras. Le logiciel, même supervisé, ne suffit pas à garantir une coupure sûre si un relais reste mécaniquement collé.

Le serveur HTTP doit écouter **exclusivement 127.0.0.1**. Les clés SSH et certificats SharePoint ne doivent jamais être présents dans Git. Le chemin Windows synchronisé de SharePoint sur PC01 n'est pas accessible directement au Pi : l'envoi se fait via Microsoft Graph.

## Utilisation en développement

Voir `docs/STAGING_SERVICE.md` (installation de validation), `docs/USB_CAMERAS.md` (appairage), `docs/ENTRA.md` (authentification future) et `docs/INSTALLATION.md` (bascule de production non réalisée).

## Origines

Sources du contrôleur : scripts de laboratoire `Programme_complet.py`, `Test_LED.py` et `temperature.py` (audités le 23 octobre 2026). Animations et identité graphique inspirées de `DamTheo/dama-companion-interface`. Le simulateur clinique, le LLM et les modules DAMA historiques ne font pas partie de DAMA Lite.
