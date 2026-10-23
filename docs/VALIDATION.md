# Plan de qualification de l'incubateur DAMA Lite

Critères de lancement de la phase de tests : protection thermique matérielle fonctionnelle, relais contrôlé, alimentation USB suffisante, certificat Graph et identifiant caméra stable. La conformité analytique est hors périmètre de cette version d'acquisition.

| Essai | Entrée / perturbation | Réponse attendue |
|---|---|---|
| Préchauffage | Enceinte à 34,9 °C | Analyse refusée, pas de dossier créé |
| Première autorisation | Enceinte à 35,0 °C | Analyse possible si caméra/Graph disponibles et sans défaut |
| Régulation | Enceinte vers 37 °C | ON/OFF avec hystérésis, dépassement thermique mesuré |
| Sonde | Débranchement, CRC invalide, valeur 85 °C | Relais désactivé et défaut verrouillé |
| Température enceinte | Dépassement du seuil de sécurité qualifié | Coupure de chauffe, alerte et aucune nouvelle analyse |
| CPU | 65 °C | Avertissement « Attention, j'ai chaud » |
| Caméras | Retirer/rebrancher chaque USB ; reboot | Identité de chaque emplacement conservée |
| Acquisition | 8 tests avec départs décalés | 1 image par test au départ puis toutes les 5 min, sans confusion d'image |
| Éclairage | LED couleur active pendant preview / photo | LED éteintes pendant acquisition, absence de contamination colorimétrique |
| Dossiers SharePoint | Deux tests sur caméras différentes | Un dossier \`DAMA-Lite/Nom_test\` par test, aucune sous-arborescence caméra |
| Doublon | Nom déjà présent sur SharePoint | Refus clair, aucun nouveau test ouvert |
| Réseau indisponible en cours | Interruption Graph | Images conservées localement, puis resynchronisées |
| Stockage local saturé | Dépassement quota spool | Session en défaut, aucune perte de photo non signalée |
| Redémarrage du backend | Acquisition active | Anciennes sessions identifiées « interrupted » et données conservées |
| Écran tactile | Démarrage sans clavier | Visage visible et navigation tactile fonctionnelle |
| Bouton physique | Maintien GPIO de la commande réelle | Chauffe coupée d'abord, sessions interrompues, animation puis OS arrêté |

### Qualification thermique scientifique

Cartographier au minimum les positions 1 à 8 à l'aide de références traçables à 35 °C puis à 37 °C. Relever les courbes lors d'un démarrage froid, de l'ouverture/fermeture de l'enceinte et lors d'une charge complète. Distinguer température de contrôle DS18B20, température de chaque échantillon, gradient spatial et retard thermique. Fixer un critère d'acceptation de stabilité **avant** d'examiner les résultats. Ne pas extrapoler la précision d'une sonde unique à toutes les positions.
