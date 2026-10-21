# Actions — <mission>

> À copier vers `<projet>/state/actions.md` (liens écrits pour une mission client). Ce registre fait foi pour ID, responsable, échéance et statut ; conserver le préfixe d'ID du client, y compris entre missions. La ligne d'action garde ID, responsable, intitulé et métadonnées Tasks (priorité, `📅` échéance précise, `⏳` date de travail choisie) ; seules les nuances d'échéance, la source et l'historique vont en sous-puces. Ne pas dupliquer une date `📅` en sous-puce. États : `[ ]` à faire · `[/]` en cours · `[w]` en attente (relancée) · `[x]` faite · `[-]` annulée. Le tableau [`tasks.md`](../../../../../../tasks.md) l'affiche avec le plugin Tasks. Une action close depuis plus de 30 jours passe avec ses sous-puces dans `actions-archive-AAAA.md`, sans demander (ID réservés ; voir `docs/CONVENTIONS.md`).

## Ouvertes
- [ ] **<ID>** — <responsable> — <action concrète> 📅 YYYY-MM-DD
    - échéance: <nuance si nécessaire, sinon retirer cette puce>
    - source: [YYYY-MM-DD-<type>-<slug>](../sources/YYYY-MM/YYYY-MM-DD-<type>-<slug>.md)
    - créée : YYYY-MM-DD HH:MM
    - mise à jour : YYYY-MM-DD HH:MM
    - JJ/MM : <changement d'état, avec sa source>

## Terminées
- [x] **<ID>** — <responsable> — <action réalisée> 📅 YYYY-MM-DD ✅ YYYY-MM-DD
    - source: [YYYY-MM-DD-<type>-<slug>](../sources/YYYY-MM/YYYY-MM-DD-<type>-<slug>.md)
    - faite : <preuve datée, ou case cochée par le propriétaire dans le tableau>

## Annulées
- [-] **<ID>** — <responsable> — <action> ❌ YYYY-MM-DD
    - annulée le YYYY-MM-DD par <personne> — [source](../sources/YYYY-MM/YYYY-MM-DD-<type>-<slug>.md)
