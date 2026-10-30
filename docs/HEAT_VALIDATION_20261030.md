# DAMA Lite - préqualification thermique du 30 octobre 2026

## Observations directes sur Incub-resa (.201)

- Sonde DS18B20 `28-0000006ca681` sur GPIO22, CRC YES.
- Avant le test : **21,625 °C**, CPU **46,738 °C**.
- Préqualification répétée : **5 lectures de 21,687 °C**, CPU **47,23 °C**.
- `GPIO21` en entrée ; sortie de chauffe non activée.
- `/etc/dama-lite/heating-qualified` absent.
- Service de chauffage de production non installé sur `/opt/dama-lite`.
- Le service de staging interdit explicitement `heating_enabled=true`.

## Résultats des essais logiciels

- 8 tests du contrôleur thermique : réussis.
- 2 tests du précontrôle, sonde réelle et relais simulé : réussis.
- Test ajouté `test_thermal_cycle.py` : montée de 21,687 à 38,0 °C
  **par injection de températures**, puis refroidissement,
  redémarrage de la chauffe, et défauts simulés de sonde/CPU.
- Aucune courbe de montée réelle à 37-38 °C n'a été obtenue :
  le relais GPIO21 et la résistance n'ont pas été mis sous tension.

## Comportement du régulateur prévu

1. <35 °C : chauffe demandée, expériences interdites.
2. 35 °C : expériences autorisables seulement si chauffe réellement
   qualifiée, capteurs sains, caméra disponible et tests configurés.
3. Depuis l'arrêt : relais ON pour T <=36,7 °C.
4. En chauffe : relais OFF pour T >=37,3 °C.
5. Si T=38 °C (après une éventuelle inertie) : relais reste OFF.
6. Si T redescend à <=36,7 °C : relais revient ON.
7. Enceinte >=41 °C, CPU >=80 °C, perte de sonde CPU ou DS18B20 :
   chauffage OFF et défaut verrouillé jusqu'à reprise contrôlée.
8. CPU >=65 °C : alerte ; cette alerte seule ne coupe pas la chauffe.

## Éléments indispensables pour l'essai réel

- Contrôle sur place du relais : activation par niveau haut et borne
  normalement ouverte, résistance hors tension à l'arrêt du Pi.
- Vérification d'un **thermostat ou fusible thermique indépendant**,
  en série avec la résistance. Son seuil/câblage doivent être relevés.
- Opérateur présent, température indépendante, accès à la coupure
  d'alimentation, absence de matière thermosensible/inflammable.
- Installer et qualifier séparément le service de production avec
  son garde matériel ; ne pas modifier le profil de staging pour
  contourner ses protections.

## Essai physique à réaliser après qualification

- Préparer une enceinte sans échantillons, mesurer la sonde indépendante.
- Documenter T0, temps pour 35 °C, temps pour 37 °C, pic thermique,
  états relais ON/OFF, T CPU.
- Suivre le maintien autour de 37 °C durant au moins 30 minutes :
  consigner minimum, maximum, amplitudes et durées des cycles.
- Critère fonctionnel visé : température de travail voisine de
  **37-38 °C**, sans échauffement anormal ni défaut.
- La cible logicielle reste 37 °C avec hystérésis +/-0,3 °C.
  Les dépassements dus à l'inertie ne sont pas prévisibles avant une
  mesure réelle ; adapter ensuite la régulation sur la base des données.

**Décision du 30/10 : logiciel testé, qualification physique NON
terminée ; ne pas conclure au bon maintien réel à 37-38 °C.**
