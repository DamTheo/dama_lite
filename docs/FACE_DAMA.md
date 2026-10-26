# Visage de DAMA — fidélité avec DAMA Companion

Source canonique inspectée en lecture seule dans
\`DamTheo/dama-companion-interface\` :
- \`src/components/DamaSimulator.tsx\` : yeux annulaires et
  sourire SVG (\`M 12 8 Q 50 46 88 8\`).
- \`src/styles.css\` : largeur des yeux **27 %** de la zone,
  marges latérales **7 %**, sourire **27 %**, animation du regard sur
  **11 s** (déplacements +7 / -6 px), clignement **7 s**, trait blanc 5 px.

Écart corrigé : la version DAMA Lite rétrécissait excessivement le visage
en CSS à **33vh ≈ 158 px** à la résolution réelle 800×480 et utilisait
un sourire de largeur 35 % qui déformait ses proportions.

Nouvelle version :
- visage d'accueil jusqu'à **230 px** à 800×480 ;
- yeux plus grands, positions, clignement et regard fidèles au compagnon ;
- sourire revenu à **27 %** et trait blanc avec extrémités arrondies ;
- respiration douce, réponse au toucher et sommeil avec Zzz si activé ;
- adaptation 7 pouces rectangulaire ; ne pas réutiliser le masque 5" rond ;
- respecte \`prefers-reduced-motion\` pour les animations.

Seuls les éléments graphiques du personnage ont été repris, pas les
simulateurs LIMS, voix ou modules fictifs du compagnon.
