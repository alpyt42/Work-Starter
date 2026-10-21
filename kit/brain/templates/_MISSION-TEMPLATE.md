# Mission: <Nom>

> À copier vers `projects/clients/<client>/missions/<mission>/<mission>.md`. Index court : état actuel et chemins de lecture. Les sources datées restent dans `sources/`, les actions et décisions font foi dans `state/`.

- **Client :** [<Nom>](../../<client>.md)
- **Status :** active | paused | done
- **Goal :** <une phrase : à quoi ressemble « terminé »>
- **Suivi du temps :** <référence confirmée par le propriétaire, jamais devinée ; facultatif, à retirer si inutile>
- **Repo :** <pointeur vers les dépôts utiles, sans copie de code>
- **Stakeholders :** [Prénom Nom](../../../../../people/prenom-nom.md)
- **Tableau :** [tasks](../../../../../tasks.md)

## En bref
- <périmètre, état, échéance et blocage principal en quelques lignes, avec sources>

## État actuel
- <ce qui a changé depuis le dernier point ; renvoyer au sujet ou à la source, ne pas dupliquer leur contenu>

## Lire selon le besoin
- [Actions](state/actions.md) — ID, responsable, échéance et statut faisant foi
- [Décisions](state/decisions.md) — proposées, validées, refusées, remplacées
- [Glossaire](state/glossary.md) — facultatif : termes, sigles et erreurs de transcription du projet
- [Sources du mois](sources/YYYY-MM/index.md) — une entrée par réunion ou échange substantiel
- [<Sujet de travail>](workstreams/<sujet>.md) — doc de référence ou état vivant du sujet, nommé par sujet et jamais daté, si nécessaire
- [<Note datée>](notes/YYYY-MM-DD-<sujet>.md) — note de travail datée du propriétaire, si nécessaire

## Timeline
> Jalons internes et changements d'état, une ligne chacun. Les sources figurent dans l'index mensuel. Seul le mois en cours reste ici : dès qu'il écrit un nouveau mois, l'agent déplace sans demander les entrées antérieures, inchangées, dans `journal/YYYY-MM.md` (convention du brain) et liste les mois archivés ci-dessous (ligne à retirer tant que rien n'est archivé).
Mois précédents : [YYYY-MM](journal/YYYY-MM.md)
- YYYY-MM-DD — <jalon ou changement d'état, avec lien>
