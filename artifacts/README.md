# artifacts/ — outputs destinés aux humains

> Les fichiers produits **pour être vus par quelqu'un** : decks, one-pagers, documents Office, PDF, exports, diagrammes, maquettes. Ni du code (→ `repos/`), ni du contexte de travail (→ `brain/`), ni du scratch d'agent (→ `agents/`).

Ça couvre les vrais livrables (un deck, un one-pager) **et** les artefacts de travail qui ne sont livrés à personne mais qui restent des documents (un schéma, une page HTML de synthèse) **et** le matériel source reçu d'un client ou d'un tiers quand il est volumineux (un Excel, un PDF, une capture d'écran). Le critère n'est pas « qui l'a fait », mais « est-ce un gros binaire qui n'a rien à faire dans un historique git » (voir plus bas).

## Structure

Groupé **par projet d'abord**, puis un dossier par artefact :

```
artifacts/
├── <client>/                   # un dossier par client, à plat
│   └── <slug-artefact>/
│       ├── README.md           # provenance : d'où ça vient, à quoi ça sert, comment le rebuild
│       └── …
└── internal/                   # ce qui n'a pas de client
    └── <projet>/
        └── <slug-artefact>/
```

Chaque dossier d'artefact porte un `README.md` de provenance — sans lui, on retrouve dans six mois un `.pptx` de 4 Mo dont personne ne sait s'il est à jour ni comment le régénérer. Minimum : **quoi** (une phrase), **usage** (pour qui, envoyé quand), **provenance** (généré par quoi, depuis quelle note, quel jour), **maintenance** (comment le refaire).

## Les fichiers de fabrication vivent dans `agents/` ou un repo

Ici restent les livrables destinés à être lus par un humain et leur README de provenance. Plans de build, scripts et rendus intermédiaires vivent dans `agents/<projet>/<session>/` pendant la fabrication. Si un générateur doit être conservé et réutilisé, le promouvoir dans un repo adapté. Le README de l'artefact indique où trouver sa source tant qu'elle existe ; ne pas modifier la sortie à la main quand elle peut être régénérée.

## Les artefacts ne sont pas versionnés

À part ce README, le contenu du dossier est ignoré par Git : les fichiers peuvent être lourds et les binaires ne se diffent pas. La mémoire garde le pointeur (la fiche projet mentionne l'artefact et son chemin). Un générateur conservé durablement est versionné dans un repo ; dans `agents/`, il reste jetable. Si tu veux une sauvegarde du livrable, utilise un emplacement de stockage adapté, pas ce dépôt Git.

**Matériel source reçu** (workbook Excel, export PDF, capture d'écran transmis par un client) : même règle — ça va ici, pas dans `brain/` (versionné en git, pas fait pour porter des binaires). Le texte qui en est extrait (analyse, chiffres, notes) reste dans `brain/` sous forme de `.md`, avec un lien vers son dossier `artifacts/` correspondant.

⚠️ **Contenu client** : un artefact qui contient des données ou du contexte d'un client ne se publie jamais à l'extérieur (page web, service tiers, artefact partagé) sans demande explicite par pièce.
